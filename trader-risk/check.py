#!/usr/bin/env python3
"""Risk Manager (NSE). PASS or BLOCK for every ticket in trader/orders.json, with the reasons.

  python3 trader-risk/check.py [--now "2026-11-25 10:20"] [--offline]
--offline skips the live checks (event day, circuit band, fresh price) and says so.
Exits never get blocked by a day limit. Verdicts go to trader/risk.json for trader-ticket.
"""

import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402

DEFAULTS = {"capital": 100000.0, "max_loss_per_trade": 500.0, "daily_loss_limit": 1500.0, "max_trades_per_day": 3,
            "min_reward_risk": 1.5, "entry_window": ["09:30", "14:30"], "max_order_value": 50000.0,
            "max_position_pct": 25.0, "cash_buffer_pct": 10.0, "mis_leverage": 1.0, "blocked": [],
            "near_circuit_pct": 2.0, "block_on_event_day": True, "max_orders_per_day": 10}


def config():
    c = dict(DEFAULTS)
    c.update({k: v for k, v in C.load_config().items() if k in DEFAULTS})
    return c


def day_state(journal, risk_doc, today):
    """Today's realized P&L, open risk already approved, and number of entries."""
    fills = [f for f in (journal or {}).get("fills", []) if f.get("date") == today]
    realized = sum(f.get("pnl") or 0 for f in fills)
    entries = len([f for f in fills if f["side"] == "BUY"])
    passed = [v for v in (risk_doc or {}).get("verdicts", []) if v.get("date") == today and v["verdict"] == "PASS" and v.get("side") == "BUY"]
    return {"realized": realized, "entries": entries, "approved_risk": sum(v.get("max_loss") or 0 for v in passed),
            "approved_ids": {v["id"] for v in passed}, "orders_today": len([v for v in (risk_doc or {}).get("verdicts", []) if v.get("date") == today])}


