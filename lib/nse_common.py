"""Shared core for nse-day-trader: IST clock, NSE calendar, ticks, Rupee format,
HTTP with rate limits and a dated disk cache, the nseindia.com session, the
Kite Connect client (market data only), Yahoo .NS fallback bars, the
universe and the end-of-day store. Python 3.8+, standard library only.

Nothing in this file (or this pack) places, modifies or cancels an order.
"""

import csv, datetime as dt, gzip, hashlib, io, json, os, re
import http.cookiejar as cookiejar
import sys, time, urllib.error, urllib.parse, urllib.request
from collections import deque
from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nse_parsers as P  # noqa: E402

for _s in (sys.stdout, sys.stderr):  # ₹ on Windows consoles
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
OPEN, CLOSE, PREOPEN = dt.time(9, 15), dt.time(15, 30), dt.time(9, 0)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
NOTE_NFA = "Not financial advice: data and arithmetic only; you decide and you place any order."

# Fallback only: NSE trading holidays (Capital Market) fetched live from
# nseindia.com/api/holiday-master?type=trading on 2026-11-24. The live list
# is refreshed weekly into trader/cache/holidays.json and wins over this.
FALLBACK_HOLIDAYS = {
    "2026-01-15", "2026-01-26", "2026-02-15", "2026-03-03", "2026-03-21", "2026-03-26", "2026-03-31",
    "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-08-15", "2026-09-14",
    "2026-10-02", "2026-10-20", "2026-11-08", "2026-11-10", "2026-11-24", "2026-12-25"}


SourceError, FieldError, require = P.SourceError, P.FieldError, P.need


# ---------------------------------------------------------------- paths, json
def data_dir():
    return os.environ.get("NSE_TRADER_DIR") or "trader"


def path(*parts):
    p = os.path.join(data_dir(), *parts)
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    return p


def read_json(p, default=None):
    try:
        if p.endswith(".gz"):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                return json.load(f)
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(p, obj, compact=False):
    d = os.path.dirname(p)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = p + ".tmp"
    kw = {"separators": (",", ":")} if compact else {"indent": 1}
    if p.endswith(".gz"):
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(obj, f, **kw)
    else:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, **kw)
    os.replace(tmp, p)
    return p


def load_config():
    cfg = read_json(path("config.json"), {}) or {}
    return cfg


# ---------------------------------------------------------------- clock
def now_ist(text=None):
    """Current IST time, or a fixed time from 'YYYY-MM-DD HH:MM' (or env NSE_NOW) for replays/tests."""
    text = text or os.environ.get("NSE_NOW")
    if text:
        return dt.datetime.strptime(text.strip()[:16].replace("T", " "), "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    return dt.datetime.now(IST)


def iso(t):
    return t.astimezone(IST).isoformat(timespec="seconds")


def parse_iso(s):
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=IST)


def holidays(refresh=False, web=None, now=None):
    """Trading holidays as a set of 'YYYY-MM-DD'. Live list cached weekly, fallback merged in."""
    p = path("cache", "holidays.json")
    doc = read_json(p)
    now = now or now_ist()
    fresh = doc and (now - parse_iso(doc["fetched_at"])).days < 7
    if (refresh or not fresh) and web is not None:
        try:
            days = P.parse_holidays(web.api("/api/holiday-master", type="trading"))
            doc = {"fetched_at": iso(now), "source": "nseindia.com holiday-master", "days": sorted(days)}
            write_json(p, doc)
        except SourceError:
            pass
    return set(FALLBACK_HOLIDAYS) | set((doc or {}).get("days", []))


_HOL = None


def is_trading_day(d, hol=None):
    global _HOL
    if hol is None:
        _HOL = _HOL if _HOL is not None else holidays()
        hol = _HOL
    return d.weekday() < 5 and d.isoformat() not in hol


def prev_trading_day(d, hol=None):
    d -= dt.timedelta(days=1)
    while not is_trading_day(d, hol):
        d -= dt.timedelta(days=1)
    return d


