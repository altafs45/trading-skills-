---
name: trader-entry
description: >-
  Entry Timer (NSE, long only). Watches a setup on completed 5-minute (or 1/15-minute) bars and says
  waiting, triggered, expired or not open: an opening-range breakout (first 15 minutes by default)
  or a close above a level you give (like the scanner's breakout level), with an optional volume
  check, inside your entry window. Knows NSE hours (09:15-15:30 IST) and holidays. Writes
  trader/entry.json for /trader-exit. Never places an order. Use when the user says "tell me when to
  get in", "watch RELIANCE", "has it broken out", "did it break the opening range", "entry signal",
  "time my entry", or after /trader-scanner.
---
# Entry Timer (NSE)

```bash
python3 trader-entry/entry.py check RELIANCE                       # ORB on 5m bars
python3 trader-entry/entry.py check CHALET --setup level --level 840.40 --vol-mult 1.5
python3 trader-entry/entry.py watch RELIANCE --every 30 --max-minutes 120
python3 trader-entry/entry.py check RELIANCE --now "2026-11-23 10:20"   # replay a past moment
```
Only bars that have closed count. The entry window comes from `trader/config.json` → `entry_window` (default 09:30-14:30 IST).

## States
- **waiting**: the opening range is still forming, or the last close is under the level (it says how far).
- **triggered**: the first close above the level, its time and price. It writes `trader/entry.json`. Next is `/trader-exit`.
- **expired**: no trigger before the cutoff, or the first trigger came after it.
- **not open**: before 09:15, a weekend or an NSE holiday.

Bars come from Kite when logged in, else Yahoo (delayed, can lag a few minutes). Say which.

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
