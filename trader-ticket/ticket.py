#!/usr/bin/env python3
"""Order Ticket (NSE). Turns tickets that passed trader-risk into plain instructions YOU place in your broker app.
This script never calls a broker: it cannot place, modify or cancel an order.

  python3 trader-ticket/ticket.py show
  python3 trader-ticket/ticket.py confirm --reply "yes buy 8 CHALET"   # records your yes, word for word
  python3 trader-ticket/ticket.py fill CHALET --side BUY --qty 8 --price 846.5
  python3 trader-ticket/ticket.py close CHALET                          # the exit ticket (never blocked)
  python3 trader-ticket/ticket.py log
"""

import argparse, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402

DOUBT = {"no", "not", "dont", "don't", "wait", "cancel", "stop", "but", "maybe", "later", "hold", "?"}


def parse_yes(reply, o):
    """A yes counts only if it says yes, names the symbol and the exact quantity, and has no doubt words."""
    words = re.findall(r"[a-z0-9'?]+|\?", reply.lower())
    if not words or words[0] not in ("yes", "y"):
        return False, "reply must start with yes"
    if any(w in DOUBT for w in words):
        return False, "reply has a doubt word; ask again"
    if o["symbol"].lower() not in words:
        return False, "say the symbol (%s)" % o["symbol"]
    if str(o["qty"]) not in words:
        return False, "say the exact quantity (%d)" % o["qty"]
    return True, "ok"


def verdict_for(o, risk, today):
    vs = [v for v in risk.get("verdicts", []) if v.get("id") == o.get("id") and v.get("date") == today]
    return vs[-1] if vs else None


def plain(o):
    return ("BUY %d %s on NSE, product %s, LIMIT %s.\n"
            "    Then protect it: SL-M SELL %d trigger %s, and LIMIT SELL %d at %s (or one GTT/OCO with both).\n"
            "    Max loss at the stop %s. Square off by %s IST." % (
                o["qty"], o["symbol"], o.get("product", "MIS"), C.inr(o["entry"]), o["qty"], C.inr(o["stop"]),
                o["qty"], C.inr(o["target"]), C.inr(o["max_loss"]), o.get("flat_by") or "15:10"))


def load():
    return ((C.read_json(C.path("orders.json"), {}) or {}).get("orders") or [], C.read_json(C.path("risk.json"), {}) or {},
            C.read_json(C.path("tickets.json"), {"confirmations": []}) or {"confirmations": []})


def cmd_show(a, now):
    orders, risk, _ = load()
    today = now.date().isoformat()
    if not orders:
        print("No tickets. Run /trader-budget, then /trader-risk.")
    for i, o in enumerate(orders, 1):
        v = verdict_for(o, risk, today)
        state = "READY" if v and v["verdict"] == "PASS" else "NOT READY (%s)" % ("blocked: " + "; ".join(v["reasons"]) if v else "not risk-checked today")
        print("Ticket %d [%s] %s\n    %s" % (i, o.get("id"), state, plain(o)))
    print("You place orders yourself in your broker app. This pack never sends one.")


def cmd_confirm(a, now):
    orders, risk, t = load()
    if not orders:
        sys.exit("No tickets.")
    o = orders[a.index - 1]
    v = verdict_for(o, risk, now.date().isoformat())
    if not v or v["verdict"] != "PASS":
        sys.exit("NOT READY: ticket %d has no PASS from trader-risk today." % a.index)
    ok, why = parse_yes(a.reply, o)
    if not ok:
        sys.exit("Not recorded: " + why)
    t["confirmations"].append({"id": o["id"], "at": C.iso(now), "reply": a.reply, "symbol": o["symbol"], "qty": o["qty"]})
    C.write_json(C.path("tickets.json"), t)
    print("Recorded your yes for ticket %d. Now place it yourself:\n    %s" % (a.index, plain(o)))


def apply_fill(j, sym, side, qty, price, now):
    pos = j.setdefault("positions", {})
    p = pos.get(sym, {"qty": 0, "avg": 0.0})
    pnl = None
    if side == "BUY":
        tot = p["qty"] + qty
        p = {"qty": tot, "avg": round((p["qty"] * p["avg"] + qty * price) / tot, 4)}
    else:
        if qty > p["qty"]:
            raise ValueError("selling %d but only %d held (no short selling)" % (qty, p["qty"]))
        pnl = round((price - p["avg"]) * qty, 2)
        p = {"qty": p["qty"] - qty, "avg": p["avg"] if p["qty"] - qty else 0.0}
    if p["qty"]:
        pos[sym] = p
    else:
        pos.pop(sym, None)
    j.setdefault("fills", []).append({"date": now.date().isoformat(), "at": C.iso(now), "symbol": sym, "side": side,
                                      "qty": qty, "price": price, "pnl": pnl})
    return pnl


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("show")
    c = sp.add_parser("confirm")
    c.add_argument("--index", type=int, default=1)
    c.add_argument("--reply", required=True)
    f = sp.add_parser("fill")
    f.add_argument("symbol")
    f.add_argument("--side", choices=("BUY", "SELL"), required=True)
    f.add_argument("--qty", type=int, required=True)
    f.add_argument("--price", type=float, required=True)
    cl = sp.add_parser("close")
    cl.add_argument("symbol")
    sp.add_parser("log")
    for p in sp.choices.values():
        p.add_argument("--now")
    a = ap.parse_args(argv)
    now = C.now_ist(a.now)
    if a.cmd == "show":
        return cmd_show(a, now)
    if a.cmd == "confirm":
        return cmd_confirm(a, now)
    j = C.read_json(C.path("journal.json"), {}) or {}
    if a.cmd == "fill":
        try:
            pnl = apply_fill(j, a.symbol.upper(), a.side, a.qty, a.price, now)
        except ValueError as e:
            sys.exit(str(e))
        C.write_json(C.path("journal.json"), j)
        print("Logged %s %d %s @ %s%s." % (a.side, a.qty, a.symbol.upper(), C.inr(a.price), "" if pnl is None else ", P&L " + C.inr(pnl)))
    elif a.cmd == "close":
        p = (j.get("positions") or {}).get(a.symbol.upper())
        if not p:
            sys.exit("No open position in %s in the journal." % a.symbol.upper())
        print("EXIT ticket (never blocked): SELL %d %s on NSE at MARKET (or LIMIT near the bid), same product.\n"
              "    Cancel the open stop and target orders for it first. Entry avg %s." % (p["qty"], a.symbol.upper(), C.inr(p["avg"])))
    else:
        today = now.date().isoformat()
        fills = [x for x in j.get("fills", []) if x["date"] == today]
        for x in fills:
            print("%s %s %d %s @ %s%s" % (x["at"][11:16], x["side"], x["qty"], x["symbol"], C.inr(x["price"]), "" if x["pnl"] is None else "  P&L " + C.inr(x["pnl"])))
        print("Today: %d fills, realized %s. Open: %s" % (len(fills), C.inr(sum(x["pnl"] or 0 for x in fills)),
                                                       ", ".join("%s %d" % (k, v["qty"]) for k, v in (j.get("positions") or {}).items()) or "none"))


if __name__ == "__main__":
    main()
