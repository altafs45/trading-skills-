---
name: trader-alerts
description: >-
  Price Alerts (NSE). Rings once when a price, a stop, a target, a % move vs the previous close, a
  time of day (like flat-by 15:10) or the 09:15 opening bell hits. Turns trader/plan.json into stop,
  target and flat-by alerts in one go. Knows NSE hours and holidays in IST, fetches quotes from Kite
  when logged in or NSE otherwise, and writes trader/prices.json for sizing and the risk check. Use
  when the user says "alert me when", "tell me if TCS hits", "watch my stop", "remind me to square
  off", "is the market open", "when does NSE open", "get me a price", or right after /trader-exit.
---
# Price Alerts (NSE)

```bash
python3 trader-alerts/alerts.py clock                              # market state in IST, next open
python3 trader-alerts/alerts.py quote TCS INFY                      # quotes -> trader/prices.json
python3 trader-alerts/alerts.py add --from-plan                     # stop, target, flat-by
python3 trader-alerts/alerts.py add --symbol TCS --above 4200 --note "breakout"
python3 trader-alerts/alerts.py add --symbol TCS --pct-down 3
python3 trader-alerts/alerts.py add --opening-bell
python3 trader-alerts/alerts.py check                               # rings what hit, once per day
python3 trader-alerts/alerts.py list | reset
```
To keep checking, the user can run `/loop 1m` with `check`. Without a Kite login, NSE quotes are delayed and limited to 10 symbols per check (one request per second). Say which source was used.

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
