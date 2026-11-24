#!/usr/bin/env python3
"""Exit Planner (NSE, long only). Stop and target before you enter, rounded to the stock's tick.

  python3 trader-exit/exit.py plan [--symbol X --entry 845.5] [--stop or-mid|or-low|pct:1.2|atr:1.5|PRICE]
                                   [--target 2R|1.5R|PRICE] [--flat-by 15:10] [--write]
  python3 trader-exit/exit.py show
Reads trader/entry.json by default; writes trader/plan.json for the Time Machine, Budget, Risk and Alerts.
"""

import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402
import indicators as I  # noqa: E402

NOTE = "A stop is a plan, not a guarantee: a gap, a circuit or a fast market can fill past it."


class PlanError(Exception):
    pass


def compute(entry, stop="or-mid", target="2R", or_high=None, or_low=None, atr=None, tick=None):
    entry = float(entry)
    s = str(stop).lower()
    if s == "or-mid":
        if or_high is None or or_low is None:
            raise PlanError("or-mid needs the opening range (run trader-entry with --setup orb, or pass --stop)")
        raw = (or_high + or_low) / 2
    elif s == "or-low":
        if or_low is None:
            raise PlanError("or-low needs the opening range")
        raw = or_low
    elif s.startswith("pct:"):
        raw = entry * (1 - float(s[4:]) / 100)
    elif s.startswith("atr:"):
        if not atr:
            raise PlanError("atr stop needs bars to measure ATR")
        raw = entry - float(s[4:]) * atr
    else:
        raw = float(s)
    st = C.round_tick(raw, tick, "down")
    if st >= entry:
        raise PlanError("stop %.2f is at or above the entry %.2f" % (st, entry))
    risk = entry - st
    tk = float(C.tick_for(entry, tick))
    if risk < max(2 * tk, entry * 0.0005):
        raise PlanError("stop %.2f is only %.2f under the entry: inside the spread (need >= %.2f)" % (st, risk, max(2 * tk, entry * 0.0005)))
    t = str(target).upper()
    raw_t = entry + float(t[:-1]) * risk if t.endswith("R") else float(t)
    tg = C.round_tick(raw_t, tick, "down")
    if tg <= entry:
        raise PlanError("target %.2f is at or below the entry %.2f" % (tg, entry))
    return {"entry": entry, "stop": st, "target": tg, "risk_per_share": round(risk, 2),
            "reward_per_share": round(tg - entry, 2), "r_multiple": round((tg - entry) / risk, 2),
            "stop_rule": stop, "target_rule": target, "tick": float(tk)}


def cmd_plan(a):
    cfg = C.load_config()
    ent = C.read_json(C.path("entry.json"), {}) or {}
    sym = (a.symbol or ent.get("symbol") or "").upper()
    entry = a.entry if a.entry is not None else ent.get("entry")
    if not sym or entry is None:
        sys.exit("Need an entry: run trader-entry first, or pass --symbol and --entry.")
    same = ent.get("symbol") == sym
    atr = None
    if str(a.stop).startswith("atr:"):
        got = C.get_bars(sym, "5m", 2, token=ent.get("token") if same else None)
        b = got["bars"][-60:]
        atr = I.atr([x[2] for x in b], [x[3] for x in b], [x[4] for x in b], 14)[-1]
    try:
        p = compute(entry, a.stop, a.target, ent.get("or_high") if same else None, ent.get("or_low") if same else None,
                    atr, ent.get("tick") if same else None)
    except (PlanError, ValueError) as e:
        sys.exit("REFUSED: %s" % e)
    p.update(symbol=sym, token=ent.get("token") if same else None, entry_time=ent.get("time") if same else None,
             date=ent.get("date") if same else C.now_ist().date().isoformat(), setup=ent.get("setup") if same else "manual",
             or_high=ent.get("or_high") if same else None, or_low=ent.get("or_low") if same else None,
             flat_by=a.flat_by or cfg.get("flat_by") or "15:10", created_at=C.iso(C.now_ist()))
    C.hhmm(p["flat_by"])
    print(describe(p))
    if a.write:
        C.write_json(C.path("plan.json"), p)
        print("-> trader/plan.json written. Next: /trader-timemachine, then /trader-budget")


def describe(p):
    return ("%s plan: entry %s, stop %s (%s), target %s (%s = %.2fR). Risk %s/share, flat by %s IST.\n%s"
            % (p["symbol"], C.inr(p["entry"]), C.inr(p["stop"]), p["stop_rule"], C.inr(p["target"]), p["target_rule"],
               p["r_multiple"], C.inr(p["risk_per_share"]), p["flat_by"], NOTE))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("plan")
    p.add_argument("--symbol")
    p.add_argument("--entry", type=float)
    p.add_argument("--stop", default="or-mid")
    p.add_argument("--target", default="2R")
    p.add_argument("--flat-by")
    p.add_argument("--write", action="store_true")
    sp.add_parser("show")
    a = ap.parse_args(argv)
    if a.cmd == "show":
        p = C.read_json(C.path("plan.json"))
        print(describe(p) if p else "No plan yet.")
        return
    cmd_plan(a)


if __name__ == "__main__":
    main()
