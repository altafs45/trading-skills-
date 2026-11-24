---
name: trader-analyze
description: >-
  Stock Analysis (NSE). One compact report for one symbol, most important first: today's setup and
  its base rates from the stock's own history (how often similar breakouts held after 1/5/10 days,
  median move, drawdowns), bull/base/bear scenario odds with levels and invalidation, event risk
  (results, board meetings, dividend/bonus/split/record dates, AGM, buyback, F&O expiry, block/bulk
  deals, credit ratings), technicals (EMA 20/50/200, RSI, MACD, ATR, Bollinger width, ADX, OBV,
  volume and delivery trend, support/resistance, relative strength vs NIFTY 50 and the sector index,
  weekly and 5-minute views), fundamentals from NSE filings and 7 days of tagged news, plus a self-
  contained candlestick chart. Use when the user says "analyze RELIANCE", "full analysis of",
  "what's the outlook for", "technical analysis", "should I look at", "deep dive on", "chart of", or
  for any one-stock question.
---
# Stock Analysis (NSE)

```bash
python3 trader-analyze/analyze.py RELIANCE               # <= 40 lines; JSON in trader/analysis/, chart in trader/charts/
python3 trader-analyze/analyze.py CHALET --horizon 5 --no-news
```
Daily data comes from the bhavcopy store if it holds 200+ sessions (with delivery %). Otherwise it uses Yahoo daily, without delivery %, and the header says so. If `trader/plan.json` is for this symbol, the Time Machine also runs (2,000 replays).

## How to present it
1. The setup line and base rates: "of N past times this fired, X% held above the level after 5 days".
2. OUTLOOK: give the three scenarios with their probabilities, the n behind them, the levels and the invalidation levels. If it says "no probabilities" (too few analogs), say exactly that.
3. EVENT RISK TODAY and the next events: flag any results or board meeting before an intraday trade.
4. Technicals, fundamentals and news briefly, then share the chart path (`trader/charts/SYMBOL.html`, which opens in a browser).
Probabilities are historical frequencies from this stock's own data, not forecasts. Never turn them into "buy" or "sell".

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
