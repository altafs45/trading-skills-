#!/usr/bin/env python3
"""News Monitor (NSE). Google News (India) + NSE announcements per symbol, tagged, new-only, newest first.

  python3 trader-news/news.py [--symbols TCS,INFY] [--days 2] [--all] [--top 10] [--no-moves]
Symbols default to the top of trader/watchlist.json. Full data: trader/news.json.
"""

import argparse, datetime as dt, hashlib, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import nse_common as C  # noqa: E402
import nse_parsers as P  # noqa: E402
import nse_research as R  # noqa: E402

KEEP_DAYS = 30


def fp(item):
    return hashlib.sha1((item.get("link") or item["title"]).encode("utf-8")).hexdigest()[:16]


def select(items, state, show_all=False):
    """New items only (unless show_all); never repeats one already shown."""
    seen = state.setdefault("seen", {})
    return [i for i in items if show_all or fp(i) not in seen]


def remember(items, state, now):
    seen = state.setdefault("seen", {})
    for i in items:
        seen[fp(i)] = now.date().isoformat()
    cut = (now.date() - dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["seen"] = {k: v for k, v in seen.items() if v >= cut}


def when(t):
    return dt.datetime.fromisoformat(t).astimezone(C.IST).strftime("%d-%b %H:%M") if t else "  --  "


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbols")
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-moves", action="store_true")
    a = ap.parse_args(argv)
    now, web, errors = C.now_ist(), C.NSEWeb(), []
    if a.symbols:
        syms = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    else:
        wl = C.read_json(C.path("watchlist.json"), {}) or {}
        syms = [r["symbol"] for r in (wl.get("stocks") or [])[:a.top]]
    if not syms:
        sys.exit("No symbols: pass --symbols or run trader-scanner first.")
    try:
        uni = C.load_universe(None)["symbols"]
    except C.SourceError:
        uni = {}
    state = C.read_json(C.path("news_state.json"), {}) or {}
    out, shown = {}, []
    print("News %s IST, last %d day(s), %s:" % (now.strftime("%d-%b %H:%M"), a.days, "all" if a.all else "new only"))
    for s in syms:
        name = (uni.get(s) or {}).get("name") or s
        items = R.news(web, s, name, now, a.days, errors)
        new = select(items, state, a.all)
        move = None
        if not a.no_moves:
            q = R.quote(web, s, now, errors)
            move = q and q.get("pchange")
        out[s] = {"name": name, "move_pct": move, "items": items}
        head = "%s (%s)%s" % (s, R.short_name(name), "  %+.2f%% vs prev close" % move if move is not None else "")
        print("\n" + head + ("  - nothing new" if not new else ""))
        for i in new[:8]:
            print("  %s  [%s] %s - %s" % (when(i["time"]), ",".join(i["tags"]), i["title"][:110], i["source"] or i["via"]))
        shown += new
    try:
        fii, at, _ = C.cached(C.path("cache", "fiidii.json"), "day", lambda: web.api("/api/fiidiiTradeReact"), now)
        rows = P.parse_fiidii(fii)
        print("\nFII/DII cash (₹ Cr, %s): %s" % (rows[0]["date"] if rows else "n/a",
                                               "  ".join("%s net %+.0f" % (r["category"], r["net_cr"] or 0) for r in rows)))
    except C.SourceError as e:
        errors.append(str(e))
    remember(shown, state, now)
    C.write_json(C.path("news_state.json"), state)
    C.write_json(C.path("news.json"), {"generated_at": C.iso(now), "days": a.days, "symbols": out, "errors": errors})
    for e in errors:
        print("source failed: " + e)


if __name__ == "__main__":
    main()
