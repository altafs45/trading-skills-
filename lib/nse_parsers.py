"""Pure parsers for every source the pack reads. No network here, so every one is unit-tested
offline. Each validates the fields it needs and raises FieldError listing the fields it found."""

import csv, datetime as dt, email.utils, html, io, re
import xml.etree.ElementTree as ET

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class SourceError(Exception):
    """A data source failed. str() names the source; callers report it and go on."""


class FieldError(SourceError):
    """A response changed shape. The message lists the fields actually found."""


def _err():
    return FieldError


def need(obj, keys, what):
    if not isinstance(obj, dict):
        raise _err()("%s: expected an object, got %s" % (what, type(obj).__name__))
    miss = [k for k in keys if k not in obj]
    if miss:
        raise _err()("%s: missing %s; fields found: %s" % (what, ", ".join(miss), ", ".join(sorted(obj)[:40])))
    return obj


def num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    if s in ("", "-", "NA", "N/A", "nil", "None", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def nse_date(s):
    """'23-Nov-2026', '30-SEP-2026', '23-11-2026', '23-Nov-2026 15:30[:00]' -> date ISO 'YYYY-MM-DD' (or None)."""
    if not s or str(s).strip() in ("-", ""):
        return None
    s = str(s).strip()
    for f in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d %b %Y", "%d%b%Y"):
        try:
            return dt.datetime.strptime(s.title() if "%b" in f else s, f).date().isoformat()
        except ValueError:
            continue
    return None


def nse_time(s):
    """'18-Nov-2026 22:10:55' -> ISO IST datetime string (or None)."""
    for f in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            return dt.datetime.strptime(str(s).strip().title(), f).replace(tzinfo=IST).isoformat()
        except ValueError:
            continue
    d = nse_date(s)
    return d + "T00:00:00+05:30" if d else None


def _csv(text, need_cols, what):
    rd = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        head = [h.strip().upper() for h in next(rd)]
    except StopIteration:
        raise _err()(what + ": empty file")
    miss = [c for c in need_cols if c not in head]
    if miss:
        raise _err()("%s: missing %s; fields found: %s" % (what, ", ".join(miss), ", ".join(head)))
    ix = {h: i for i, h in enumerate(head)}
    for row in rd:
        if row and len(row) >= len(head) - 1:
            yield {h: (row[i].strip() if i < len(row) else "") for h, i in ix.items()}


# ---------------------------------------------------------------- universe
def parse_equity_l(text):
    out = []
    for r in _csv(text, ["SYMBOL", "NAME OF COMPANY", "SERIES", "DATE OF LISTING", "ISIN NUMBER", "FACE VALUE"], "EQUITY_L.csv"):
        out.append({"symbol": r["SYMBOL"], "name": r["NAME OF COMPANY"], "series": r["SERIES"],
                    "listed": nse_date(r["DATE OF LISTING"]), "isin": r["ISIN NUMBER"], "face_value": num(r["FACE VALUE"])})
    return out


KITE_COLS = ["instrument_token", "tradingsymbol", "name", "expiry", "tick_size", "instrument_type", "segment", "exchange"]


def parse_kite_instruments(text):
    """Kite /instruments/NSE CSV -> {'eq': {SYM: {token, tick, series, name, ksym}}, 'indices': {NAME: token}}.
    Kite writes EQ as the bare symbol and other series with a suffix (KAYA-BE, XYZ-SM); tick_size is in rupees."""
    eq, ind = {}, {}
    for r in _csv(text, [c.upper() for c in KITE_COLS], "Kite instruments"):
        seg, ks = r["SEGMENT"], r["TRADINGSYMBOL"]
        if seg == "INDICES":
            ind[ks.upper()] = r["INSTRUMENT_TOKEN"]
        elif seg == "NSE" and r["INSTRUMENT_TYPE"] == "EQ":
            m = re.match(r"^(.+?)(?:-(BE|SM|ST|BZ))?$", ks)
            if "-" in ks and not m.group(2):
                continue  # bonds, G-secs, other series (-N0, -SG, -GS ...)
            eq[m.group(1)] = {"token": r["INSTRUMENT_TOKEN"], "tick": num(r["TICK_SIZE"]) or None, "series": m.group(2) or "EQ",
                              "name": r["NAME"], "ksym": ks}
    if not eq:
        raise _err()("Kite instruments: no NSE equity rows")
    return {"eq": eq, "indices": ind}


def parse_kite_fo(text):
    """Kite /instruments/NFO CSV -> {UNDERLYING: [future expiry dates]} (F&O membership and expiries)."""
    fo = {}
    for r in _csv(text, [c.upper() for c in KITE_COLS], "Kite NFO instruments"):
        if r["INSTRUMENT_TYPE"] == "FUT" and r["EXPIRY"]:
            fo.setdefault(r["NAME"], set()).add(r["EXPIRY"][:10])
    return {k: sorted(v) for k, v in fo.items()}


def parse_holidays(doc):
    need(doc, ["CM"], "holiday-master")
    out = set()
    for h in doc["CM"]:
        d = nse_date(need(h, ["tradingDate"], "holiday-master CM row")["tradingDate"])
        if d:
            out.add(d)
    return out


# ---------------------------------------------------------------- end of day
def parse_bhavcopy(text):
    """sec_bhavdata_full_DDMMYYYY.csv -> {SYM: [series, o, h, l, c, volume, turnover ₹ lakhs, delivery %]} for
    equity series only (EQ, BE, SM, ST, BZ)."""
    cols = ["SYMBOL", "SERIES", "OPEN_PRICE", "HIGH_PRICE", "LOW_PRICE", "CLOSE_PRICE", "TTL_TRD_QNTY",
            "TURNOVER_LACS", "DELIV_PER"]
    out = {}
    for r in _csv(text, cols, "bhavcopy"):
        if r["SERIES"] not in ("EQ", "BE", "SM", "ST", "BZ"):
            continue
        o, h, l, c = (num(r[k]) for k in cols[2:6])
        if None in (o, h, l, c):
            continue
        out[r["SYMBOL"]] = [r["SERIES"], o, h, l, c, int(num(r["TTL_TRD_QNTY"]) or 0), num(r["TURNOVER_LACS"]),
                            num(r["DELIV_PER"])]
    if not out:
        raise _err()("bhavcopy: no equity rows")
    return out


def parse_index_close(text):
    cols = ["INDEX NAME", "OPEN INDEX VALUE", "HIGH INDEX VALUE", "LOW INDEX VALUE", "CLOSING INDEX VALUE"]
    return {r["INDEX NAME"]: [num(r[c]) for c in cols[1:]] for r in _csv(text, cols, "ind_close_all")
            if num(r["CLOSING INDEX VALUE"]) is not None}


# ---------------------------------------------------------------- quotes and bars
def parse_quote(doc):
    """NSE GetQuoteApi getSymbolData -> flat quote with sector, PE, 52-week range and price band."""
    need(doc, ["equityResponse"], "GetQuoteApi")
    if not doc["equityResponse"]:
        raise _err()("GetQuoteApi: empty equityResponse (unknown symbol?)")
    e = doc["equityResponse"][0]
    need(e, ["metaData", "tradeInfo", "priceInfo", "secInfo"], "GetQuoteApi equityResponse")
    if e["metaData"] is None:
        raise _err()("GetQuoteApi: NSE returned no data for this symbol/series (suspended, not traded, or another series)")
    m, t, p, s = e["metaData"], e["tradeInfo"], e["priceInfo"], e["secInfo"]
    need(m, ["symbol", "open", "dayHigh", "dayLow", "previousClose", "closePrice"], "GetQuoteApi metaData")
    band = str(p.get("priceBand") or "")
    lo, hi = (num(x) for x in band.split("-")) if re.match(r"^[\d.]+-[\d.]+$", band) else (None, None)
    ltp = num(t.get("lastPrice")) or num((e.get("orderBook") or {}).get("lastPrice")) or num(m["closePrice"])
    return {"symbol": m["symbol"], "name": m.get("companyName"), "series": m.get("series"), "ltp": ltp,
            "open": num(m["open"]), "high": num(m["dayHigh"]), "low": num(m["dayLow"]), "prev_close": num(m["previousClose"]),
            "vwap": num(m.get("averagePrice")), "pchange": num(m.get("pChange")), "volume": num(t.get("totalTradedVolume")),
            "value": num(t.get("totalTradedValue")), "deliv_pct": num(t.get("deliveryToTradedQuantity")),
            "mcap": num(t.get("totalMarketCap")), "ffmc": num(t.get("ffmc")), "face_value": num(t.get("faceValue")),
            "year_high": num(p.get("yearHigh")), "year_high_date": nse_date(p.get("yearHightDt")),
            "year_low": num(p.get("yearLow")), "year_low_date": nse_date(p.get("yearLowDt")),
            "tick": num(p.get("tickSize")), "band_low": lo, "band_high": hi, "band": band or None,
            "pe": num(s.get("pdSymbolPe")), "sector_pe": num(s.get("pdSectorPe")),
            "sector_index": (s.get("pdSectorInd") or "").strip() or None, "sector": s.get("sector"),
            "industry": s.get("industryInfo"), "basic_industry": s.get("basicIndustry"),
            "indices": s.get("indexList") or [], "status": s.get("isSuspended"), "updated": nse_time(e.get("lastUpdateTime"))}


def parse_kite_quote(data):
    """Kite /quote data {'NSE:INFY': {...}} -> flat quotes. ohlc.close is the previous close."""
    if not isinstance(data, dict):
        raise _err()("Kite quote: expected an object")
    out = []
    for key, q in data.items():
        need(q, ["instrument_token", "last_price", "ohlc"], "Kite quote " + key)
        o, dep = q["ohlc"] or {}, q.get("depth") or {}
        ks = key.split(":", 1)[-1]
        out.append({"symbol": re.sub(r"-(BE|SM|ST|BZ)$", "", ks), "ksym": ks, "token": str(q["instrument_token"]),
                    "ltp": num(q["last_price"]), "open": num(o.get("open")), "high": num(o.get("high")), "low": num(o.get("low")),
                    "prev_close": num(o.get("close")), "vwap": num(q.get("average_price")), "volume": num(q.get("volume")),
                    "band_low": num(q.get("lower_circuit_limit")), "band_high": num(q.get("upper_circuit_limit")),
                    "bid": num(((dep.get("buy") or [{}])[0]).get("price")), "ask": num(((dep.get("sell") or [{}])[0]).get("price")),
                    "updated": q.get("timestamp") or q.get("last_trade_time")})
    return out


def _kite_ts(t):
    t = str(t)
    if re.search(r"[+-]\d{4}$", t):
        t = t[:-2] + ":" + t[-2:]
    return dt.datetime.fromisoformat(t).astimezone(IST).isoformat()


def parse_kite_candles(data):
    """Kite historical data {'candles': [[ts, o, h, l, c, v], ...]} -> bars in IST."""
    need(data or {}, ["candles"], "Kite historical")
    out = []
    for r in data["candles"]:
        if len(r) < 6:
            raise _err()("Kite historical: row has %d fields, expected 6" % len(r))
        out.append([_kite_ts(r[0]), num(r[1]), num(r[2]), num(r[3]), num(r[4]), int(num(r[5]) or 0)])
    return out


def parse_yahoo_chart(doc):
    need(doc, ["chart"], "Yahoo chart")
    res = (doc["chart"].get("result") or [None])[0]
    if not res:
        raise _err()("Yahoo chart: %s" % ((doc["chart"].get("error") or {}).get("description") or "no result"))
    need(res, ["timestamp", "indicators"], "Yahoo chart result")
    q = res["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(res["timestamp"]):
        o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue
        t = dt.datetime.fromtimestamp(ts, IST).isoformat()
        out.append([t, round(o, 2), round(h, 2), round(l, 2), round(c, 2), int(v or 0)])
    return out


# ---------------------------------------------------------------- filings and events
def parse_announcements(rows):
    if not isinstance(rows, list):
        raise _err()("corporate-announcements: expected a list")
    out = []
    for r in rows:
        need(r, ["an_dt", "desc"], "corporate-announcements row")
        out.append({"time": nse_time(r["an_dt"]), "subject": r.get("desc") or "", "text": (r.get("attchmntText") or "")[:300],
                    "pdf": r.get("attchmntFile") if str(r.get("attchmntFile")).startswith("http") else None})
    return sorted(out, key=lambda x: x["time"] or "", reverse=True)


def parse_event_calendar(rows):
    if not isinstance(rows, list):
        raise _err()("event-calendar: expected a list")
    return [{"date": nse_date(need(r, ["date", "purpose"], "event-calendar row")["date"]), "kind": "board meeting",
             "what": r["purpose"], "detail": (r.get("bm_desc") or "")[:200]} for r in rows]


def parse_board_meetings(rows):
    if not isinstance(rows, list):
        raise _err()("corporate-board-meetings: expected a list")
    return [{"date": nse_date(need(r, ["bm_date", "bm_purpose"], "board-meetings row")["bm_date"]), "kind": "board meeting",
             "what": r["bm_purpose"], "detail": (r.get("bm_desc") or "")[:200]} for r in rows]


ACTION_KINDS = (("dividend", "dividend"), ("bonus", "bonus"), ("split", "split"), ("sub-division", "split"),
                ("buy back", "buyback"), ("buyback", "buyback"), ("rights", "rights"), ("agm", "AGM"),
                ("annual general", "AGM"), ("demerger", "demerger"))


def parse_corp_actions(rows):
    if not isinstance(rows, list):
        raise _err()("corporates-corporateActions: expected a list")
    out = []
    for r in rows:
        need(r, ["subject", "exDate"], "corporate-actions row")
        s = r["subject"] or ""
        kind = next((k for w, k in ACTION_KINDS if w in s.lower()), "action")
        out.append({"date": nse_date(r["exDate"]), "record_date": nse_date(r.get("recDate")), "kind": kind, "what": s})
    return out


def parse_results_cmp(doc):
    """results-comparision -> quarters oldest first; money in ₹ lakhs as filed."""
    need(doc, ["resCmpData"], "results-comparision")
    out = []
    for r in doc["resCmpData"] or []:
        need(r, ["re_to_dt", "re_net_profit"], "results-comparision row")
        rev = num(r.get("re_net_sale"))
        out.append({"end": nse_date(r["re_to_dt"]), "start": nse_date(r.get("re_from_dt")), "audited": r.get("re_res_type") == "A",
                    "revenue": rev if rev is not None else num(r.get("re_total_inc")), "total_income": num(r.get("re_total_inc")),
                    "pbt": num(r.get("re_pro_loss_bef_tax")), "net_profit": num(r.get("re_con_pro_loss")) or num(r.get("re_net_profit")),
                    "eps": num(r.get("re_diluted_eps")) if num(r.get("re_diluted_eps")) is not None else num(r.get("re_dilut_eps_for_cont_dic_opr")),
                    "filed": nse_date(r.get("re_create_dt"))})
    return sorted([q for q in out if q["end"]], key=lambda q: q["end"])


def parse_shareholding(rows):
    if not isinstance(rows, list):
        raise _err()("corporate-share-holdings-master: expected a list")
    out = []
    for r in rows:
        need(r, ["date", "pr_and_prgrp", "public_val"], "shareholding row")
        out.append({"date": nse_date(r["date"]), "promoter": num(r["pr_and_prgrp"]), "public": num(r["public_val"]),
                    "employee_trusts": num(r.get("employeeTrusts")), "xbrl": r.get("xbrl")})
    return sorted([x for x in out if x["date"]], key=lambda x: x["date"])


def parse_pit(doc):
    need(doc, ["data"], "corporates-pit")
    out = []
    for r in doc["data"] or []:
        need(r, ["acqName", "tdpTransactionType", "secAcq"], "corporates-pit row")
        out.append({"name": r["acqName"], "category": r.get("personCategory"), "type": r["tdpTransactionType"],
                    "qty": num(r["secAcq"]), "value": num(r.get("secVal")), "mode": r.get("acqMode"),
                    "date": nse_date(r.get("acqtoDt")) or nse_date(r.get("acqfromDt")), "disclosed": nse_date(r.get("intimDt")),
                    "after_pct": num(r.get("afterAcqSharesPer"))})
    return sorted(out, key=lambda x: x["date"] or "", reverse=True)


def parse_deals_csv(text, kind):
    cols = ["DATE", "SYMBOL", "CLIENT NAME", "BUY/SELL", "QUANTITY TRADED", "TRADE PRICE / WGHT. AVG. PRICE"]
    return [{"kind": kind, "date": nse_date(r["DATE"]), "symbol": r["SYMBOL"], "client": r["CLIENT NAME"],
             "side": r["BUY/SELL"].upper(), "qty": num(r["QUANTITY TRADED"]), "price": num(r["TRADE PRICE / WGHT. AVG. PRICE"])}
            for r in _csv(text, cols, kind + " deals csv") if r["SYMBOL"]]


def parse_fiidii(rows):
    if not isinstance(rows, list):
        raise _err()("fiidiiTradeReact: expected a list")
    return [{"category": need(r, ["category", "netValue"], "fiidii row")["category"], "date": nse_date(r.get("date")),
             "buy_cr": num(r.get("buyValue")), "sell_cr": num(r.get("sellValue")), "net_cr": num(r["netValue"])} for r in rows]


def parse_52w(doc):
    need(doc, ["data"], "52-week list")
    return [{"symbol": need(r, ["symbol", "ltp"], "52-week row")["symbol"], "ltp": num(r["ltp"]), "level": num(r.get("new52WHL")),
             "prev_level": num(r.get("prev52WHL")), "prev_date": nse_date(r.get("prevHLDate")), "pchange": num(r.get("pChange"))}
            for r in doc["data"]]


def parse_rss(data):
    """RSS 2.0 (Google News India) -> [{title, source, time (UTC ISO), link}]. Titles, source, time and link only."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise _err()("RSS: not XML (%s)" % e)
    out = []
    for it in root.iter("item"):
        title = html.unescape((it.findtext("title") or "").strip())
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        when = it.findtext("pubDate")
        try:
            t = email.utils.parsedate_to_datetime(when).astimezone(dt.timezone.utc).isoformat() if when else None
        except (TypeError, ValueError):
            t = None
        out.append({"title": title, "source": src or None, "time": t, "link": (it.findtext("link") or "").strip()})
    return out


def parse_integrated(rows):
    """GetQuoteApi getIntegratedFilingData (filings from 2025 on) -> quarters oldest first, ₹ lakhs as filed.
    Only total income is filed here (not revenue from operations), so 'revenue' carries total income."""
    if not isinstance(rows, list):
        raise _err()("getIntegratedFilingData: expected a list")
    out = []
    for r in rows:
        need(r, ["gfrQuaterEnded", "gfrConsolidated", "gfrTotalIncome", "gfrNetProLoss"], "integrated filing row")
        end = nse_date(r["gfrQuaterEnded"])
        if end:
            out.append({"end": end, "start": None, "basis": r["gfrConsolidated"], "audited": r.get("gfrAuditedUnaudited") == "Audited",
                        "revenue": num(r["gfrTotalIncome"]), "total_income": num(r["gfrTotalIncome"]), "pbt": num(r.get("gfrProBefTax")),
                        "net_profit": num(r["gfrNetProLoss"]), "eps": num(r.get("gfrErnPerShare")), "filed": nse_date(r.get("gfSystym"))})
    return sorted(out, key=lambda q: q["end"])