def trading_days_back(end, n, hol=None):
    """The n trading days ending at end (inclusive if end trades), oldest first."""
    out, d = [], end
    while len(out) < n:
        if is_trading_day(d, hol):
            out.append(d)
        d -= dt.timedelta(days=1)
    return out[::-1]


def market_status(now=None, hol=None):
    now = now or now_ist()
    d, t = now.date(), now.time()
    if not is_trading_day(d, hol):
        return {"state": "closed", "why": "holiday" if d.weekday() < 5 else "weekend", "date": d.isoformat()}
    if t < PREOPEN:
        state = "before pre-open"
    elif t < OPEN:
        state = "pre-open"
    elif t < CLOSE:
        state = "open"
    else:
        state = "closed"
    return {"state": state, "why": "session" if state != "closed" else "after close", "date": d.isoformat()}


def last_completed_session(now=None, hol=None):
    now = now or now_ist()
    d = now.date()
    if is_trading_day(d, hol) and now.time() >= dt.time(18, 0):
        return d
    return prev_trading_day(d, hol)


def hhmm(text):
    m = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", str(text).strip())
    if not m:
        raise ValueError("time must be HH:MM, got %r" % text)
    return dt.time(int(m.group(1)), int(m.group(2)))


# ---------------------------------------------------------------- ticks, money
def tick_for(price, tick=None):
    """Tick size: the instrument's own (Kite instruments) if known, else NSE's price-band table (fallback)."""
    if tick:
        return Decimal(str(tick))
    p = float(price)
    for lim, t in ((250, "0.01"), (1000, "0.05"), (5000, "0.10"), (10000, "0.50"), (20000, "1.00")):
        if p < lim:
            return Decimal(t)
    return Decimal("5.00")


def round_tick(price, tick=None, mode="near"):
    t = tick_for(price, tick)
    q = Decimal(str(price)) / t
    q = q.to_integral_value(rounding={"down": ROUND_DOWN, "up": ROUND_UP}.get(mode, ROUND_HALF_UP))
    return float(q * t)


def inr(x, dp=2):
    """Indian digit grouping: 12,34,567.89"""
    if x is None:
        return "n/a"
    neg, x = x < 0, abs(float(x))
    s = ("%.*f" % (dp, x))
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        whole = head + "," + tail
    return ("-" if neg else "") + "₹" + whole + ("." + frac if frac else "")


def inr_short(x):
    if x is None:
        return "n/a"
    a = abs(x)
    if a >= 1e7:
        return "%s%s Cr" % ("-" if x < 0 else "", inr(a / 1e7, 0 if a >= 1e10 else 2))
    if a >= 1e5:
        return "%s%s L" % ("-" if x < 0 else "", inr(a / 1e5))
    return inr(x)


def pct(a, b):
    return None if a is None or not b else (a / b - 1) * 100


# ---------------------------------------------------------------- http
class Limiter(object):
    """Sliding-window limits, e.g. [(3, 1.0), (180, 60.0)] = 3/s and 180/min; [(1, 1.0)] = one per second."""

    def __init__(self, rules, sleep=time.sleep, clock=time.monotonic):
        self.rules, self.sleep, self.clock = rules, sleep, clock
        self.hist = deque(maxlen=max(n for n, _ in rules))

    def wait(self):
        while True:
            now, delay = self.clock(), 0.0
            for n, win in self.rules:
                recent = [t for t in self.hist if now - t < win]
                if len(recent) >= n:
                    delay = max(delay, win - (now - recent[-n]))
            if delay <= 0:
                self.hist.append(now)
                return
            self.sleep(delay)


NSE_LIMIT = Limiter([(1, 1.05)])
YAHOO_LIMIT = Limiter([(2, 1.0)])
GNEWS_LIMIT = Limiter([(1, 1.0)])


def http(url, data=None, headers=None, opener=None, limiter=None, timeout=30, source="http"):
    if limiter:
        limiter.wait()
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9", "Accept-Encoding": "gzip"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
    for attempt in (0, 1):
        try:
            with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":
                    body = gzip.decompress(body)
                return body
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt == 0:
                time.sleep(3)
                continue
            raise SourceError("%s: HTTP %s" % (source, e.code))
        except (urllib.error.URLError, OSError) as e:
            if attempt == 0:
                time.sleep(2)
                continue
            raise SourceError("%s: %s" % (source, getattr(e, "reason", e)))


