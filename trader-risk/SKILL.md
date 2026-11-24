---
name: trader-risk
description: >-
  Risk Manager (NSE). PASS or BLOCK for every ticket before it can become an order. It checks: a
  stop is required; loss at the stop within the max loss per trade (from the higher of the entry and
  a fresh price); reward:risk at or above your minimum; today's losses plus approved risk within the
  daily loss limit; trades per day; the entry window and NSE hours and holidays; blocked symbols;
  order value, position cap and cash buffer; tick-size multiples; no intraday on BE/SM trade-for-
  trade series; target not beyond the upper circuit and price not near it; no results or board
  meeting today (event risk); duplicates; a daily check limit. An exit is never blocked by a day
  limit. Use when the user says "check my order", "is this safe", "risk check", "does this break my
  rules", "can I take this trade", or before /trader-ticket, always.
---
# Risk Manager (NSE)

```bash
python3 trader-risk/check.py                       # live: fresh price, circuit band, event day from NSE
python3 trader-risk/check.py --offline             # rules only, and it says what it skipped
python3 trader-risk/check.py --now "2026-11-25 10:20"
```
Limits come from `trader/config.json` (see `trader-budget/config.example.json`). Today's fills come from `trader/journal.json` (written by `/trader-ticket fill`).

## Report
For each ticket: PASS or BLOCK, each reason in plain words, and any notes (offline, unknown circuit band, a failed source). A BLOCK is final for that ticket: suggest fixing the plan or the size, never overriding. Verdicts are saved to `trader/risk.json`. Only a PASS can be shown as READY by `/trader-ticket`.

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
