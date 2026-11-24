#!/usr/bin/env python3
"""Results Analyst (NSE filings). Revenue, PAT, margin and EPS: QoQ, YoY, TTM; promoter holding; insider trades.

  python3 trader-analyst/results.py SYMBOL
Full data: trader/analysis/SYMBOL-fundamentals.json. Money as filed (₹ lakhs) shown in ₹ crore.
"""

import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402
import nse_research as R  # noqa: E402


def cr(lakhs):
    return "n/a" if lakhs is None else "₹%s Cr" % C.inr(lakhs / 100.0, 0)[1:]


def pc(x):
    return "n/a" if x is None else "%+.1f%%" % x


def lines(f):
    out, q, r = [], f.get("quote") or {}, f.get("results")
    if q:
        out.append("PE %s vs sector %s (%s)  mcap %s" % (q.get("pe") or "n/a", q.get("sector_pe") or "n/a", q.get("sector_index") or "n/a", C.inr_short(q.get("mcap"))))
    if r:
        L = r["latest"]
        out.append("Quarter ended %s, %s, filed %s%s" % (
            L["end"], f.get("results_basis") or "n/a", L.get("filed") or "n/a", "  STALE: %d days old" % r["age_days"] if r["stale"] else ""))
        out.append("  %s %s  QoQ %s  YoY %s" % (f.get("income_label", "revenue"), cr(L["revenue"]), pc(r["rev_qoq"]), pc(r["rev_yoy"])))
        out.append("  PAT %s  QoQ %s  YoY %s   PAT margin %s (prev %s, yr ago %s)" % (
            cr(L["net_profit"]), pc(r["pat_qoq"]), pc(r["pat_yoy"]), *("n/a" if m is None else "%.1f%%" % m for m in (r["margin"], r["margin_prev"], r["margin_yago"]))))
        out.append("  EPS %s  YoY %s   TTM: income %s, PAT %s, EPS %s" % (
            L["eps"] if L["eps"] is not None else "n/a", pc(r["eps_yoy"]),
            *((cr(r["ttm"]["revenue"]), cr(r["ttm"]["net_profit"]), "%.2f" % r["ttm"]["eps"] if r["ttm"]["eps"] is not None else "n/a") if r["ttm"] else ("n/a",) * 3)))
    else:
        out.append("Results: not available")
    h = f.get("holding") or []
    if h:
        out.append("Promoter holding: " + " -> ".join("%s %.2f%%" % (x["date"][:7], x["promoter"]) for x in h[-4:] if x["promoter"] is not None)
                   + ("  (change %+.2f pts)" % f["promoter_change"] if f.get("promoter_change") is not None else ""))
        out.append("  FII/DII split and pledge %%: in the XBRL filing (%s), not parsed here" % (h[-1].get("xbrl") or "n/a"))
    i = f.get("insider") or {}
    if i:
        out.append("Insider (PIT) last 90d: %d trades, buys %s, sells %s, promoter-group %d%s" % (
            i["n_90d"], C.inr_short(i["buy_value"]), C.inr_short(i["sell_value"]), i["promoter_trades"],
            ", pledge-type %d" % len(i["pledge_like"]) if i["pledge_like"] else ""))
        if not i["n_90d"]:
            out.append("  note: newest PIT record in NSE's feed (last 365d) is %s; the feed may lag, check NSE's PIT page" % (i.get("feed_latest") or "none"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("symbol")
    a = ap.parse_args(argv)
    sym, now = a.symbol.upper(), C.now_ist()
    f = R.fundamentals(C.NSEWeb(), sym, now)
    print("%s fundamentals from NSE filings (fetched %s IST)" % (sym, now.strftime("%d-%b %H:%M")))
    for ln in lines(f):
        print("  " + ln)
    for e in f["errors"]:
        print("  source failed: " + e)
    C.write_json(C.path("analysis", sym + "-fundamentals.json"), f)
    print("  " + C.NOTE_NFA)


if __name__ == "__main__":
    main()