def cached(p, ttl, fetch, now=None):
    """Disk cache. ttl: 'day' (same IST date), seconds (int), or 0 (always fetch).
    Returns (data, fetched_at_iso, from_cache)."""
    now = now or now_ist()
    doc = read_json(p)
    if doc and ttl:
        t = parse_iso(doc["fetched_at"])
        ok = t.date() == now.date() if ttl == "day" else (now - t).total_seconds() < ttl
        if ok:
            return doc["data"], doc["fetched_at"], True
    data = fetch()
    write_json(p, {"fetched_at": iso(now), "data": data}, compact=True)
    return data, iso(now), False


class NSEWeb(object):
    """nseindia.com (unofficial endpoints). Warms a cookie session on a quote page, spaces requests >=1 s."""
    BASE = "https://www.nseindia.com"

    def __init__(self, limiter=NSE_LIMIT):
        self.jar = cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.lim, self.warm = limiter, False

    def _warm(self, symbol="INFY"):
        http(self.BASE + "/get-quotes/equity?symbol=" + symbol, opener=self.op, limiter=self.lim,
             headers={"Accept": "text/html"}, source="nseindia.com session")
        self.warm = True

    def api(self, endpoint, **params):
        url = self.BASE + endpoint + ("?" + urllib.parse.urlencode(params) if params else "")
        ref = {"Referer": self.BASE + "/get-quotes/equity?symbol=" + params.get("symbol", "INFY")}
        for attempt in (0, 1):
            if not self.warm or attempt:
                self._warm(params.get("symbol", "INFY"))
            try:
                body = http(url, opener=self.op, limiter=self.lim, headers=ref, source="nseindia.com" + endpoint)
                return json.loads(body.decode("utf-8"))
            except SourceError:
                if attempt:
                    raise
            except ValueError:
                raise SourceError("nseindia.com%s: not JSON" % endpoint)

    def archive(self, url, source=None):
        return http(url, opener=self.op, limiter=self.lim, source=source or url.split("/")[-1])

    def quote(self, symbol, series="EQ"):
        """Live-ish quote + sector/PE/52w/band from GetQuoteApi (quote-equity returns 403 since 2026)."""
        return P.parse_quote(self.api("/api/NextApi/apiClient/GetQuoteApi", functionName="getSymbolData",
                                      marketType="N", series=series or "EQ", symbol=symbol))


# ---------------------------------------------------------------- Kite Connect (Zerodha), market data only
KITE = "https://api.kite.trade"
KITE_INSTRUMENTS = KITE + "/instruments/%s"  # public CSV dump, no login needed
KITE_LOGIN = "https://kite.zerodha.com/connect/login?v=3&api_key=%s"
KITE_INTERVALS = {"1m": ("minute", 60), "3m": ("3minute", 100), "5m": ("5minute", 100), "15m": ("15minute", 200),
                  "1h": ("60minute", 400), "1d": ("day", 2000)}
CRED_FILE = os.path.join(os.path.expanduser("~"), ".config", "nse-day-trader", "kite.json")


def kite_reset(now):
    """Kite access tokens expire at 06:00 IST every day."""
    r = now.replace(hour=6, minute=0, second=0, microsecond=0)
    return r if now >= r else r - dt.timedelta(days=1)


def kite_creds(now=None):
    """api_key + access_token from env (KITE_API_KEY, KITE_ACCESS_TOKEN) or ~/.config/nse-day-trader/kite.json.
    A saved token from before today's 06:00 IST reset counts as expired. Returns None when unusable. Never printed."""
    if (load_config().get("data_source") or "kite") == "free":
        return None
    env = {"api_key": os.environ.get("KITE_API_KEY"), "access_token": os.environ.get("KITE_ACCESS_TOKEN")}
    if all(env.values()):
        return env
    f = read_json(CRED_FILE, {}) or {}
    c = {"api_key": env["api_key"] or f.get("api_key"), "access_token": env["access_token"] or f.get("access_token")}
    if not all(c.values()):
        return None
    if c["access_token"] == f.get("access_token") and f.get("token_at"):
        if parse_iso(f["token_at"]) < kite_reset(now or now_ist()):
            return None
    return c


