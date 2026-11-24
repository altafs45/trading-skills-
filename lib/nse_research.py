"""Per-stock research shared by trader-analyze, trader-analyst, trader-news, trader-risk and trader-track:
fundamentals, events, deals and news. Every fetch is cached for the IST day; every failure is
collected in `errors` (named by source) and the rest carries on."""

import datetime as dt, glob, os, re, urllib.parse
import nse_common as C
import nse_parsers as P

ENDPOINTS = {  # key: (endpoint, params, parser)
    "announcements": ("/api/corporate-announcements", {"index": "equities"}, P.parse_announcements),
    "events": ("/api/event-calendar", {"index": "equities"}, P.parse_event_calendar),
    "board": ("/api/corporate-board-meetings", {"index": "equities"}, P.parse_board_meetings),
    "actions": ("/api/corporates-corporateActions", {"index": "equities"}, P.parse_corp_actions),
    "results": ("/api/results-comparision", {}, P.parse_results_cmp),
    "holding": ("/api/corporate-share-holdings-master", {"index": "equities"}, P.parse_shareholding),
    "insider": ("/api/corporates-pit", {"index": "equities"}, P.parse_pit),
    "filings": ("/api/corporates-financial-results", {"index": "equities", "period": "Quarterly"}, None),
    "integrated": ("/api/NextApi/apiClient/GetQuoteApi", {"functionName": "getIntegratedFilingData"}, P.parse_integrated),
}
TAGS = [("results", r"\bresults?\b|\bq[1-4]\b|quarterly|\bprofit|revenue|earnings|net loss|\bpat\b|ebitda"),
        ("order win", r"\b(bags|wins|won|secures?|receives?|bagged)\b.{0,40}\b(order|contract|project)|\border (win|inflow)"),
        ("deal", r"acqui|merger|amalgamat|\bstake\b|joint venture|\bjv\b|takeover|demerger|divest|\bqip\b|fund ?rais"),
        ("management", r"\bceo\b|\bcfo\b|\bmd\b|managing director|chairman|resign|appoint|steps down|key managerial"),
        ("regulatory", r"\bsebi\b|\brbi\b|penalt|show.cause|\bgst\b|tax demand|probe|investigat|\bcourt\b|nclt|\bban\b|income.tax"),
        ("rating", r"\bcredit rating|crisil|icra|\bcare ratings?|india ratings|upgrade|downgrade|target price|price target|brokerage|broker.s call|"
                    r"\b(buy|sell|hold|accumulate|reduce) (rating|call)|initiates? coverage"),
        ("pledge", r"pledg|encumb"), ("block deal", r"block deal|bulk deal|block trade")]


def tag(text):
    t = (text or "").lower()
    return [k for k, rx in TAGS if re.search(rx, t)] or ["other"]


def _fetch(web, key, sym, now, errors, **extra):
    ep, params, parse = ENDPOINTS[key]
    p = C.path("cache", "nse", sym, key + ".json")
    try:
        raw, at, _ = C.cached(p, "day", lambda: web.api(ep, symbol=sym, **dict(params, **extra)), now)
        return (parse(raw) if parse else raw), at
    except C.SourceError as e:
        errors.append(str(e))
        return None, None


def quote(web, sym, now, errors, ttl=300, series=None):
    if series is None:
        try:
            series = (C.load_universe(None)["symbols"].get(sym) or {}).get("series")
        except C.SourceError:
            series = None
    try:
        q, at, _ = C.cached(C.path("cache", "nse", sym, "quote.json"), ttl, lambda: web.quote(sym, series or "EQ"), now)
        C.remember_sector(sym, q)
        q["fetched_at"] = at
        return q
    except C.SourceError as e:
        errors.append(str(e))
        return None


# ---------------------------------------------------------------- fundamentals
def _q_ok(q):
    if not q.get("start"):
        return True
    span = (dt.date.fromisoformat(q["end"]) - dt.date.fromisoformat(q["start"])).days
    return span < 100


def _find(qs, end, days, slack=12):
    t = dt.date.fromisoformat(end) - dt.timedelta(days=days)
    return next((q for q in qs if abs((dt.date.fromisoformat(q["end"]) - t).days) <= slack), None)


