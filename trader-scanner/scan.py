#!/usr/bin/env python3
"""Chart Scanner (NSE). universe | eod | daily | intraday. Summaries to stdout, full data to trader/watchlist.json.

  python3 trader-scanner/scan.py universe [--refresh]
  python3 trader-scanner/scan.py eod [--sessions 260]
  python3 trader-scanner/scan.py daily [--top 30] [--min-price 20] [--min-turnover-cr 5] [--include-be-sm]
  python3 trader-scanner/scan.py intraday [--top 15]
"""

import argparse, datetime as dt, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402
import breakout as B  # noqa: E402


def cfg_from(a):
    cfg = dict(B.DEFAULTS)
    cfg.update({k: v for k, v in (C.load_config().get("scanner") or {}).items() if k in cfg})
    for k in ("min_price", "min_turnover_cr", "base_days", "base_max_pct", "vol_mult"):
        if getattr(a, k, None) is not None:
            cfg[k] = getattr(a, k)
    if getattr(a, "include_be_sm", False):
        cfg["include_be_sm"] = True
    return cfg


def scan_store(series, meta, cfg, min_sessions=21):
    """-> (ranked rows, filtered counts). Pure: series from C.eod_load, meta = universe symbols."""
    rows, skipped = [], {}
    for sym, s in series.items():
        if sym not in meta:
            skipped["not in universe"] = skipped.get("not in universe", 0) + 1
            continue
        if len(s["c"]) < min_sessions:
            skipped["history < %d sessions" % min_sessions] = skipped.get("history < %d sessions" % min_sessions, 0) + 1
            continue
        why = B.liquid(s, cfg, meta[sym])
        if why:
            key = why.split(" ")[0] if not why.startswith("turnover") else "turnover"
            skipped[key] = skipped.get(key, 0) + 1
            continue
        r = B.score(s, None, cfg)
        if r:
            r.update(symbol=sym, date=s["d"][-1], name=meta[sym].get("name"), token=meta[sym].get("token"),
                     tick=meta[sym].get("tick"), turnover_cr=round((s["t"][-1] or 0) / 100, 2),
                     prev_high=s["h"][-1], avg_vol20=s["av20"][-1], sessions=len(s["c"]))
            rows.append(r)
    rows.sort(key=lambda r: (-r["score"], -(r["rvol"] or 0)))
    return rows, skipped


def line(r):
    rv = "%.1fx" % r["rvol"] if r.get("rvol") else "n/a"
    return "%-12s %-26s %3d  lvl %-9.2f +%-5.2f%%  RVOL %s" % (r["symbol"], r["setup_name"], r["score"], r["level"], r["pct_above"], rv)


def cmd_universe(a):
    web = C.NSEWeb()
    doc = C.load_universe(web, refresh=a.refresh)
    syms = doc["symbols"].values()
    by = {}
    for s in syms:
        by[s["series"]] = by.get(s["series"], 0) + 1
    print("Universe %s (built %s): %d symbols  %s" % (doc["session"], doc["built_at"][:16], doc["count"],
                                                     "  ".join("%s %d" % kv for kv in sorted(by.items()))))
    print("  with Kite token: %d   F&O stocks: %d   ETFs flagged: %d" % (
        sum(1 for s in syms if s.get("token")), sum(1 for s in syms if s.get("fo")), sum(1 for s in syms if s.get("etf"))))
    for e in doc.get("errors") or []:
        print("  source failed: " + e)


def cmd_eod(a):
    web = C.NSEWeb()
    r = C.eod_update(web, a.sessions)
    print("EOD store: %d sessions through %s (+%d new)" % (r["have"], r["through"], len(r["added"])))
    for m in r["missing"][:10]:
        print("  missing: " + m)


