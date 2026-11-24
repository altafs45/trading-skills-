---
name: trader-exit
description: >-
  Exit Planner (NSE, long only). Sets the stop and target before you enter: stop at the opening-
  range midpoint by default (or the range low, a percent, an ATR multiple or your price), rounded
  down to the stock's tick size; target at 2R by default (or any R, or a price). Refuses a stop at
  or above the entry, a target at or below it, or a stop inside the spread, and says why. Sets a
  flat-by time before the MIS auto square-off. Writes trader/plan.json for the Time Machine, Budget,
  Risk, Alerts and Track. Use when the user says "where's my stop", "set stop and target", "plan the
  exit", "what's my R", "risk reward", "stop loss", or after /trader-entry triggers.
---
# Exit Planner (NSE)

```bash
python3 trader-exit/exit.py plan --write                                   # from trader/entry.json: or-mid stop, 2R target
python3 trader-exit/exit.py plan --stop atr:1.5 --target 1.5R --write
python3 trader-exit/exit.py plan --symbol TCS --entry 4120 --stop pct:1 --target 2R --flat-by 15:05 --write
python3 trader-exit/exit.py show
```
Stops: `or-mid`, `or-low`, `pct:X`, `atr:X` (ATR14 on 5m bars), or a price. Targets: `NR` or a price. Prices round to the stock's tick (from Kite instruments, else NSE's price-band table): the stop rounds down and the target rounds down.

## Report
Entry, stop, target, risk per share, R multiple, flat-by (IST). Always add: a stop is a plan, not a guarantee; a gap, a circuit or a fast market can fill past it. Default flat-by is 15:10, before brokers' MIS auto square-off.

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