def results_summary(quarters, today):
    """QoQ / YoY / TTM on revenue, net profit, margin and EPS. Money in ₹ lakhs as filed."""
    qs = [q for q in quarters if _q_ok(q)]
    if not qs:
        return None
    L = qs[-1]
    prev, yago = _find(qs, L["end"], 91), _find(qs, L["end"], 365)
    g = lambda a, b, k: C.pct(a.get(k), b.get(k)) if a and b and b.get(k) and b.get(k) > 0 else None
    margin = lambda q: (q["net_profit"] / q["revenue"] * 100) if q and q.get("revenue") and q.get("net_profit") is not None else None
    ttm = None
    last4 = [L] + [_find(qs, L["end"], 91 * k) for k in (1, 2, 3)]
    if all(last4):
        ttm = {k: sum(q[k] for q in last4) if all(q.get(k) is not None for q in last4) else None for k in ("revenue", "net_profit", "eps")}
    age = (today - dt.date.fromisoformat(L["end"])).days
    return {"latest": L, "prev": prev, "year_ago": yago, "margin": margin(L), "margin_prev": margin(prev), "margin_yago": margin(yago),
            "rev_qoq": g(L, prev, "revenue"), "rev_yoy": g(L, yago, "revenue"), "pat_qoq": g(L, prev, "net_profit"),
            "pat_yoy": g(L, yago, "net_profit"), "eps_yoy": g(L, yago, "eps"), "ttm": ttm, "age_days": age,
            "stale": age > 135, "quarters": qs[-6:]}


def fundamentals(web, sym, now=None, errors=None):
    now, errors = now or C.now_ist(), errors if errors is not None else []
    q = quote(web, sym, now, errors)
    integ, res_at = _fetch(web, "integrated", sym, now, errors)
    basis, res = None, None
    for b in ("Consolidated", "Standalone"):
        qs = [x for x in integ or [] if x["basis"] == b]
        if qs:
            basis, res = b, qs
            break
    if not res:  # older feed (frozen at Dec 2024 when checked on 2026-11-24): standalone, revenue from operations
        res, res_at = _fetch(web, "results", sym, now, errors)
        basis = "Standalone (results-comparision)" if res else None
    hold, hold_at = _fetch(web, "holding", sym, now, errors)
    ins, ins_at = _fetch(web, "insider", sym, now, errors, from_date=(now.date() - dt.timedelta(days=365)).strftime("%d-%m-%Y"),
                         to_date=now.date().strftime("%d-%m-%Y"))
    out = {"quote": q, "results": results_summary(res or [], now.date()) if res else None, "results_at": res_at,
           "results_basis": basis, "income_label": "total income" if basis in ("Consolidated", "Standalone") else "revenue",
           "holding": (hold or [])[-6:], "holding_at": hold_at, "errors": errors}
    if hold and len(hold) >= 2:
        out["promoter_change"] = round(hold[-1]["promoter"] - hold[-2]["promoter"], 2) if None not in (hold[-1]["promoter"], hold[-2]["promoter"]) else None
    cut = (now.date() - dt.timedelta(days=90)).isoformat()
    recent = [r for r in (ins or []) if (r["date"] or "") >= cut]
    buy = sum(r["value"] or 0 for r in recent if (r["type"] or "").lower().startswith("buy"))
    sell = sum(r["value"] or 0 for r in recent if (r["type"] or "").lower().startswith("sell"))
    promo = [r for r in recent if "promoter" in (r["category"] or "").lower()]
    out["insider"] = {"n_90d": len(recent), "buy_value": buy, "sell_value": sell, "promoter_trades": len(promo),
                      "pledge_like": [r for r in recent if re.search(r"pledg|invoc|revoc", (r["mode"] or ""), re.I)][:3],
                      "latest": recent[:5], "fetched_at": ins_at,
                      "feed_latest": max((r["date"] or "" for r in ins or []), default=None)}
    return out


# ---------------------------------------------------------------- deals (market-wide, accumulated per day)
DEALS = {"bulk": "https://nsearchives.nseindia.com/content/equities/bulk.csv",
         "block": "https://nsearchives.nseindia.com/content/equities/block.csv"}


def refresh_deals(web, now, errors):
    """Today's bulk/block CSVs, saved per trading date so history builds up in trader/cache/deals/."""
    for kind, url in DEALS.items():
        p = C.path("cache", "deals_raw", kind + ".json")
        try:
            rows, at, fromcache = C.cached(p, "day", lambda: P.parse_deals_csv(web.archive(url, kind + ".csv").decode("utf-8", "replace"), kind), now)
        except C.SourceError as e:
            errors.append(str(e))
            continue
        by = {}
        for r in rows:
            by.setdefault(r["date"], []).append(r)
        for d, rs in by.items():
            f = C.path("cache", "deals", "%s_%s.json" % (d, kind))
            C.write_json(f, rs, compact=True)


def deals_for(sym, since):
    out = []
    for f in glob.glob(os.path.join(C.data_dir(), "cache", "deals", "*.json")):
        if os.path.basename(f)[:10] >= since:
            out += [r for r in C.read_json(f, []) if r["symbol"] == sym]
    return sorted(out, key=lambda r: r["date"] or "")


# ---------------------------------------------------------------- events
RISK_WORDS = r"result|financial|dividend|bonus|split|buy ?back|fund|merger|demerger|agm|rights"