def cmd_daily(a):
    cfg = cfg_from(a)
    web = C.NSEWeb()
    uni = C.load_universe(web)
    dates, series, _ = C.eod_load(C.KEEP)
    if not dates:
        sys.exit("No EOD data yet. Run: python3 trader-scanner/scan.py eod")
    rows, skipped = scan_store(series, uni["symbols"], cfg)
    top = rows[:a.top]
    doc = {"generated_at": C.iso(C.now_ist()), "session": dates[-1], "sessions_in_store": len(dates),
           "source": "NSE bhavcopy (sec_bhavdata_full), %d sessions" % len(dates), "filters": cfg,
           "count": len(rows), "skipped": skipped, "stocks": rows[:max(a.top, 100)]}
    C.write_json(C.path("watchlist.json"), doc)
    print("Daily scan %s (%d sessions in store): %d setups, top %d. Full list: trader/watchlist.json" % (
        dates[-1], len(dates), len(rows), len(top)))
    if len(dates) < 250:
        print("  note: only %d sessions stored; 52-week and EMA200 rules need ~250 (run scan.py eod)." % len(dates))
    for r in top:
        print("  " + line(r))
    print(C.NOTE_NFA)


def cmd_intraday(a):
    doc = C.read_json(C.path("watchlist.json"))
    if not doc or not doc.get("stocks"):
        sys.exit("No watchlist. Run: python3 trader-scanner/scan.py daily")
    now = C.now_ist()
    st = C.market_status(now)
    if st["state"] != "open":
        print("Market %s (%s); intraday rules use the latest session's bars." % (st["state"], st["why"]))
    errors = []
    t0 = dt.datetime.combine(now.date(), C.OPEN, C.IST)
    frac = min(1.0, max(0.01, (now - t0).total_seconds() / (375 * 60)))
    out = []
    for r in doc["stocks"][:a.top]:
        try:
            got = C.get_bars(r["symbol"], "5m", 2, now, token=r.get("token"))
        except C.SourceError as e:
            errors.append(str(e))
            continue
        days = C.days_in(got["bars"])
        if not days:
            continue
        bars = [b for b in got["bars"] if b[0][:10] == days[-1]]
        f = frac if days[-1] == now.date().isoformat() and st["state"] == "open" else 1.0
        x = B.intraday(bars, r.get("prev_high"), r.get("avg_vol20"), cfg_from(a)["or_minutes"], f)
        x.update(source=got["source"], fetched_at=got["fetched_at"], session=days[-1])
        r["intraday"] = x
        out.append(r)
    C.write_json(C.path("watchlist.json"), doc)
    print("Intraday check %s IST on %d shortlisted (bars: %s):" % (now.strftime("%H:%M"), len(out), out[0]["intraday"]["source"] if out else "n/a"))
    for r in out:
        x = r["intraday"]
        flags = [k for k in ("orb", "vwap_reclaim", "pdh_break") if x.get(k)]
        print("  %-12s last %-9.2f ORH %-9.2f VWAP %-9.2f %s RVOL %s  %s" % (
            r["symbol"], x["last"], x["or_high"], x["vwap"], "above" if x["above_vwap"] else "below",
            x.get("rvol", "n/a"), ", ".join(flags) or "no trigger"))
    for e in errors:
        print("  source failed: " + e)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    u = sp.add_parser("universe")
    u.add_argument("--refresh", action="store_true")
    e = sp.add_parser("eod")
    e.add_argument("--sessions", type=int, default=C.KEEP)
    d = sp.add_parser("daily")
    d.add_argument("--top", type=int, default=30)
    for k, t in (("--min-price", float), ("--min-turnover-cr", float), ("--base-days", int), ("--base-max-pct", float), ("--vol-mult", float)):
        d.add_argument(k, type=t)
    d.add_argument("--include-be-sm", action="store_true")
    i = sp.add_parser("intraday")
    i.add_argument("--top", type=int, default=15)
    a = ap.parse_args(argv)
    try:
        {"universe": cmd_universe, "eod": cmd_eod, "daily": cmd_daily, "intraday": cmd_intraday}[a.cmd](a)
    except C.SourceError as e:
        sys.exit("source failed: %s" % e)


if __name__ == "__main__":
    main()
