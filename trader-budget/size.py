#!/usr/bin/env python3
"""Budget Manager (NSE). Whole shares that fit four limits; writes ONE order ticket to trader/orders.json.

  python3 trader-budget/size.py [--capital 100000] [--max-loss 500] [--price 846.2] [--cash 80000] [--write]
Limits from trader/config.json: max_loss_per_trade, max_position_pct, max_order_value, cash_buffer_pct, mis_leverage.
Nothing is placed: the ticket is for you to place yourself.
"""

import argparse, hashlib, json, math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402

DEFAULTS = {"capital": 100000.0, "max_loss_per_trade": 500.0, "max_position_pct": 25.0, "max_order_value": 50000.0,
            "cash_buffer_pct": 10.0, "mis_leverage": 1.0, "product": "MIS"}


class SizeError(Exception):
    pass


def fingerprint(o):
    keys = ("symbol", "side", "qty", "entry", "stop", "target", "product")
    return hashlib.sha1(json.dumps([o.get(k) for k in keys]).encode()).hexdigest()[:12]


def size_trade(plan, cfg, price=None, cash=None):
    c = dict(DEFAULTS)
    c.update({k: v for k, v in cfg.items() if k in DEFAULTS and v is not None})
    entry, stop = float(plan["entry"]), float(plan["stop"])
    ref = max(entry, float(price)) if price else entry
    risk = ref - stop
    if risk <= 0:
        raise SizeError("the price %.2f is already at or below the stop %.2f" % (ref, stop))
    lev = max(1.0, float(c["mis_leverage"])) if c["product"] == "MIS" else 1.0
    cash = float(cash if cash is not None else c["capital"])
    limits = {
        "max loss per trade": math.floor(c["max_loss_per_trade"] / risk + 1e-9),
        "position cap": math.floor(c["capital"] * c["max_position_pct"] / 100 * lev / ref + 1e-9),
        "max order": math.floor(c["max_order_value"] / ref + 1e-9),
        "cash after buffer": math.floor(cash * (1 - c["cash_buffer_pct"] / 100) * lev / ref + 1e-9),
    }
    if limits["max loss per trade"] < 1:
        raise SizeError("one share risks %s, more than your max loss %s: the stop is too far for this budget. "
                        "Not sizing smaller." % (C.inr(risk), C.inr(c["max_loss_per_trade"])))
    decider = min(limits, key=lambda k: (limits[k], list(limits).index(k)))
    qty = limits[decider]
    if qty < 1:
        raise SizeError("%s allows 0 shares at %s" % (decider, C.inr(ref)))
    return {"qty": qty, "decided_by": decider, "limits": limits, "ref_price": ref, "risk_per_share": round(risk, 2),
            "max_loss": round(qty * risk, 2), "value": round(qty * ref, 2), "margin_needed": round(qty * ref / lev, 2),
            "product": c["product"], "leverage": lev}


def ticket(plan, s, now):
    o = {"symbol": plan["symbol"], "token": plan.get("token"), "exchange": "NSE", "side": "BUY", "qty": s["qty"],
         "product": s["product"], "order_type": "LIMIT", "entry": plan["entry"], "stop": plan["stop"], "target": plan["target"],
         "max_loss": s["max_loss"], "value": s["value"], "flat_by": plan.get("flat_by"), "decided_by": s["decided_by"],
         "created_at": C.iso(now), "date": now.date().isoformat()}
    o["id"] = fingerprint(o)
    return o


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capital", type=float)
    ap.add_argument("--max-loss", type=float)
    ap.add_argument("--price", type=float, help="a fresh price; risk is measured from the higher of this and the entry")
    ap.add_argument("--cash", type=float)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    plan = C.read_json(C.path("plan.json"))
    if not plan:
        sys.exit("No plan: run trader-exit plan --write first.")
    cfg = C.load_config()
    if a.capital:
        cfg["capital"] = a.capital
    if a.max_loss:
        cfg["max_loss_per_trade"] = a.max_loss
    try:
        s = size_trade(plan, cfg, a.price, a.cash)
    except SizeError as e:
        sys.exit("REFUSED: %s" % e)
    now = C.now_ist()
    o = ticket(plan, s, now)
    print("%s: %d shares at %s = %s (%s, margin %s). Decided by: %s." % (
        o["symbol"], o["qty"], C.inr(s["ref_price"]), C.inr(o["value"]), o["product"], C.inr(s["margin_needed"]), s["decided_by"]))
    print("  limits: " + ", ".join("%s %d" % kv for kv in s["limits"].items()))
    print("  loss if the stop fills at %s: %s. Target %s. Flat by %s." % (C.inr(o["stop"]), C.inr(o["max_loss"]), C.inr(o["target"]), o["flat_by"]))
    if a.write:
        C.write_json(C.path("orders.json"), {"orders": [o]})
        print("  -> trader/orders.json (1 ticket). Next: /trader-risk. Nothing has been placed.")


if __name__ == "__main__":
    main()
