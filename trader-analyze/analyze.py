#!/usr/bin/env python3
"""Analyze one NSE stock: technicals, fundamentals, events, news, data-based outlook and a chart.

  python3 trader-analyze/analyze.py SYMBOL [--no-news] [--horizon 10]
Prints <= 40 lines, most important first. Full data: trader/analysis/SYMBOL.json; chart: trader/charts/SYMBOL.html.
"""

import argparse, datetime as dt, importlib.util, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import nse_common as C  # noqa: E402
import indicators as I  # noqa: E402
import breakout as B  # noqa: E402
import nse_research as R  # noqa: E402
import chart as CH  # noqa: E402


def sibling(folder, name):
    spec = importlib.util.spec_from_file_location("nse_" + name, os.path.join(HERE, "..", folder, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def daily_series(sym, token, now, errors):
    """EOD store first (has delivery %), Yahoo daily as fallback. -> (series, index dict, source)."""
    dates, ser, idx = C.eod_load(C.KEEP, [sym])
    s = ser.get(sym)
    if s and len(s["c"]) >= 200:
        return s, idx, "NSE bhavcopy store (%d sessions)" % len(s["c"])
    try:
        b = C.get_bars(sym, "1d", 500, now, token=token)["bars"]
        s = {"d": [x[0][:10] for x in b], "series": "EQ", "o": [x[1] for x in b], "h": [x[2] for x in b], "l": [x[3] for x in b],
             "c": [x[4] for x in b], "v": [x[5] for x in b], "t": [x[4] * x[5] / 1e5 for x in b], "dp": [None] * len(b)}
        try:
            n = C.get_bars("^NSEI", "1d", 500, now)["bars"]
            idx = dict(idx, **{"NIFTY 50": {"d": [x[0][:10] for x in n], "c": [x[4] for x in n]}})
        except C.SourceError as e:
            errors.append(str(e))
        return s, idx, "Yahoo daily (store has %d sessions; no delivery %%)" % (len(ser.get(sym, {}).get("c", [])))
    except C.SourceError as e:
        errors.append(str(e))
        return (s, idx, "NSE bhavcopy store (%d sessions)" % len(s["c"])) if s else (None, idx, None)


def technicals(s, idx, sector_index):
    c, h, l, v = s["c"], s["h"], s["l"], s["v"]
    e20, e50, e200 = I.ema(c, 20)[-1], I.ema(c, 50)[-1], I.ema(c, 200)[-1]
    ml, sg, hist = I.macd(c)
    ax, pdi, mdi = I.adx(h, l, c)
    a14 = I.atr(h, l, c)[-1]
    bw = I.bb_width(c)
    bwh = [x for x in bw[-120:] if x is not None]
    ob = I.obv(c, v)
    sup, res = I.support_resistance(h, l, c[-1], 3)
    dp = [x for x in s["dp"][-60:] if x is not None]
    t = {"close": c[-1], "date": s["d"][-1], "ema20": e20, "ema50": e50, "ema200": e200, "rsi14": I.rsi(c)[-1],
         "macd": ml[-1], "macd_signal": sg[-1], "macd_hist": hist[-1], "atr14": a14, "atr_pct": a14 / c[-1] * 100 if a14 else None,
         "bb_width": bw[-1], "bb_width_pctile": (sum(1 for x in bwh if x <= bw[-1]) / len(bwh) * 100) if bwh and bw[-1] else None,
         "adx": ax[-1], "plus_di": pdi[-1], "minus_di": mdi[-1], "obv_20d_change": ob[-1] - ob[-21] if len(ob) > 21 else None,
         "vol_20_vs_60": (sum(v[-20:]) / 20) / (sum(v[-60:]) / 60) if len(v) >= 60 else None,
         "deliv_10_vs_60": (sum(dp[-10:]) / len(dp[-10:])) / (sum(dp) / len(dp)) if len(dp) >= 30 else None,
         "deliv_last": s["dp"][-1], "support": sup, "resistance": res, "structure": I.structure(h, l, 3)[0]}
    for name, key in (("NIFTY 50", "rs_nifty"), (sector_index, "rs_sector")):
        y = idx.get((name or "").upper())
        if y:
            a, b = I.align(s["d"], c, y["d"], y["c"])
            t[key + "_20d"], t[key + "_60d"] = I.rel_strength(a, b, 20), I.rel_strength(a, b, 60)
    w = I.weekly(s["d"], s["o"], h, l, c, v)
    we10, we30 = I.ema(w["c"], 10)[-1], I.ema(w["c"], 30)[-1]
    t["weekly"] = "up (close > wEMA10 > wEMA30)" if we10 and we30 and w["c"][-1] > we10 > we30 else \
        "down (close < wEMA10 < wEMA30)" if we10 and we30 and w["c"][-1] < we10 < we30 else "mixed"
    return t


def intraday(sym, token, now, errors):
    try:
        got = C.get_bars(sym, "5m", 5, now, token=token)
    except C.SourceError as e:
        errors.append(str(e))
        return None
    days = C.days_in(got["bars"])
    if not days:
        return None
    b = [x for x in got["bars"] if x[0][:10] == days[-1]]
    vw = I.vwap(b)
    orh = max(x[2] for x in b[:3])
    return {"session": days[-1], "last": b[-1][4], "vwap": round(vw[-1], 2), "or_high": orh, "or_low": min(x[3] for x in b[:3]),
            "orb": any(x[4] > orh for x in b[3:]), "structure": I.structure([x[2] for x in b], [x[3] for x in b], 2)[0],
            "source": got["source"]}


def f2(x, d=2):
    return "n/a" if x is None else ("%." + str(d) + "f") % x


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol")
    ap.add_argument("--horizon", type=int, default=10)
    ap.add_argument("--no-news", action="store_true")
    a = ap.parse_args(argv)
    sym, now, errors = a.symbol.upper(), C.now_ist(), []
    web = C.NSEWeb()
    try:
        uni = C.load_universe(web)
    except C.SourceError as e:
        errors.append(str(e))
        uni = {"symbols": {}}
    meta = uni["symbols"].get(sym, {})
    fund = R.fundamentals(web, sym, now, errors)
    q = fund.get("quote") or {}
    s, idx, src = daily_series(sym, meta.get("token"), now, errors)
    if not s:
        sys.exit("No price history for %s (%s)" % (sym, "; ".join(errors)))
    tech = technicals(s, idx, q.get("sector_index"))
    sc = B.score(s)
    rule = sc["setup"] if sc else None
    rates = B.base_rates(s, rule) if rule else None
    scen = B.scenarios(s, rule, a.horizon)
    ev = R.events(web, sym, now, 30, uni, errors)
    news = [] if a.no_news else R.news(web, sym, meta.get("name") or q.get("name") or sym, now, 7, errors)
    intra = intraday(sym, meta.get("token"), now, errors)
    plan, tm = C.read_json(C.path("plan.json")) or {}, None
    if plan.get("symbol") == sym:
        try:
            tmm = sibling("trader-timemachine", "timemachine")
            tm = tmm.run(plan, C.get_bars(sym, "5m", 60, now, token=meta.get("token"))["bars"], 2000, 19)
        except C.SourceError as e:
            errors.append(str(e))

    # ---- chart
    lv = [(sc["level"], "breakout") if sc else (None, ""), (tech["support"], "support"), (tech["resistance"], "resistance")]
    if scen.get("ok"):
        lv += [(scen["bull"]["level"], "bull %d%%" % scen["bull"]["prob"]), (scen["bear"]["level"], "bear %d%%" % scen["bear"]["prob"])]
    evm = [(e["date"], "%s: %s" % (e["kind"], e["what"][:60])) for e in ev["past"] + ev["upcoming"]]
    chart = CH.write_chart(C.path("charts", sym + ".html"), s["d"], s["o"], s["h"], s["l"], s["c"], s["v"],
                           "%s daily" % sym, "%s. Levels and scenarios from the stock's own history; not a forecast." % src,
                           {"EMA20": I.ema(s["c"], 20), "EMA50": I.ema(s["c"], 50), "EMA200": I.ema(s["c"], 200)}, lv, evm)

    # ---- text, most important first
    L = []
    L.append("%s %s  close %s (%s, %s)  %s%s" % (sym, R.short_name(meta.get("name") or q.get("name") or ""), C.inr(tech["close"]), tech["date"], src,
                                                 q.get("basic_industry") or q.get("sector") or "", "  [%s]" % meta["series"] if meta.get("series", "EQ") != "EQ" else ""))
    L.append("SETUP: " + ("%s, score %d, level %.2f (%+.2f%%), RVOL %s. %s" % (sc["setup_name"], sc["score"], sc["level"], sc["pct_above"], sc["rvol"], "; ".join(sc["reasons"][:3])) if sc else "no breakout trigger today"))
    if rates:
        for hz, r in sorted(rates["horizons"].items()):
            L.append("  base rate %2dd: %d past triggers, held above level %.0f%%, median %+.2f%%, median DD %.2f%%, worst %.2f%%" % (hz, r["n"], r["held_pct"], r["median_pct"], r["median_dd_pct"], r["worst_dd_pct"]))
    if scen.get("ok"):
        inv_bull = sc["level"] if sc else tech["support"]
        L.append("OUTLOOK %dd (n=%d, %s; move threshold ±%.2f%%):" % (scen["horizon"], scen["n"], scen["basis"], scen["k_pct"]))
        L.append("  bull %d%% -> ~%s (invalid below %s) | base %d%% (±%.2f%%) | bear %d%% -> ~%s (invalid above %s)" % (
            scen["bull"]["prob"], f2(scen["bull"]["level"]), f2(inv_bull), scen["base"]["prob"], scen["k_pct"], scen["bear"]["prob"], f2(scen["bear"]["level"]), f2(tech["resistance"])))
    else:
        L.append("OUTLOOK: " + scen.get("why", "n/a"))
    if tm:
        L.append("  intraday (time machine on plan.json, 2,000 runs): target first %.1f%%, stop first %.1f%%, open %.1f%%: %s" % (tm["sim"]["target_first"], tm["sim"]["stop_first"], tm["sim"]["neither"], tm["verdict"]))
    risk = ev["event_risk_today"]
    L.append("EVENT RISK TODAY: " + ("; ".join("%s %s" % (e["kind"], e["what"][:50]) for e in risk) if risk else "none found"))
    for e in ev["upcoming"][:4]:
        L.append("  next  %s  %s: %s" % (e["date"], e["kind"], e["what"][:70]))
    for e in ev["past"][-3:]:
        L.append("  past  %s  %s: %s" % (e["date"], e["kind"], e["what"][:70]))
    L.append("TECH: EMA20 %s EMA50 %s EMA200 %s | RSI %s | MACD %s/%s | ADX %s (+DI %s -DI %s)" % tuple(f2(tech[k], d) for k, d in (
        ("ema20", 1), ("ema50", 1), ("ema200", 1), ("rsi14", 1), ("macd", 2), ("macd_signal", 2), ("adx", 1), ("plus_di", 1), ("minus_di", 1))))
    L.append("  ATR %s (%s%%) | BB width %s%% (pctile %s of 120d) | swings %s | weekly %s" % (
        f2(tech["atr14"]), f2(tech["atr_pct"]), f2(tech["bb_width"]), f2(tech["bb_width_pctile"], 0), tech["structure"], tech["weekly"]))
    L.append("  S %s / R %s | vol 20d/60d %sx | delivery %s%% (10d/60d %sx) | OBV 20d %s" % (
        f2(tech["support"]), f2(tech["resistance"]), f2(tech["vol_20_vs_60"]), f2(tech["deliv_last"], 1), f2(tech["deliv_10_vs_60"]),
        "rising" if (tech["obv_20d_change"] or 0) > 0 else "falling"))
    L.append("  RS vs NIFTY 50: 20d %s%% 60d %s%% | vs %s: 20d %s%% 60d %s%%" % (
        f2(tech.get("rs_nifty_20d"), 1), f2(tech.get("rs_nifty_60d"), 1), q.get("sector_index") or "sector",
        f2(tech.get("rs_sector_20d"), 1), f2(tech.get("rs_sector_60d"), 1)))
    if intra:
        L.append("  5m %s (%s): last %.2f, VWAP %.2f, OR %.2f-%.2f%s, %s" % (intra["session"], intra["source"], intra["last"], intra["vwap"], intra["or_low"], intra["or_high"], ", ORB fired" if intra["orb"] else "", intra["structure"]))
    if q:
        L.append("  52w %s-%s, band %s, quote %s" % (f2(q.get("year_low")), f2(q.get("year_high")), q.get("band") or "n/a", (q.get("updated") or "")[:16]))
    try:
        L += ["FUND: " + x if i == 0 else "  " + x for i, x in enumerate(sibling("trader-analyst", "results").lines(fund)[:6])]
    except Exception as e:  # report, don't hide
        errors.append("fundamentals render: %s" % e)
    if news:
        L.append("NEWS 7d (%d):" % len(news))
        for n in news[:5]:
            L.append("  %s [%s] %s - %s" % ((n["time"] or "")[:10], ",".join(n["tags"]), n["title"][:85], n["source"] or n["via"]))
    L.append("Chart: %s  JSON: %s" % (chart, C.path("analysis", sym + ".json")))
    for e in errors[:4]:
        L.append("source failed: " + e)
    L.append(C.NOTE_NFA + " Outlook = historical frequencies, not a forecast.")
    print("\n".join(L[:40]))
    C.write_json(C.path("analysis", sym + ".json"), {
        "symbol": sym, "generated_at": C.iso(now), "price_source": src, "technical": tech, "setup": sc, "base_rates": rates,
        "scenarios": scen, "timemachine": tm, "intraday": intra, "fundamentals": fund, "events": ev, "news": news, "errors": errors})


if __name__ == "__main__":
    main()
