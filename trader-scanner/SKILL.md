---
name: trader-scanner
description: >-
  Chart Scanner (NSE). Scans every NSE equity for breakouts from one bhavcopy download per day:
  20/50-day and 52-week closing highs, tight-base / VCP breakouts, volume surges (2x the 20-day
  average with delivery % above its own average), EMA 20/50/200 trend, gap-ups that held, inside-bar
  breakouts and retests of a broken level, scored 0-100 with reasons; then an intraday pass on the
  shortlist (opening-range breakout, VWAP reclaim, prior-day-high break, relative volume). Liquidity
  filters on price and rupee turnover; BE/SM and ETFs excluded by default. Writes
  trader/watchlist.json. Use when the user says "scan the market", "scan NSE", "find breakouts",
  "what's breaking out", "52 week high stocks", "volume surge", "VCP", "build my watchlist", "pre-
  market scan", "opening range breakouts", or at the start of the trading day.
---
# Chart Scanner (NSE)

```bash
python3 trader-scanner/scan.py universe            # NSE EQUITY_L + Kite instruments (tokens, ticks, SME, F&O); auto-rebuilds
python3 trader-scanner/scan.py eod                 # rolling 260-session bhavcopy store in trader/cache/eod/ (first run ~15 min, then 1 file/day)
python3 trader-scanner/scan.py daily --top 30      # rank today's setups -> trader/watchlist.json
python3 trader-scanner/scan.py intraday --top 15   # ORB / VWAP reclaim / prior-day high / RVOL on the shortlist (5m bars)
```
Options for `daily`: `--min-price 20`, `--min-turnover-cr 5`, `--base-days 15`, `--base-max-pct 10`, `--vol-mult 2`, `--include-be-sm`. Defaults also come from `trader/config.json` → `"scanner"`.

## Workflow
1. Before the open: `eod` (fetches only the missing sessions), then `daily`. If it says fewer than ~250 sessions are stored, tell the user the 52-week and EMA200 rules are limited until `eod` finishes.
2. After 09:30 IST: `intraday` on the top names. Bars come from Kite when logged in, else Yahoo (delayed), and the output says which.
3. Hand off: `/trader-news` on the list, `/trader-analyze SYMBOL` for one name, `/trader-track` to watch live, `/trader-entry` to time an entry.

## Reading the output
One line per stock: symbol, headline setup, score, breakout level, % above it, RVOL. The score adds points for each rule that fired (52w high 30, 50d 20, 20d 12 — only the highest counts; tight base 15 +5 VCP; volume 15 +5 delivery; EMA stack 15 or above all EMAs 8; retest 10; gap 6; inside bar 6), capped at 100. A high score means many conditions fired, not that the price will rise.

## Rules for Claude
- Run the script and read its printed summary. Do not open the JSON files unless the user asks for a detail that is not in the summary.
- Quote numbers exactly as printed, with their source and time. If a line says `source failed`, say which source and carry on with the rest. Never fill a gap with a guess.
- Every nseindia.com endpoint is unofficial: if a script stops with `fields found: ...`, report that line; do not guess the new field names.
- Never place, modify or cancel an order, by any API, plugin or connector. The user places orders in their own broker app.
- Data source: Kite (Zerodha) by default. Scripts use it when today's token exists, else fall back to NSE/Yahoo (delayed) and say so. If a script says the Kite token expired, ask the user to run `python3 lib/kite_login.py` themselves in a terminal. Never ask for, print or store Kite keys, secrets, request tokens or access tokens in chat.
- If the claude.ai Kite connector is connected, you may use its read-only market-data tools (quotes, LTP, OHLC, historical candles, instrument search) to cross-check prices, and holdings or positions only when the user asks. Never call its order or GTT tools (place, modify, cancel).
- Talk about scenarios and historical frequencies, never "it will go up", never buy/sell advice. End with: not financial advice.
- Scripts live next to this file; shared code is in `../lib/`. Run them from the user's project folder (data goes to `trader/`). Python 3.8+, no installs.

Not financial advice: these tools read public data and do arithmetic. Most day traders lose money.
