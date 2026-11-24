"""Breakout rules, the 0-100 score, intraday rules, historical base rates and scenario odds.
Daily rules read a series dict s = {'d','o','h','l','c','v','dp','t'} (oldest first) at bar i ("today")."""

import math
import indicators as I

DEFAULTS = {"base_days": 15, "base_max_pct": 10.0, "vol_mult": 2.0, "retest_pct": 1.5, "min_price": 20.0,
            "min_turnover_cr": 5.0, "include_be_sm": False, "include_etf": False, "or_minutes": 15}
W = {"hi52": 30, "hi50": 20, "hi20": 12, "base": 15, "vcp": 5, "vol": 15, "deliv": 5, "stacked": 15,
     "above": 8, "gap": 6, "inside": 6, "retest": 10}
TRIGGERS = ("hi52", "hi50", "base", "hi20", "retest", "inside", "gap")  # priority for the headline setup
NAMES = {"hi52": "52-week closing high", "hi50": "50-day closing high", "hi20": "20-day closing high",
         "base": "tight-base breakout", "retest": "retest of broken level", "inside": "inside-bar breakout",
         "gap": "gap-up held"}


def prepare(s):
    if "e20" in s:
        return s
    c, v = s["c"], s["v"]
    s["e20"], s["e50"], s["e200"] = I.ema(c, 20), I.ema(c, 50), I.ema(c, 200)
    n = len(c)
    s["av20"] = [None] * n
    s["ad20"] = [None] * n
    for i in range(20, n):
        s["av20"][i] = sum(v[i - 20:i]) / 20.0
        d = [x for x in s["dp"][i - 20:i] if x is not None]
        s["ad20"][i] = sum(d) / len(d) if len(d) >= 10 else None
    return s


def _hi(s, i, n):
    if i < n:
        return None
    lvl = max(s["c"][i - n:i])
    return lvl if s["c"][i] > lvl else None


def rules(s, i, cfg=DEFAULTS):
    """-> {rule: (level or True, reason)} for every rule that fires at bar i."""
    s = prepare(s)
    c, h, l, o = s["c"], s["h"], s["l"], s["o"]
    hits = {}
    n52 = min(250, i)
    if n52 >= 120:
        lvl = _hi(s, i, n52)
        if lvl:
            hits["hi52"] = (lvl, "closed above its %s-session closing high %.2f" % ("52-week" if n52 >= 245 else str(n52), lvl))
    for n, k in ((50, "hi50"), (20, "hi20")):
        lvl = _hi(s, i, n)
        if lvl:
            hits[k] = (lvl, "closed above the %d-day closing high %.2f" % (n, lvl))
    b = cfg["base_days"]
    if i >= b:
        H, L = max(h[i - b:i]), min(l[i - b:i])
        width = (H - L) / L * 100 if L else 99
        if width < cfg["base_max_pct"] and c[i] > H:
            hits["base"] = (H, "%d-day range %.1f%% wide, closed above its high %.2f" % (b, width, H))
            if i >= 30:
                seg = [(max(h[j:j + 10]) - min(l[j:j + 10])) / min(l[j:j + 10]) * 100 for j in (i - 30, i - 20, i - 10)]
                if seg[0] > seg[1] > seg[2]:
                    hits["vcp"] = (True, "ranges contracting %.1f%% > %.1f%% > %.1f%% (VCP)" % tuple(seg))
    av = s["av20"][i]
    if av and s["v"][i] >= cfg["vol_mult"] * av:
        hits["vol"] = (True, "volume %.1fx its 20-day average" % (s["v"][i] / av))
        ad, dp = s["ad20"][i], s["dp"][i]
        if ad is not None and dp is not None and dp > ad:
            hits["deliv"] = (True, "delivery %.0f%% vs %.0f%% average" % (dp, ad))
    e = (s["e20"][i], s["e50"][i], s["e200"][i])
    if None not in e:
        if c[i] > e[0] > e[1] > e[2]:
            hits["stacked"] = (True, "close > EMA20 > EMA50 > EMA200")
        elif c[i] > max(e):
            hits["above"] = (True, "close above EMA20/50/200")
    if i >= 1 and o[i] > h[i - 1] and l[i] > h[i - 1]:
        hits["gap"] = (h[i - 1], "gapped above yesterday's high %.2f and never filled" % h[i - 1])
    if i >= 2 and h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2] and c[i] > h[i - 1]:
        hits["inside"] = (h[i - 1], "closed above inside bar high %.2f" % h[i - 1])
    if i >= 40:
        lvl = max(c[i - 40:i - 10])
        broke = any(c[j] > lvl for j in range(i - 10, i - 2))
        if broke and min(l[i - 2:i + 1]) <= lvl * (1 + cfg["retest_pct"] / 100) and c[i] > lvl:
            hits["retest"] = (lvl, "broke %.2f, pulled back to it and held" % lvl)
    return hits


def score(s, i=None, cfg=DEFAULTS):
    """Score bar i (default last) 0-100. Returns None when no trigger rule fired."""
    i = len(s["c"]) - 1 if i is None else i
    hits = rules(s, i, cfg)
    trig = [k for k in TRIGGERS if k in hits]
    if not trig:
        return None
    pts = max(W[k] for k in ("hi52", "hi50", "hi20") if k in hits) if any(k in hits for k in ("hi52", "hi50", "hi20")) else 0
    pts += sum(W[k] for k in hits if k not in ("hi52", "hi50", "hi20"))
    head = trig[0]
    lvl = hits[head][0]
    av = s["av20"][i]
    return {"setup": head, "setup_name": NAMES[head], "score": min(100, pts), "level": round(lvl, 2),
            "close": s["c"][i], "pct_above": round((s["c"][i] / lvl - 1) * 100, 2),
            "rvol": round(s["v"][i] / av, 2) if av else None, "rules": sorted(hits),
            "reasons": [hits[k][1] for k in sorted(hits, key=lambda k: -W[k])]}


