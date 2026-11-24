---
name: trader-timemachine
description: >-
  Time Machine (NSE). Before any money is at risk, replays the rest of the session 10,000 times from
  the stock's own 5-minute candles at the same time of day over the last ~60 sessions, and re-runs
  the opening-range rule on every past session. Prints the odds of target first, stop first, or
  neither by the flat-by time, where open trades closed, the average R, the history and one plain
  verdict. Seeded, so it repeats. Use when the user says "run the time machine", "what are the
  odds", "simulate this trade", "backtest this setup", "monte carlo", "is this a coin flip", or
  after /trader-exit.
---
# Time Machine (NSE)

```bash
python3 trader-timemachine/timemachine.py run --write            # reads trader/plan.json; 10,000 replays, seed 19
python3 trader-timemachine/timemachine.py run --sims 20000 --seed 7 --days 60
```

## How it works
- Each replayed 5-minute candle is drawn from the stock's real candles at that same slot (09:15 ... 15:25) on past sessions: the gap from the prior close and the high/low/close relative to the open. The trade day itself is left out.
- If a candle touches both the stop and the target, it counts as the stop (the conservative read).
- History: on every past session, the first 5m close above the first-15-minute high is the entry, with the plan's stop and target distance in %, flat by the plan's time.

## Report
Target-first %, stop-first %, still-open %, average R, the history counts and the verdict ("close to a coin flip", "leans your way, modestly", "leans against this plan"; "history is thin" under 15 triggers). Always say it is a simulation of the last ~60 sessions, not a prediction. Earnings, halts and circuits are not in it. Next: `/trader-budget`.

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