def kite_checksum(api_key, request_token, api_secret):
    return hashlib.sha256((api_key + request_token + api_secret).encode("utf-8")).hexdigest()


def kite_session(api_key, api_secret, request_token):
    """Exchange the one-time request_token for today's access_token (POST /session/token)."""
    body = urllib.parse.urlencode({"api_key": api_key, "request_token": request_token,
                                   "checksum": kite_checksum(api_key, request_token, api_secret)}).encode()
    raw = http(KITE + "/session/token", data=body, source="Kite login",
               headers={"X-Kite-Version": "3", "Content-Type": "application/x-www-form-urlencoded"})
    d = json.loads(raw.decode("utf-8"))
    return require(d.get("data") or {}, ["access_token"], "Kite login")["access_token"]


class Kite(object):
    """Quotes (500 instruments per request, 1 request/s) and historical candles (3 requests/s). No order calls."""

    def __init__(self, creds):
        self.c = creds
        self.q_lim, self.h_lim = Limiter([(1, 1.0)]), Limiter([(3, 1.0)])

    def _get(self, ep, params, lim, what):
        url = KITE + ep + "?" + urllib.parse.urlencode(params, doseq=True)
        hdr = {"X-Kite-Version": "3", "Authorization": "token %s:%s" % (self.c["api_key"], self.c["access_token"])}
        try:
            raw = http(url, headers=hdr, limiter=lim, source=what)
        except SourceError as e:
            if "HTTP 403" in str(e):
                raise SourceError("%s (token expired, or the plan lacks this data): run python3 lib/kite_login.py" % e)
            raise
        try:
            d = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise SourceError(what + ": not JSON")
        if d.get("status") != "success":
            raise SourceError("%s: %s" % (what, d.get("message") or "failed"))
        return d.get("data")

    def quote(self, ksyms):
        """ksyms: Kite trading symbols ('INFY', 'KAYA-BE')."""
        out = []
        for i in range(0, len(ksyms), 500):
            out += P.parse_kite_quote(self._get("/quote", {"i": ["NSE:" + s for s in ksyms[i:i + 500]]}, self.q_lim, "Kite quote"))
        return out

    def candles(self, token, interval, start, end):
        name, maxdays = KITE_INTERVALS[interval]
        bars, a = [], start
        while a <= end:
            b = min(end, a + dt.timedelta(days=maxdays))
            d = self._get("/instruments/historical/%s/%s" % (token, name),
                          {"from": a.strftime("%Y-%m-%d %H:%M:%S"), "to": b.strftime("%Y-%m-%d %H:%M:%S")}, self.h_lim, "Kite historical")
            bars += P.parse_kite_candles(d)
            a = b + dt.timedelta(minutes=1)
        return bars


_KITE = None


def kite():
    """A Kite client when today's access token exists (and data_source is not 'free'), else None: callers use NSE/Yahoo."""
    global _KITE
    if _KITE is None:
        c = kite_creds()
        _KITE = Kite(c) if c else False
    return _KITE or None


# ---------------------------------------------------------------- bars
YAHOO = "https://query2.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=%s"


def yahoo_bars(symbol, interval="5m", days=5):
    ysym = symbol if symbol.startswith("^") else urllib.parse.quote(symbol) + ".NS"
    if interval == "1d":
        rng = "1y" if days <= 250 else "2y" if days <= 500 else "5y"
    else:
        rng = "%dd" % min(days, 7 if interval == "1m" else 60)
    body = http(YAHOO % (ysym, rng, interval), limiter=YAHOO_LIMIT, headers={"Referer": "https://finance.yahoo.com/"},
                source="Yahoo chart " + ysym)
    return P.parse_yahoo_chart(json.loads(body.decode("utf-8")))