def liquid(s, cfg=DEFAULTS, meta=None):
    """-> None if OK, else the reason it is filtered out."""
    meta = meta or {}
    if s["series"] != "EQ" and not cfg["include_be_sm"]:
        return "series %s (no intraday)" % s["series"]
    if meta.get("etf") and not cfg["include_etf"]:
        return "ETF"
    if s["c"][-1] < cfg["min_price"]:
        return "price under %.0f" % cfg["min_price"]
    t = (s["t"][-1] or 0) / 100.0  # lakhs -> crore
    if t < cfg["min_turnover_cr"]:
        return "turnover ₹%.1f Cr < ₹%.0f Cr" % (t, cfg["min_turnover_cr"])
    return None


# ---------------------------------------------------------------- intraday (shortlist)
def intraday(bars, prev_high, avg_daily_vol=None, or_minutes=15, elapsed_frac=None):
    """Rules on one session's bars [t,o,h,l,c,v]: ORB, VWAP reclaim, prior-day-high break, RVOL so far."""
    if not bars:
        return {"status": "no bars"}
    step = max(1, or_minutes // 5) if len(bars) > 1 else 1
    rng = bars[:step]
    orh, orl = max(b[2] for b in rng), min(b[3] for b in rng)
    vw = I.vwap(bars)
    last = bars[-1]
    out = {"or_high": orh, "or_low": orl, "vwap": round(vw[-1], 2), "last": last[4], "time": last[0][11:16]}
    out["orb"] = any(b[4] > orh for b in bars[step:])
    out["vwap_reclaim"] = len(bars) > 1 and bars[-2][4] < vw[-2] and last[4] > vw[-1]
    out["above_vwap"] = last[4] > vw[-1]
    out["pdh_break"] = prev_high is not None and last[4] > prev_high
    vol = sum(b[5] for b in bars)
    if avg_daily_vol and elapsed_frac:
        out["rvol"] = round(vol / (avg_daily_vol * elapsed_frac), 2)
    return out


# ---------------------------------------------------------------- history: base rates and scenarios
def base_rates(s, rule, horizons=(1, 5, 10), start=60, cfg=DEFAULTS):
    """Every past bar where `rule` fired: did close stay above the level after h days, median move, max drawdown."""
    s = prepare(s)
    c, l, n = s["c"], s["l"], len(s["c"])
    ev = []
    for i in range(start, n - 1):
        hit = rules(s, i, cfg).get(rule)
        if hit:
            ev.append((i, hit[0] if hit[0] is not True else c[i]))
    out = {"rule": rule, "events": len(ev), "horizons": {}}
    for h in horizons:
        rows = [(c[i + h] / c[i] - 1, c[i + h] > lv, min(l[i + 1:i + h + 1]) / c[i] - 1) for i, lv in ev if i + h < n]
        if rows:
            out["horizons"][h] = {"n": len(rows), "held_pct": round(100.0 * sum(r[1] for r in rows) / len(rows), 1),
                                  "median_pct": round(100 * I.median([r[0] for r in rows]), 2),
                                  "median_dd_pct": round(100 * I.median([r[2] for r in rows]), 2),
                                  "worst_dd_pct": round(100 * min(r[2] for r in rows), 2)}
    return out


def scenarios(s, rule=None, horizon=10, min_n=8, start=60, cfg=DEFAULTS):
    """Bull/base/bear odds from the stock's own analog days (same trigger rule, else same EMA-stack state).
    Threshold k = 0.5 * ATR14% * sqrt(horizon). Levels: close x (1 + median move of that bucket)."""
    s = prepare(s)
    c, n = s["c"], len(s["c"])
    a = I.atr(s["h"], s["l"], c, 14)[-1]
    if a is None:
        return {"ok": False, "why": "fewer than 14 sessions"}
    k = 0.5 * a / c[-1] * math.sqrt(horizon)
    if rule:
        idx = [i for i in range(start, n - horizon) if rule in rules(s, i, cfg)]
        basis = "days the same setup (%s) fired" % NAMES.get(rule, rule)
    else:
        now_stacked = "stacked" in rules(s, n - 1, cfg)
        idx = [i for i in range(max(start, 200), n - horizon) if ("stacked" in rules(s, i, cfg)) == now_stacked]
        basis = "days with the same EMA alignment (%s)" % ("stacked" if now_stacked else "not stacked")
    fw = [c[i + horizon] / c[i] - 1 for i in idx]
    out = {"ok": len(fw) >= min_n, "n": len(fw), "horizon": horizon, "basis": basis, "k_pct": round(100 * k, 2)}
    if not out["ok"]:
        out["why"] = "only %d analog days (need %d): no probabilities" % (len(fw), min_n)
        return out
    for name, sel in (("bull", [f for f in fw if f > k]), ("base", [f for f in fw if -k <= f <= k]),
                      ("bear", [f for f in fw if f < -k])):
        m = I.median(sel)
        out[name] = {"prob": round(100.0 * len(sel) / len(fw)), "n": len(sel),
                     "median_pct": round(100 * m, 2) if m is not None else None,
                     "level": round(c[-1] * (1 + m), 2) if m is not None else None}
    return out