def events(web, sym, now=None, days=30, universe=None, errors=None):
    now, errors = now or C.now_ist(), errors if errors is not None else []
    today = now.date()
    lo, hi = (today - dt.timedelta(days=days)).isoformat(), (today + dt.timedelta(days=days)).isoformat()
    rows = []
    for key in ("events", "board", "actions"):
        got, _ = _fetch(web, key, sym, now, errors)
        rows += [dict(r, source=key) for r in got or [] if r.get("date") and lo <= r["date"] <= hi]
    ann, _ = _fetch(web, "announcements", sym, now, errors)
    for a in ann or []:
        if re.search(r"credit rating", a["subject"] + " " + a["text"], re.I) and (a["time"] or "")[:10] >= lo:
            rows.append({"date": a["time"][:10], "kind": "credit rating", "what": a["subject"], "detail": a["text"][:160], "source": "announcements"})
    refresh_deals(web, now, errors)
    for d in deals_for(sym, lo):
        rows.append({"date": d["date"], "kind": d["kind"] + " deal", "what": "%s %s %s @ %.2f" % (d["client"], d["side"], C.inr(d["qty"], 0)[1:], d["price"] or 0), "source": "deals"})
    if universe:
        for e in (universe.get("fo_expiries") or {}).get(sym, []):
            if today.isoformat() <= e <= hi:
                rows.append({"date": e, "kind": "F&O expiry", "what": "stock futures/options expiry", "source": "Kite instruments"})
    seen, out = set(), []
    for r in sorted(rows, key=lambda r: r["date"]):
        k = (r["date"], r["kind"], (r.get("what") or "")[:40].lower())
        if k not in seen:
            seen.add(k)
            out.append(r)
    risk_today = [r for r in out if r["date"] == today.isoformat() and (re.search(RISK_WORDS, (r.get("what") or "") + (r.get("detail") or ""), re.I) or r["kind"] in ("dividend", "bonus", "split", "buyback", "demerger"))]
    return {"past": [r for r in out if r["date"] < today.isoformat()], "upcoming": [r for r in out if r["date"] >= today.isoformat()],
            "event_risk_today": risk_today, "errors": errors}


# ---------------------------------------------------------------- news
GNEWS = "https://news.google.com/rss/search?q=%s&hl=en-IN&gl=IN&ceid=IN:en"


def short_name(name):
    return re.sub(r"\b(limited|ltd\.?|the)\b", "", name or "", flags=re.I).strip(" .,")


def news(web, sym, name, now=None, days=7, errors=None):
    """Google News (India) + NSE announcements. Titles, source, time, link only."""
    now, errors = now or C.now_ist(), errors if errors is not None else []
    since = (now - dt.timedelta(days=days)).astimezone(dt.timezone.utc).isoformat()
    items = []
    q = '"%s" OR "NSE:%s" when:%dd' % (short_name(name) or sym, sym, days)
    try:
        raw, _, _ = C.cached(C.path("cache", "news", sym + "_gnews.json"), 900,
                             lambda: P.parse_rss(C.http(GNEWS % urllib.parse.quote(q), limiter=C.GNEWS_LIMIT, source="Google News RSS")), now)
        items += [dict(r, via="Google News") for r in raw]
    except C.SourceError as e:
        errors.append(str(e))
    ann, _ = _fetch(web, "announcements", sym, now, errors)
    for a in ann or []:
        t = dt.datetime.fromisoformat(a["time"]).astimezone(dt.timezone.utc).isoformat() if a["time"] else None
        items.append({"title": "%s: %s" % (a["subject"], a["text"][:140]), "source": "NSE filing", "time": t, "link": a["pdf"], "via": "NSE"})
    items = [i for i in items if (i["time"] or "") >= since]
    seen, out = set(), []
    for i in sorted(items, key=lambda i: i["time"] or "", reverse=True):
        k = re.sub(r"\W+", " ", i["title"].lower())[:70]
        if k in seen:
            continue
        seen.add(k)
        i["tags"] = tag(i["title"])
        out.append(i)
    return out


# ---------------------------------------------------------------- live quotes (alerts, track)
def live_quotes(web, syms, universe, now=None, errors=None, max_nse=10):
    """Kite quotes when logged in (up to 500 per request, 1 request/s), else NSE GetQuoteApi one by one
    (>=1 s apart, first `max_nse` symbols). -> ({SYM: quote}, source)"""
    now, errors = now or C.now_ist(), errors if errors is not None else []
    meta = (universe or {}).get("symbols") or {}
    k = C.kite()
    if k and syms:
        try:
            got = k.quote([meta.get(s, {}).get("ksym") or s for s in syms])
            return {q["symbol"]: dict(q, fetched_at=C.iso(now)) for q in got}, "Kite"
        except C.SourceError as e:
            errors.append(str(e))
    out = {}
    if len(syms) > max_nse:
        errors.append("NSE quotes: only the first %d of %d symbols (log in to Kite for more)" % (max_nse, len(syms)))
    for s in syms[:max_nse]:
        q = quote(web, s, now, errors, ttl=10, series=meta.get(s, {}).get("series"))
        if q:
            out[s] = q
    return out, "NSE (delayed)"