def get_bars(symbol, interval="5m", days=5, now=None, source="auto", token=None):
    """OHLCV bars [iso_ist, o, h, l, c, v], oldest first. Kite historical when logged in (needs the instrument
    token), else Yahoo .NS (delayed). If Kite fails, falls back to Yahoo and the source label says why.
    Cached: 60 s while the market is open, else for the day."""
    now = now or now_ist()
    live = market_status(now)["state"] == "open"
    ttl = 60 if live else "day"
    why = ""
    if source in ("auto", "kite") and kite() and token:
        start = dt.datetime.combine(now.date() - dt.timedelta(days=int(days * 1.6) + 3), OPEN)
        try:
            bars, fetched, _ = cached(path("cache", "bars", "%s_%s_%d_kite.json" % (symbol, interval, days)), ttl,
                                      lambda: kite().candles(token, interval, start, now.replace(tzinfo=None)), now)
            return {"symbol": symbol, "interval": interval, "source": "Kite", "fetched_at": fetched, "bars": bars}
        except SourceError as e:
            why = " (Kite failed: %s)" % e
    bars, fetched, _ = cached(path("cache", "bars", "%s_%s_%d_yahoo.json" % (symbol, interval, days)), ttl,
                              lambda: yahoo_bars(symbol, interval, days), now)
    return {"symbol": symbol, "interval": interval, "source": "Yahoo (delayed)" + why, "fetched_at": fetched, "bars": bars}


def session_bars(bars, day):
    k = day.isoformat()
    return [b for b in bars if b[0][:10] == k]


def days_in(bars):
    return sorted({b[0][:10] for b in bars})


# ---------------------------------------------------------------- universe
EQUITY_L = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def build_universe(web, now=None, log=print):
    now = now or now_ist()
    errors = []
    eq = P.parse_equity_l(web.archive(EQUITY_L, "NSE EQUITY_L.csv").decode("utf-8", "replace"))
    try:
        km = P.parse_kite_instruments(http(KITE_INSTRUMENTS % "NSE", timeout=120, source="Kite instruments NSE").decode("utf-8"))
    except SourceError as e:
        errors.append(str(e))
        km = {"eq": {}, "indices": {}}
    try:
        fo = P.parse_kite_fo(http(KITE_INSTRUMENTS % "NFO", timeout=120, source="Kite instruments NFO").decode("utf-8"))
    except SourceError as e:
        errors.append(str(e))
        fo = {}
    old = read_json(path("cache", "sectors.json"), {}) or {}
    rows = {}
    for r in eq:
        s = r["symbol"]
        if r["series"] not in ("EQ", "BE", "SM", "ST", "BZ"):
            continue
        k = km["eq"].get(s, {})
        r.update(token=k.get("token"), tick=k.get("tick"), ksym=k.get("ksym") or s, fo=s in fo,
                 intraday_ok=r["series"] == "EQ", etf=bool(re.search(r"\bETF\b|BEES", r["name"], re.I)))
        r.update(old.get(s, {}))
        rows[s] = r
    for s, k in km["eq"].items():  # SME (SM/ST) and others that EQUITY_L does not list
        if s not in rows and k["series"] in ("SM", "ST", "BE", "BZ"):
            rows[s] = {"symbol": s, "name": k["name"], "series": k["series"], "listed": None, "isin": None, "face_value": None,
                       "token": k["token"], "tick": k["tick"], "ksym": k["ksym"], "fo": False, "intraday_ok": False,
                       "etf": False, "source": "Kite instruments"}
            rows[s].update(old.get(s, {}))
    doc = {"built_at": iso(now), "session": last_completed_session(now).isoformat(),
           "sources": ["NSE EQUITY_L.csv", "Kite instruments NSE + NFO"], "errors": errors,
           "count": len(rows), "symbols": rows, "indices": km["indices"], "fo_expiries": fo}
    write_json(path("cache", "universe.json"), doc, compact=True)
    return doc


