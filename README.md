# nse-day-trader

12 Claude skills for **NSE (India) equity research and breakout tracking**. Scan every NSE stock from one
bhavcopy download a day, track breakouts live, analyze one stock end to end (technicals, filings, events,
news, data-based scenarios, chart), and plan, size, risk-check and ticket trades **that you place yourself**.

Python 3.8+, standard library only, nothing to install. Data: **Zerodha Kite Connect** by default (live quotes
and candles), NSE archives and nseindia.com, Yahoo `.NS` as the free fallback for bars, Google News (India).

> **Never places orders.** No script calls an order API. `/trader-ticket` prints instructions; you place
> the order in your broker app. **Not financial advice**: these tools read public data and do arithmetic.

## Install

```
/plugin marketplace add altafs45/trading-skills-
/plugin install nse-day-trader@nse-day-trader
```
Or copy the folders into `~/.claude/skills/`. Copy `lib/` too, because every script imports it:
```bash
git clone https://github.com/altafs45/trading-skills-.git
cp -r trading-skills-/trader-* trading-skills-/lib ~/.claude/skills/
```

### Kite (Zerodha), the default data source
You need a Kite Connect app (developers.kite.trade): its `api_key` and `api_secret`. Historical candles need
a plan that includes historical data. Put the keys in env vars (`KITE_API_KEY`, `KITE_API_SECRET`) or in
`~/.config/nse-day-trader/kite.json`, **never in chat**. Then once a day (tokens reset at 06:00 IST), in your
own terminal:
```bash
python3 lib/kite_login.py          # opens Kite login; paste the redirect URL back (hidden input)
python3 lib/kite_login.py --status
```
The pack only calls `/quote`, `/instruments` and `/instruments/historical`, never an order endpoint.
Not logged in? Everything still works: quotes come from NSE (delayed, at most 10 symbols per poll) and bars from
Yahoo (delayed). The output always names its source. Set `"data_source": "free"` in `trader/config.json` to skip Kite.

If the **claude.ai Kite connector** is connected, Claude may use its read-only market-data tools to cross-check
prices. The skills forbid its order and GTT tools.

### Your limits
```bash
mkdir -p trader && cp trader-budget/config.example.json trader/config.json   # rupees; edit it
```

## The twelve

| command | what it does |
| --- | --- |
| `/trader-scanner` | Universe (NSE EQUITY_L + Kite instruments, incl. SME) and a rolling 260-session bhavcopy store. Breakouts on 20/50-day and 52-week highs, tight base/VCP, volume + delivery surge, EMA stack, gap holds, inside bars and retests, scored 0-100. Then ORB, VWAP and PDH checks on the shortlist. |
| `/trader-track` | Live: 1m bars from polled LTP and volume, trend (HH/HL), swing S/R, pivots, VWAP, ORB, breakout confirmed/failed, circuit distance. Prints changes only; alerts ring once. |
| `/trader-analyze` | One stock in 40 lines or fewer: setup and base rates, bull/base/bear odds with invalidation, event risk, technicals (EMA, RSI, MACD, ATR, BB, ADX, OBV, delivery, RS vs NIFTY and sector, weekly and 5m), fundamentals, news, and an SVG chart. |
| `/trader-analyst` | Quarterly results from NSE integrated filings (QoQ, YoY, TTM), PE vs sector, promoter holding, insider trades. |
| `/trader-news` | Google News (India) + NSE announcements, tagged, new only; FII/DII flows. |
| `/trader-entry` | Waiting / triggered / expired on ORB or a level, completed bars only. |
| `/trader-exit` | Stop and target to the tick; refuses bad plans. |
| `/trader-timemachine` | 10,000 replays from the stock's own 5m candles plus the ORB rule on past sessions. |
| `/trader-budget` | Whole shares within four limits; one ticket. |
| `/trader-risk` | PASS/BLOCK: max loss, R:R, daily loss, trades/day, window, holidays, circuits, T2T series, event day, duplicates. |
| `/trader-ticket` | Plain-English ticket you place yourself; records your yes; journal of fills; exit ticket. |
| `/trader-alerts` | Price, stop, target, % move, time, opening bell; IST clock. |

## Data and efficiency

| need | source | cache |
| --- | --- | --- |
| all stocks EOD (OHLC, volume, delivery %) | `sec_bhavdata_full_DDMMYYYY.csv`, one file a day | `trader/cache/eod/` 260 sessions, gzip |
| index closes (NIFTY, sectors) | `ind_close_all_DDMMYYYY.csv` | same day file |
| universe, ticks, F&O expiries | `EQUITY_L.csv` + Kite `/instruments/NSE` and `/NFO` (public dump) | rebuilt when a session old |
| quote, sector, PE, 52w, band | `GetQuoteApi getSymbolData` | 5 min (10 s in track) |
| results | `GetQuoteApi getIntegratedFilingData` (fallback `results-comparision`) | day |
| events | `event-calendar`, `corporate-board-meetings`, `corporates-corporateActions`, announcements | day |
| holdings, insiders | `corporate-share-holdings-master`, `corporates-pit` | day |
| deals, FII/DII, holidays | `bulk.csv`, `block.csv`, `fiidiiTradeReact`, `holiday-master` | day (deals accumulate) |
| live quotes / candles | Kite `/quote` (500 per request, 1/s) / `/instruments/historical` (3/s) | live / 60 s |
| bars without a Kite login | Yahoo `SYMBOL.NS` (delayed) | 60 s live, else day |

nseindia.com requests are spaced at least 1 second apart through one cookie session. Every nseindia.com endpoint is
unofficial. Each parser checks its fields and stops with `fields found: ...` if NSE changes a response, so it
never guesses. `quote-equity` returned 403 when checked live (2026-11-24), so the pack uses `GetQuoteApi`.

## A day with it
```bash
python3 trader-scanner/scan.py eod && python3 trader-scanner/scan.py daily      # before 09:15
python3 trader-news/news.py                                                     # what moved them
python3 trader-analyze/analyze.py CHALET                                        # one name, deeply
python3 trader-track/track.py                                                   # 09:15-15:30, changes only
python3 trader-entry/entry.py check CHALET --setup level --level 840.40
python3 trader-exit/exit.py plan --write && python3 trader-timemachine/timemachine.py run
python3 trader-budget/size.py --write && python3 trader-risk/check.py && python3 trader-ticket/ticket.py show
```

## Tests
```bash
python3 -m unittest discover -s tests -v
```
Offline, on **synthetic fixtures** (`tests/fixtures/`, every file labelled FAKE). They cover every parser
(using the real field names), each indicator against hand-computed values, the breakout rules, scoring,
base rates and scenarios, the chart writer, and the logic of every skill.

## Fine print
- **Not financial advice.** Most day traders lose money. Outlooks are historical frequencies from the stock's own data, not forecasts.
- **A stop is a plan, not a guarantee.** Gaps, circuits and fast markets fill past stops.
- **MIS** positions are auto squared off by brokers around 15:15-15:20 IST. The default flat-by time is 15:10.
- **BE/SM/ST series** are trade-for-trade (no intraday). They are excluded by default and blocked for MIS.
- **Free data is delayed and unofficial.** Check anything important against your broker before you act.
- NSE's PIT (insider) feed and the old `results-comparision` feed were found lagging when checked. The scripts print how fresh they are.

## Credits
NSE edition by altafs45. Based on the MIT-licensed
[day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) by Jake Schincariol. MIT.
