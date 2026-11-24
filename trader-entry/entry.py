#!/usr/bin/env python3
"""Entry Timer (NSE, long only). Says waiting / triggered / expired / not open on completed bars.

  python3 trader-entry/entry.py check SYMBOL [--setup orb|level] [--level 845.5] [--interval 5m] [--or-minutes 15] [--vol-mult 1.5]
  python3 trader-entry/entry.py watch SYMBOL [--every 30] [--max-minutes 120]
Triggered writes trader/entry.json for trader-exit. Never places an order.
"""

import argparse, datetime as dt, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402

MINUTES = {"1m": 1, "5m": 5, "15m": 15}


def evaluate(bars, now, setup="orb", or_minutes=15, interval="5m", level=None, vol_mult=0.0, window=("09:30", "14:30")):
    """bars: one session's [t,o,h,l,c,v]. Only bars that have CLOSED by `now` count."""
    step = MINUTES[interval]
    st = C.market_status(now)
    res = {"setup": setup, "interval": interval, "now": now.strftime("%H:%M")}
    if st["state"] in ("before pre-open", "pre-open") or (st["state"] == "closed" and st["why"] != "after close"):
        return dict(res, status="not open", why=st["why"] if st["state"] == "closed" else "opens 09:15 IST")
    done = [b for b in bars if C.parse_iso(b[0]) + dt.timedelta(minutes=step) <= now]
    if not done:
        return dict(res, status="waiting", why="no completed bar yet")
    t_open = dt.datetime.combine(now.date(), C.OPEN, C.IST)
    or_end = t_open + dt.timedelta(minutes=or_minutes)
    rng = [b for b in done if C.parse_iso(b[0]) < or_end]
    if setup == "orb":
        if now < or_end or len(rng) < or_minutes // step:
            return dict(res, status="waiting", why="opening range forming until %s" % or_end.strftime("%H:%M"))
        lvl = max(b[2] for b in rng)
        res.update(or_high=lvl, or_low=min(b[3] for b in rng))
    else:
        if level is None:
            raise ValueError("--level is required for setup 'level'")
        lvl = float(level)
    res["level"] = lvl
    avg_v = sum(b[5] for b in rng) / len(rng) if rng else None
    last_ok = dt.datetime.combine(now.date(), C.hhmm(window[1]), C.IST)
    first_ok = dt.datetime.combine(now.date(), C.hhmm(window[0]), C.IST)
    for b in done:
        t = C.parse_iso(b[0])
        if setup == "orb" and t < or_end:
            continue
        end = t + dt.timedelta(minutes=step)
        if b[4] > lvl and end >= first_ok:
            if vol_mult and avg_v and b[5] < vol_mult * avg_v:
                continue
            if end > last_ok:
                return dict(res, status="expired", why="first close above %.2f came at %s, after the %s cutoff" % (lvl, end.strftime("%H:%M"), window[1]))
            return dict(res, status="triggered", entry=b[4], time=end.strftime("%H:%M"),
                        pct_over=round((b[4] / lvl - 1) * 100, 2), bar=b)
    if now >= last_ok:
        return dict(res, status="expired", why="no close above %.2f before %s" % (lvl, window[1]))
    last = done[-1][4]
    return dict(res, status="waiting", last=last, away_pct=round((lvl / last - 1) * 100, 2),
                why="last close %.2f is %.2f%% under %.2f" % (last, (lvl / last - 1) * 100, lvl))


def describe(sym, r):
    s = r["status"].upper()
    if r["status"] == "triggered":
        return "%s %s at %s: closed %.2f, %.2f%% over %.2f (%s %s)" % (sym, s, r["time"], r["entry"], r["pct_over"], r["level"], r["setup"], r["interval"])
    return "%s %s (%s): %s" % (sym, s, r["now"], r["why"])


def _meta(sym):
    try:
        return C.load_universe(None)["symbols"].get(sym, {})
    except C.SourceError:
        return {}


def run_once(a, sym, now):
    cfg = C.load_config()
    meta = _meta(sym)
    got = C.get_bars(sym, a.interval, 1 if a.interval == "1m" else 2, now, token=meta.get("token"))
    bars = C.session_bars(got["bars"], now.date())
    win = tuple(cfg.get("entry_window") or ("09:30", "14:30"))
    r = evaluate(bars, now, a.setup, a.or_minutes, a.interval, a.level, a.vol_mult, win)
    r.update(symbol=sym, source=got["source"], fetched_at=got["fetched_at"], token=meta.get("token"), tick=meta.get("tick"))
    print(describe(sym, r) + "  [%s, fetched %s]" % (got["source"], got["fetched_at"][11:16]))
    if r["status"] == "triggered":
        r.pop("bar", None)
        r["date"] = now.date().isoformat()
        C.write_json(C.path("entry.json"), r)
        print("  -> trader/entry.json written. Next: /trader-exit")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "watch"):
        p = sp.add_parser(name)
        p.add_argument("symbol")
        p.add_argument("--setup", choices=("orb", "level"), default="orb")
        p.add_argument("--level", type=float)
        p.add_argument("--interval", choices=tuple(MINUTES), default="5m")
        p.add_argument("--or-minutes", type=int, default=15)
        p.add_argument("--vol-mult", type=float, default=0.0)
        p.add_argument("--now")
        if name == "watch":
            p.add_argument("--every", type=int, default=30)
            p.add_argument("--max-minutes", type=int, default=120)
    a = ap.parse_args(argv)
    sym = a.symbol.upper()
    try:
        if a.cmd == "check":
            run_once(a, sym, C.now_ist(a.now))
            return
        stop = time.time() + a.max_minutes * 60
        while time.time() < stop:
            r = run_once(a, sym, C.now_ist(a.now))
            if r["status"] in ("triggered", "expired", "not open") or a.now:
                return
            time.sleep(max(5, a.every))
    except C.SourceError as e:
        sys.exit("source failed: %s" % e)


if __name__ == "__main__":
    main()