def load_universe(web=None, refresh=False, now=None):
    now = now or now_ist()
    doc = read_json(path("cache", "universe.json"))
    stale = not doc or doc.get("session", "") < prev_trading_day(last_completed_session(now)).isoformat()
    if refresh or stale:
        if web is None:
            if doc:
                return doc
            raise SourceError("universe: no cache yet; run scan.py universe")
        return build_universe(web, now)
    return doc


def remember_sector(symbol, q):
    p = path("cache", "sectors.json")
    s = read_json(p, {}) or {}
    s[symbol] = {k: q.get(k) for k in ("sector", "industry", "basic_industry", "sector_index") if q.get(k)}
    write_json(p, s, compact=True)


# ---------------------------------------------------------------- end-of-day store
BHAV = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_%s.csv"
INDCLOSE = "https://nsearchives.nseindia.com/content/indices/ind_close_all_%s.csv"
KEEP = 260


def eod_file(d):
    return os.path.join(data_dir(), "cache", "eod", d.isoformat() + ".json.gz")


def eod_update(web, sessions=KEEP, now=None, log=print):
    now = now or now_ist()
    hol = holidays(web=web, now=now)
    want = trading_days_back(last_completed_session(now, hol), sessions, hol)
    added, missing = [], []
    for d in want:
        f = eod_file(d)
        if os.path.exists(f):
            continue
        tag = d.strftime("%d%m%Y")
        try:
            rows = P.parse_bhavcopy(web.archive(BHAV % tag, "bhavcopy " + tag).decode("utf-8", "replace"))
        except SourceError as e:
            missing.append("%s (%s)" % (d, e))
            continue
        try:
            idx = P.parse_index_close(web.archive(INDCLOSE % tag, "index close " + tag).decode("utf-8", "replace"))
        except SourceError as e:
            idx, _ = {}, log("  index closes missing for %s: %s" % (d, e))
        write_json(f, {"date": d.isoformat(), "source": "NSE sec_bhavdata_full + ind_close_all", "rows": rows,
                       "indices": idx}, compact=True)
        added.append(d.isoformat())
        if len(added) % 20 == 0:
            log("  stored %d sessions..." % len(added))
    keep = {eod_file(d) for d in want}
    folder = os.path.join(data_dir(), "cache", "eod")
    for n in os.listdir(folder) if os.path.isdir(folder) else []:
        if os.path.join(folder, n) not in keep and n.endswith(".json.gz") and n[:10] < want[0].isoformat():
            os.remove(os.path.join(folder, n))
    have = len([n for n in os.listdir(folder)]) if os.path.isdir(folder) else 0
    return {"added": added, "missing": missing, "have": have, "through": want[-1].isoformat()}


FIELDS = ("o", "h", "l", "c", "v", "t", "dp")


def eod_load(sessions=KEEP, symbols=None):
    """-> (dates, {sym: {'d': [...], 'series': s, 'o','h','l','c','v','t' (turnover ₹ lakhs),'dp' (delivery %)}},
    {index: {'d': [...], 'c': [...]}})"""
    folder = os.path.join(data_dir(), "cache", "eod")
    files = sorted(n for n in os.listdir(folder) if n.endswith(".json.gz"))[-sessions:] if os.path.isdir(folder) else []
    want = set(symbols) if symbols else None
    out, idx, dates = {}, {}, []
    for n in files:
        doc = read_json(os.path.join(folder, n))
        if not doc:
            continue
        d = doc["date"]
        dates.append(d)
        for s, r in doc["rows"].items():
            if want and s not in want:
                continue
            x = out.get(s)
            if x is None:
                x = out[s] = {"d": [], "series": r[0], **{k: [] for k in FIELDS}}
            x["d"].append(d)
            x["series"] = r[0]
            for k, v in zip(FIELDS, r[1:]):
                x[k].append(v)
        for name, v in (doc.get("indices") or {}).items():
            y = idx.setdefault(name.upper(), {"d": [], "c": []})
            y["d"].append(d)
            y["c"].append(v[3])
    return dates, out, idx
