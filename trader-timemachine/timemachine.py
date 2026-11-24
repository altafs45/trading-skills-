#!/usr/bin/env python3
"""Time Machine (NSE). Replays the rest of the session N times from the stock's own 5-minute candles at the
same time of day (last ~60 sessions), and re-runs the opening-range rule on every past session.

  python3 trader-timemachine/timemachine.py run [--sims 10000] [--seed 19] [--days 60] [--write]
Reads trader/plan.json. A simulation, not a prediction.
"""

import argparse, datetime as dt, os, random, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402
import indicators as I  # noqa: E402

SLOTS = 75  # 09:15 .. 15:25 five-minute candles


def slot_of(t):
    """'2026-11-23T10:05:00+05:30' -> candle index from 09:15 (0..74)."""
    h, m = int(t[11:13]), int(t[14:16])
    return ((h * 60 + m) - (9 * 60 + 15)) // 5


def sessions(bars):
    out = {}
    for b in bars:
        out.setdefault(b[0][:10], []).append(b)
    return out


def library(days):
    """Per slot: relative candles (gap vs previous close, high/low/close vs open)."""
    lib = [[] for _ in range(SLOTS)]
    for bars in days.values():
        prev = None
        for b in bars:
            s = slot_of(b[0])
            if 0 <= s < SLOTS and b[1] > 0:
                gap = (b[1] / prev - 1) if prev else 0.0
                lib[s].append((gap, b[2] / b[1] - 1, b[3] / b[1] - 1, b[4] / b[1] - 1))
            prev = b[4]
    return lib


def simulate(lib, entry, stop, target, start_slot, end_slot, sims=10000, seed=19):
    rng = random.Random(seed)
    hit_t = hit_s = 0
    closes, rs = [], []
    risk = entry - stop
    for _ in range(sims):
        p, done = entry, None
        for s in range(start_slot, end_slot):
            if not lib[s]:
                continue
            g, hr, lr, cr = rng.choice(lib[s])
            o = p * (1 + g)
            hi, lo, p = o * (1 + hr), o * (1 + lr), o * (1 + cr)
            if lo <= stop:            # both in one candle counts as the stop: the conservative read
                done = "stop"
                break
            if hi >= target:
                done = "target"
                break
        if done == "stop":
            hit_s += 1
            rs.append(-1.0)
        elif done == "target":
            hit_t += 1
            rs.append((target - entry) / risk)
        else:
            closes.append(p)
            rs.append((p - entry) / risk)
    n = float(sims)
    return {"sims": sims, "seed": seed, "target_first": round(100 * hit_t / n, 1), "stop_first": round(100 * hit_s / n, 1),
            "neither": round(100 * (sims - hit_t - hit_s) / n, 1), "avg_r": round(sum(rs) / n, 3),
            "close_p10": round(I.percentile(closes, 0.1), 2) if closes else None,
            "close_p50": round(I.percentile(closes, 0.5), 2) if closes else None,
            "close_p90": round(I.percentile(closes, 0.9), 2) if closes else None}


def history(days, risk_pct, r_mult, or_bars=3, cutoff_slot=63, flat_slot=71, skip=None):
    """The same ORB rule on every past session: entry = first 5m close above the OR high; stop/target at the plan's %."""
    out = {"fired": 0, "target": 0, "stop": 0, "neither": 0, "sessions": 0}
    for d, bars in sorted(days.items()):
        if d == skip or len(bars) < or_bars + 2:
            continue
        out["sessions"] += 1
        orh = max(b[2] for b in bars[:or_bars])
        k = next((i for i in range(or_bars, len(bars)) if slot_of(bars[i][0]) <= cutoff_slot and bars[i][4] > orh), None)
        if k is None:
            continue
        out["fired"] += 1
        e = bars[k][4]
        st, tg = e * (1 - risk_pct), e * (1 + r_mult * risk_pct)
        res = "neither"
        for b in bars[k + 1:]:
            if slot_of(b[0]) >= flat_slot:
                break
            if b[3] <= st:
                res = "stop"
                break
            if b[2] >= tg:
                res = "target"
                break
        out[res] += 1
    return out


def verdict(sim, hist):
    gap = sim["target_first"] - sim["stop_first"]
    if abs(gap) < 7:
        v = "close to a coin flip"
    elif gap > 0 and sim["avg_r"] > 0.1:
        v = "the replay leans your way, modestly"
    elif gap < 0:
        v = "the replay leans against this plan"
    else:
        v = "mixed"
    if hist["fired"] < 15:
        v += "; history is thin (%d past triggers)" % hist["fired"]
    return v


def run(plan, bars, sims=10000, seed=19):
    days = sessions(bars)
    lib = library({d: b for d, b in days.items() if d != plan.get("date")})
    start = slot_of("2000-01-01T%s:00" % (plan.get("entry_time") or "09:30")) if plan.get("entry_time") else 3
    fh, fm = map(int, plan["flat_by"].split(":"))
    end = min(SLOTS, ((fh * 60 + fm) - (9 * 60 + 15)) // 5)
    sim = simulate(lib, plan["entry"], plan["stop"], plan["target"], max(0, start), end, sims, seed)
    hist = history(days, plan["risk_per_share"] / plan["entry"], plan["r_multiple"], 3, 63, end, plan.get("date"))
    return {"symbol": plan["symbol"], "sessions_used": len(lib[0]), "sim": sim, "history": hist, "verdict": verdict(sim, hist)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--sims", type=int, default=10000)
    r.add_argument("--seed", type=int, default=19)
    r.add_argument("--days", type=int, default=60)
    r.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    plan = C.read_json(C.path("plan.json"))
    if not plan:
        sys.exit("No plan: run trader-exit plan --write first.")
    try:
        got = C.get_bars(plan["symbol"], "5m", a.days, token=plan.get("token"))
    except C.SourceError as e:
        sys.exit("source failed: %s" % e)
    res = run(plan, got["bars"], a.sims, a.seed)
    res.update(source=got["source"], fetched_at=got["fetched_at"])
    s, h = res["sim"], res["history"]
    print("Time Machine %s: entry %.2f stop %.2f target %.2f, flat by %s IST (%d sessions of %s 5m bars, seed %d)" % (
        plan["symbol"], plan["entry"], plan["stop"], plan["target"], plan["flat_by"], res["sessions_used"], got["source"], a.seed))
    print("  %d replays: target first %.1f%%, stop first %.1f%%, open at flat-by %.1f%%; avg %.2fR" % (
        s["sims"], s["target_first"], s["stop_first"], s["neither"], s["avg_r"]))
    if s["close_p50"]:
        print("  where the open ones closed: p10 %.2f, median %.2f, p90 %.2f" % (s["close_p10"], s["close_p50"], s["close_p90"]))
    print("  history: rule fired %d of %d sessions -> %d target, %d stop, %d neither" % (h["fired"], h["sessions"], h["target"], h["stop"], h["neither"]))
    print("  verdict: " + res["verdict"])
    print("  A simulation of the last %d sessions, not a prediction. %s" % (a.days, C.NOTE_NFA))
    if a.write:
        C.write_json(C.path("timemachine.json"), res)


if __name__ == "__main__":
    main()
