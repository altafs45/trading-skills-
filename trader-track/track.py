#!/usr/bin/env python3
"""Track Mode (NSE). Live structure for a watchlist; prints only what changed; alerts ring once.

  python3 trader-track/track.py [--symbols A,B] [--top 8] [--every 15] [--loops 0] [--once]
Loop: quotes (Kite when logged in, else NSE) -> local 1m bars (LTP + volume deltas, re-seeded from candles every 5 min) -> structure -> changes.
Structure: trend (swing HH/HL), swing support/resistance, pivots, VWAP, ORB, distance to the breakout level,
breakout confirmed/failed (5m close back below), circuit proximity. Alerts: breakout, failure, volume spike,
near circuit, stop, target. State: trader/track.json. Never places an order.
"""

import argparse, datetime as dt, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402
import indicators as I  # noqa: E402

RESEED = 300


def bucket(t, minutes=1):
    m = t.hour * 60 + t.minute - (9 * 60 + 15)
    m = (m // minutes) * minutes + 9 * 60 + 15
    return t.replace(hour=m // 60, minute=m % 60, second=0, microsecond=0).isoformat()


class BarBuilder(object):
    """1-minute bars from polled LTP and cumulative volume (deltas between polls)."""

    def __init__(self):
        self.bars, self.last_vol = [], None

    def seed(self, bars):
        self.bars = [list(b) for b in bars]

    def update(self, t, ltp, cum_vol):
        dv = 0 if self.last_vol is None or cum_vol is None else max(0, cum_vol - self.last_vol)
        if cum_vol is not None:
            self.last_vol = cum_vol
        k = bucket(t)
        if self.bars and self.bars[-1][0] == k:
            b = self.bars[-1]
            b[2], b[3], b[4], b[5] = max(b[2], ltp), min(b[3], ltp), ltp, b[5] + dv
        elif not self.bars or k > self.bars[-1][0]:
            self.bars.append([k, ltp, ltp, ltp, ltp, dv])


def aggregate(bars, minutes=5):
    out = []
    for b in bars:
        k = bucket(C.parse_iso(b[0]), minutes)
        if out and out[-1][0] == k:
            o = out[-1]
            o[2], o[3], o[4], o[5] = max(o[2], b[2]), min(o[3], b[3]), b[4], o[5] + b[5]
        else:
            out.append([k] + list(b[1:]))
    return out


def completed(bars, now, minutes):
    return [b for b in bars if C.parse_iso(b[0]) + dt.timedelta(minutes=minutes) <= now]


def structure(b1, now, ltp, level=None, prev_day=None, quote=None, cfg=None):
    cfg = cfg or {}
    b5 = completed(aggregate(b1, 5), now, 5)
    c1 = completed(b1, now, 1)
    s = {"ltp": ltp, "time": now.strftime("%H:%M")}
    if b5:
        h, l = [b[2] for b in b5], [b[3] for b in b5]
        s["trend"] = I.structure(h, l, 2)[0]
        s["support"], s["resistance"] = I.support_resistance(h, l, ltp, 2)
        if len(b5) >= 3:
            orh, orl = max(h[:3]), min(l[:3])
            last = b5[-1][4]
            s["or_high"], s["or_low"] = orh, orl
            s["orb"] = "above" if last > orh and len(b5) > 3 else "below" if last < orl and len(b5) > 3 else "inside" if len(b5) > 3 else "forming"
        else:
            s["orb"] = "forming"
    if b1:
        s["vwap"] = round(I.vwap(b1)[-1], 2)
        s["above_vwap"] = ltp > s["vwap"]
    if prev_day:
        s["pivots"] = {k: round(v, 2) for k, v in I.pivots(*prev_day).items()}
    if level:
        s["level"] = level
        s["dist_pct"] = round((ltp / level - 1) * 100, 2)
        i = next((k for k, b in enumerate(b5) if b[4] > level), None)
        s["breakout"] = "none" if i is None else "confirmed" if b5[-1][4] > level else "failed"
    if quote and quote.get("band_high"):
        s["to_upper_circuit_pct"] = round((quote["band_high"] / ltp - 1) * 100, 2)
        s["to_lower_circuit_pct"] = round((1 - quote["band_low"] / ltp) * 100, 2) if quote.get("band_low") else None
    if len(c1) >= 11:
        avg = sum(b[5] for b in c1[:-1]) / (len(c1) - 1)
        s["vol_spike"] = c1[-1][5] >= cfg.get("vol_spike_mult", 3.0) * avg and avg > 0
        s["vol_spike_bar"] = c1[-1][0][11:16]
    return s


def events(prev, cur, plan=None, cfg=None):
    """-> [(key, message)]. key makes each alert ring once (per day, per bar for volume)."""
    cfg, out = cfg or {}, []
    if cur.get("breakout") == "confirmed" and (prev or {}).get("breakout") != "confirmed":
        out.append(("breakout", "BREAKOUT confirmed: 5m close above %.2f" % cur["level"]))
    if cur.get("breakout") == "failed":
        out.append(("failed", "BREAKOUT FAILED: 5m close back below %.2f" % cur["level"]))
    if cur.get("vol_spike"):
        out.append(("volspike:" + cur["vol_spike_bar"], "VOLUME SPIKE in the %s minute" % cur["vol_spike_bar"]))
    up = cur.get("to_upper_circuit_pct")
    if up is not None and up <= cfg.get("near_circuit_pct", 2.0):
        out.append(("circuit_up", "NEAR UPPER CIRCUIT: %.2f%% away" % up))
    lo = cur.get("to_lower_circuit_pct")
    if lo is not None and lo <= cfg.get("near_circuit_pct", 2.0):
        out.append(("circuit_dn", "NEAR LOWER CIRCUIT: %.2f%% away" % lo))
    if plan:
        if cur["ltp"] <= plan["stop"]:
            out.append(("stop", "STOP HIT: %.2f <= %.2f" % (cur["ltp"], plan["stop"])))
        elif cur["ltp"] >= plan["target"]:
            out.append(("target", "TARGET HIT: %.2f >= %.2f" % (cur["ltp"], plan["target"])))
    return out


def summary(s):
    r = lambda x: None if x is None else round(x, 1)
    return [s.get("trend"), s.get("orb"), s.get("breakout"), s.get("above_vwap"), r(s.get("support")), r(s.get("resistance"))]


def render(sym, s, changed):
    parts = ["%s %.2f" % (sym, s["ltp"]), "trend %s" % s.get("trend", "?"), "ORB %s" % s.get("orb", "?")]
    if "vwap" in s:
        parts.append("%s VWAP %.2f" % ("above" if s["above_vwap"] else "below", s["vwap"]))
    if s.get("level"):
        parts.append("lvl %.2f (%+.2f%%, %s)" % (s["level"], s["dist_pct"], s["breakout"]))
    parts.append("S %s / R %s" % (s.get("support") or "-", s.get("resistance") or "-"))
    if s.get("to_upper_circuit_pct") is not None:
        parts.append("UC %.1f%% away" % s["to_upper_circuit_pct"])
    return "%s  %s  [%s]" % (s["time"], " | ".join(parts), ", ".join(changed))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--every", type=int)
    ap.add_argument("--loops", type=int, default=0, help="0 = until 15:30")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    import nse_research as R
    cfg = C.load_config()
    every = max(5, a.every or cfg.get("poll_seconds") or 15)
    wl = C.read_json(C.path("watchlist.json"), {}) or {}
    levels = {r["symbol"]: r["level"] for r in wl.get("stocks") or []}
    syms = [s.strip().upper() for s in a.symbols.split(",")] if a.symbols else [r["symbol"] for r in (wl.get("stocks") or [])[:a.top]]
    if not syms:
        sys.exit("No symbols: pass --symbols or run trader-scanner first.")
    plan = C.read_json(C.path("plan.json")) or {}
    if plan.get("symbol"):
        levels.setdefault(plan["symbol"], plan["entry"])
    try:
        uni = C.load_universe(None)
    except C.SourceError:
        uni = {"symbols": {}}
    web, state = C.NSEWeb(), C.read_json(C.path("track.json"), {}) or {}
    rang, last = state.setdefault("rang", {}), state.setdefault("last", {})
    builders, seeded, prevday = {s: BarBuilder() for s in syms}, 0.0, {}
    loop = 0
    while True:
        now = C.now_ist()
        st = C.market_status(now)
        errs = []
        if time.time() - seeded > RESEED:
            for s in syms:
                tok = (uni["symbols"].get(s) or {}).get("token")
                try:
                    got = C.get_bars(s, "1m", 2, now, token=tok)
                    day = C.days_in(got["bars"])[-1:] or [now.date().isoformat()]
                    builders[s].seed([b for b in got["bars"] if b[0][:10] == day[0]])
                    d = C.get_bars(s, "1d", 10, now, token=tok)["bars"]
                    prior = [b for b in d if b[0][:10] < day[0]]
                    if prior:
                        prevday[s] = (prior[-1][2], prior[-1][3], prior[-1][4])
                except (C.SourceError, IndexError) as e:
                    errs.append(str(e))
            seeded = time.time()
        quotes, src = R.live_quotes(web, syms, uni, now, errs)
        live = st["state"] == "open"
        for s in syms:
            q = quotes.get(s)
            b = builders[s]
            if q and q.get("ltp") and live:
                b.update(now, q["ltp"], q.get("volume"))
            ltp = (q or {}).get("ltp") or (b.bars[-1][4] if b.bars else None)
            if not ltp:
                continue
            ref = now if live else C.parse_iso(b.bars[-1][0]) + dt.timedelta(minutes=1) if b.bars else now
            cur = structure(b.bars, ref, ltp, levels.get(s), prevday.get(s), q, cfg)
            prev = last.get(s)
            changed = [k for k, x, y in zip(("trend", "orb", "breakout", "vwap", "support", "resistance"), summary(cur), (prev or {}).get("sum") or [None] * 6) if x != y]
            if changed or not prev:
                print(render(s, cur, changed or ["first look"]))
            for key, msg in (events(prev and prev.get("s"), cur, plan if plan.get("symbol") == s else None, cfg) if live else []):
                k = "%s:%s:%s" % (now.date(), s, key)
                if k not in rang:
                    rang[k] = C.iso(now)
                    print("  RING %s %s" % (s, msg))
            last[s] = {"sum": summary(cur), "s": cur}
        for e in errs:
            print("  source failed: " + e)
        state["updated"], state["source"] = C.iso(now), src
        state["rang"] = {k: v for k, v in rang.items() if k[:10] >= (now.date() - dt.timedelta(days=3)).isoformat()}
        C.write_json(C.path("track.json"), state)
        loop += 1
        if a.once or not live or (a.loops and loop >= a.loops) or now.time() >= C.CLOSE:
            if not live and loop == 1:
                print("Market %s (%s): snapshot from the latest session; no live loop. %s" % (st["state"], st["why"], C.NOTE_NFA))
            return
        time.sleep(every)


if __name__ == "__main__":
    main()
