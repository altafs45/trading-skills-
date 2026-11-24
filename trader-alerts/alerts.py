#!/usr/bin/env python3
"""Price Alerts (NSE). Each alert rings once per day.

  python3 trader-alerts/alerts.py clock
  python3 trader-alerts/alerts.py quote TCS INFY
  python3 trader-alerts/alerts.py add --from-plan
  python3 trader-alerts/alerts.py add --symbol TCS --above 4200 | --below 4000 | --pct-up 3 | --pct-down 3 | --at 15:10 | --opening-bell
  python3 trader-alerts/alerts.py check [--now "..."]
  python3 trader-alerts/alerts.py list | reset
Quotes: Kite when logged in, else NSE (delayed). Writes trader/prices.json.
"""

import argparse, datetime as dt, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402

NO_QUOTE = {"time", "opening_bell"}


def rules_from_plan(plan):
    s = plan["symbol"]
    return [{"type": "stop", "symbol": s, "level": plan["stop"], "note": "stop"},
            {"type": "target", "symbol": s, "level": plan["target"], "note": "target"},
            {"type": "time", "symbol": s, "at": plan.get("flat_by") or "15:10", "note": "flat by close: square off %s" % s}]


def evaluate(rules, quotes, now, rang):
    """-> list of (rule, message). Marks rang[id] = today so each rings once a day."""
    today, out = now.date().isoformat(), []
    st = C.market_status(now)
    for r in rules:
        rid = r["id"]
        if rang.get(rid) == today:
            continue
        t, q = r["type"], quotes.get(r.get("symbol"))
        msg = None
        if t == "opening_bell":
            if st["state"] == "open":
                msg = "NSE is open (09:15 IST)"
        elif t == "time":
            if C.is_trading_day(now.date()) and now.time() >= C.hhmm(r["at"]):
                msg = "%s IST: %s" % (r["at"], r.get("note") or "time alert")
        elif st["state"] != "open":
            continue  # price alerts never ring on a stale quote outside the session
        elif q and q.get("ltp") is not None:
            p, lv = q["ltp"], r.get("level")
            if t in ("above", "target") and p >= lv:
                msg = "%s %.2f >= %.2f (%s)" % (r["symbol"], p, lv, r.get("note") or t)
            elif t in ("below", "stop") and p <= lv:
                msg = "%s %.2f <= %.2f (%s)" % (r["symbol"], p, lv, r.get("note") or t)
            elif t in ("pct_up", "pct_down") and q.get("prev_close"):
                ch = (p / q["prev_close"] - 1) * 100
                if (t == "pct_up" and ch >= lv) or (t == "pct_down" and ch <= -lv):
                    msg = "%s %+.2f%% vs prev close" % (r["symbol"], ch)
        if msg:
            rang[rid] = today
            out.append((r, msg))
    return out


def load():
    return C.read_json(C.path("alerts.json"), {"rules": [], "rang": {}}) or {"rules": [], "rang": {}}


def save(doc):
    C.write_json(C.path("alerts.json"), doc)


def add(doc, rule):
    rule["id"] = "%s:%s:%s" % (rule["type"], rule.get("symbol") or "-", rule.get("level", rule.get("at", "")))
    if all(r["id"] != rule["id"] for r in doc["rules"]):
        doc["rules"].append(rule)
    return rule


def fetch(syms, now):
    import nse_research as R
    errs = []
    try:
        uni = C.load_universe(None)
    except C.SourceError:
        uni = {}
    q, src = R.live_quotes(C.NSEWeb(), syms, uni, now, errs)
    C.write_json(C.path("prices.json"), {"fetched_at": C.iso(now), "source": src,
                                         "prices": {s: {"price": v["ltp"], "time": v.get("updated") or v.get("fetched_at")} for s, v in q.items()}})
    return q, src, errs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("clock").add_argument("--now")
    sp.add_parser("quote").add_argument("symbols", nargs="+")
    ad = sp.add_parser("add")
    ad.add_argument("--from-plan", action="store_true")
    ad.add_argument("--symbol")
    for k in ("--above", "--below", "--pct-up", "--pct-down"):
        ad.add_argument(k, type=float)
    ad.add_argument("--at")
    ad.add_argument("--opening-bell", action="store_true")
    ad.add_argument("--note")
    sp.add_parser("check").add_argument("--now")
    sp.add_parser("list")
    sp.add_parser("reset")
    a = ap.parse_args(argv)
    doc = load()
    if a.cmd == "clock":
        now = C.now_ist(a.now)
        st = C.market_status(now)
        d = now.date() + dt.timedelta(days=1)
        while not C.is_trading_day(d):
            d += dt.timedelta(days=1)
        nxt = now.date() if st["state"] in ("before pre-open", "pre-open") else d
        print("%s IST: market %s (%s). Session 09:15-15:30; next open %s 09:15." % (now.strftime("%a %d-%b %H:%M"), st["state"], st["why"], nxt))
    elif a.cmd == "quote":
        q, src, errs = fetch([s.upper() for s in a.symbols], C.now_ist())
        for s, v in q.items():
            print("%-12s %s  %+.2f%%  (%s, %s)" % (s, C.inr(v["ltp"]), C.pct(v["ltp"], v.get("prev_close")) or 0, src, v.get("updated") or v.get("fetched_at")))
        for e in errs:
            print("source failed: " + e)
    elif a.cmd == "add":
        new = []
        if a.from_plan:
            plan = C.read_json(C.path("plan.json"))
            if not plan:
                sys.exit("No plan.json: run trader-exit first.")
            new = rules_from_plan(plan)
        sym = (a.symbol or "").upper() or None
        for k, t in (("above", "above"), ("below", "below"), ("pct_up", "pct_up"), ("pct_down", "pct_down")):
            if getattr(a, k) is not None:
                if not sym:
                    sys.exit("--symbol is required")
                new.append({"type": t, "symbol": sym, "level": getattr(a, k), "note": a.note})
        if a.at:
            C.hhmm(a.at)
            new.append({"type": "time", "symbol": sym, "at": a.at, "note": a.note or "time alert"})
        if a.opening_bell:
            new.append({"type": "opening_bell"})
        for r in new:
            add(doc, r)
            print("added " + r["id"])
        save(doc)
    elif a.cmd == "check":
        now = C.now_ist(a.now)
        syms = sorted({r["symbol"] for r in doc["rules"] if r["type"] not in NO_QUOTE and r.get("symbol")})
        q, src, errs = fetch(syms, now) if syms else ({}, "-", [])
        rang = evaluate(doc["rules"], q, now, doc["rang"])
        save(doc)
        for r, m in rang:
            print("RING  " + m)
        print("%d alert(s) checked at %s IST, %d rang (quotes: %s)." % (len(doc["rules"]), now.strftime("%H:%M"), len(rang), src))
        for e in errs:
            print("source failed: " + e)
    elif a.cmd == "list":
        for r in doc["rules"]:
            print("%-40s %s" % (r["id"], "rang " + doc["rang"][r["id"]] if r["id"] in doc["rang"] else ""))
    else:
        save({"rules": [], "rang": {}})
        print("All alerts cleared.")


if __name__ == "__main__":
    main()
