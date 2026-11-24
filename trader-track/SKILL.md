---
name: trader-track
description: >-
  Track Mode (NSE). Live tracker for a watchlist: polls quotes (Kite, up to 500 symbols per request,
  every 15 s by default), builds 1-minute bars from LTP and volume deltas, re-seeded from candles
  every 5 minutes, and prints only what changed: trend from swing highs/lows, swing support and
  resistance, floor pivots, VWAP, opening-range status, distance to the breakout level, breakout
  confirmed or failed on 5-minute closes, circuit proximity. Rings once for breakout, failure,
  volume spike, near circuit, stop or target. Use when the user says "track these stocks", "watch my
  watchlist live", "monitor the breakout", "is the breakout holding", "live structure", "tell me if
  it fails", or after /trader-scanner.
---
# Track Mode (NSE)

```bash
python3 trader-track/track.py                         # top 8 of trader/watchlist.json, levels from the scanner
python3 trader-track/track.py --symbols CHALET,TCS --every 15 --loops 40
python3 trader-track/track.py --once                  # one snapshot
```
Outside market hours it prints one snapshot of the latest session and does not ring alerts. During the session it loops until 15:30 or `--loops`. Run it in the background and read its output as it changes. State is saved in `trader/track.json`.

## Reading a line
`HH:MM SYMBOL ltp | trend uptrend/downtrend/range | ORB above/inside/below | above/below VWAP | lvl L (+x%, confirmed/failed/none) | S / R | UC y% away [what changed]`
- confirmed = the latest 5m close is above the level; failed = it broke and the latest 5m close is back below.
- RING lines are alerts, each once per day (volume spikes once per bar). If the plan's symbol is tracked, stop and target ring too.
Without a Kite login it uses delayed NSE quotes for at most 10 symbols. Say so.

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