def check(o, cfg, now, day, meta=None, live=None):
    """-> (verdict, reasons, warnings). live: {'price','band_high','band_low','event_today': [...]} or None (offline)."""
    meta, bad, warn = meta or {}, [], []
    sym, side = o.get("symbol", ""), o.get("side", "").upper()
    try:
        qty, entry = int(o["qty"]), float(o.get("entry") or 0)
        stop, target = float(o.get("stop") or 0), float(o.get("target") or 0)
    except (KeyError, TypeError, ValueError):
        return "BLOCK", ["malformed ticket: qty/entry/stop/target missing or not numbers"], warn
    if qty <= 0 or side not in ("BUY", "SELL") or entry < 0:
        bad.append("malformed ticket: qty must be > 0 and side BUY or SELL")
    if side == "SELL":
        return ("BLOCK" if bad else "PASS"), bad, ["exit ticket: day limits never block getting out"]
    tick = float(C.tick_for(entry, meta.get("tick")))
    for name, p in (("entry", entry), ("stop", stop), ("target", target)):
        if p and abs(round(p / tick) * tick - p) > 1e-6:
            bad.append("%s %.2f is not a multiple of the tick %.2f" % (name, p, tick))
    if not stop:
        return "BLOCK", bad + ["a stop is required"], warn
    if stop >= entry:
        bad.append("stop %.2f is not below the entry %.2f" % (stop, entry))
    if target <= entry:
        bad.append("target %.2f is not above the entry %.2f" % (target, entry))
    ref = max(entry, (live or {}).get("price") or 0)
    risk = max(0.0, ref - stop) * qty
    if risk > cfg["max_loss_per_trade"] + 1e-6:
        bad.append("loss at the stop %s (from %.2f) is over your max loss %s" % (C.inr(risk), ref, C.inr(cfg["max_loss_per_trade"])))
    if stop < entry and target > entry and (target - entry) / (entry - stop) < cfg["min_reward_risk"] - 1e-9:
        bad.append("reward:risk %.2f is under your minimum %.2f" % ((target - entry) / (entry - stop), cfg["min_reward_risk"]))
    used = -min(0.0, day["realized"]) + day["approved_risk"]
    if used + risk > cfg["daily_loss_limit"] + 1e-6:
        bad.append("today's loss + approved risk %s + this %s is over the daily limit %s" % (C.inr(used), C.inr(risk), C.inr(cfg["daily_loss_limit"])))
    if day["entries"] >= cfg["max_trades_per_day"]:
        bad.append("already %d entries today (limit %d)" % (day["entries"], cfg["max_trades_per_day"]))
    if day["orders_today"] >= cfg["max_orders_per_day"]:
        bad.append("daily order-check limit %d reached" % cfg["max_orders_per_day"])
    st = C.market_status(now)
    if st["state"] != "open":
        bad.append("market is %s (%s): no new entries" % (st["state"], st["why"]))
    else:
        lo, hi = C.hhmm(cfg["entry_window"][0]), C.hhmm(cfg["entry_window"][1])
        if not lo <= now.time() <= hi:
            bad.append("%s is outside your entry window %s-%s IST" % (now.strftime("%H:%M"), cfg["entry_window"][0], cfg["entry_window"][1]))
    if sym in {s.upper() for s in cfg["blocked"]}:
        bad.append("%s is on your blocked list" % sym)
    lev = max(1.0, float(cfg["mis_leverage"])) if o.get("product", "MIS") == "MIS" else 1.0
    val = qty * ref
    if val > cfg["max_order_value"] + 1e-6:
        bad.append("order value %s is over max order %s" % (C.inr(val), C.inr(cfg["max_order_value"])))
    if val / lev > cfg["capital"] * cfg["max_position_pct"] / 100 + 1e-6:
        bad.append("position %s is over %.0f%% of capital" % (C.inr(val / lev), cfg["max_position_pct"]))
    if val / lev > cfg["capital"] * (1 - cfg["cash_buffer_pct"] / 100) + 1e-6:
        bad.append("needs %s, more than cash after your %.0f%% buffer" % (C.inr(val / lev), cfg["cash_buffer_pct"]))
    series = meta.get("series")
    if series and series != "EQ" and o.get("product", "MIS") == "MIS":
        bad.append("series %s is trade-for-trade: no intraday (MIS)" % series)
    if o.get("id") in day["approved_ids"]:
        bad.append("duplicate: this exact ticket already passed today")
    if live is None:
        warn.append("offline: event day, circuit band and fresh price NOT checked")
    else:
        bh = live.get("band_high")
        if bh:
            if target > bh:
                bad.append("target %.2f is above the upper circuit %.2f" % (target, bh))
            elif (bh / ref - 1) * 100 < cfg["near_circuit_pct"]:
                bad.append("price %.2f is within %.1f%% of the upper circuit %.2f" % (ref, cfg["near_circuit_pct"], bh))
        else:
            warn.append("circuit band unknown")
        if live.get("event_today"):
            msg = "event today: " + "; ".join(e["what"][:60] for e in live["event_today"][:2])
            (bad if cfg["block_on_event_day"] else warn).append(msg)
    return ("BLOCK" if bad else "PASS"), bad, warn


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--now")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    now, cfg = C.now_ist(a.now), config()
    today = now.date().isoformat()
    orders = (C.read_json(C.path("orders.json"), {}) or {}).get("orders") or []
    if not orders:
        sys.exit("No tickets: run trader-budget size.py --write first.")
    risk_doc = C.read_json(C.path("risk.json"), {}) or {}
    day = day_state(C.read_json(C.path("journal.json"), {}), risk_doc, today)
    try:
        uni = C.load_universe(None)
    except C.SourceError:
        uni = {"symbols": {}}
    web = None if a.offline else C.NSEWeb()
    verdicts = risk_doc.get("verdicts", [])
    verdicts = [v for v in verdicts if v.get("date") >= (now.date().replace(day=1)).isoformat()]
    for o in orders:
        meta = uni["symbols"].get(o.get("symbol"), {})
        live, errs = None, []
        if web:
            import nse_research as R
            q = R.quote(web, o["symbol"], now, errs, ttl=60)
            ev = R.events(web, o["symbol"], now, 1, uni, errs)
            live = {"price": q and q.get("ltp"), "band_high": q and q.get("band_high"), "event_today": ev["event_risk_today"]}
        v, bad, warn = check(o, cfg, now, day, meta, live)
        warn += ["source failed: " + e for e in errs]
        print("%s  %s %s %s x%s  entry %s stop %s target %s" % (v, o.get("side"), o.get("symbol"), o.get("product", "MIS"), o.get("qty"),
                                                                o.get("entry"), o.get("stop"), o.get("target")))
        for r in bad:
            print("   BLOCK: " + r)
        for w in warn:
            print("   note:  " + w)
        rec = {"id": o.get("id"), "date": today, "at": C.iso(now), "symbol": o.get("symbol"), "side": o.get("side"),
               "verdict": v, "reasons": bad, "warnings": warn, "max_loss": o.get("max_loss")}
        verdicts.append(rec)
        if v == "PASS" and o.get("side") == "BUY":
            day["approved_risk"] += o.get("max_loss") or 0
            day["approved_ids"].add(o.get("id"))
        day["orders_today"] += 1
    C.write_json(C.path("risk.json"), {"verdicts": verdicts})
    print("Verdicts -> trader/risk.json. Only a PASS can become a ticket (/trader-ticket).")


if __name__ == "__main__":
    main()
