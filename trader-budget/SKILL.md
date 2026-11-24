---
name: trader-budget
description: >-
  Budget Manager (NSE). Sizes the position in whole shares to four limits (max loss per trade,
  position cap as a % of capital, max order value, and cash after your buffer), says which limit
  decided it, and writes ONE order ticket (buy, stop, target, MIS/CNC) to trader/orders.json. A stop
  too far for your max loss is a refusal, not a smaller order. Risk is measured from the higher of
  the entry and a fresh price. Nothing is placed. Use when the user says "how many shares", "size
  this trade", "how much should I buy", "I have ₹1 lakh", "I only want to risk ₹500", "set my
  rules", or after /trader-timemachine.
---
# Budget Manager (NSE)

```bash
cp trader-budget/config.example.json trader/config.json      # once; then edit the rupee limits
python3 trader-budget/size.py --write
python3 trader-budget/size.py --capital 200000 --max-loss 1000 --price 846.2 --write
```
Config keys: `capital`, `max_loss_per_trade`, `max_position_pct`, `max_order_value`, `cash_buffer_pct`, `product` (MIS/CNC), `mis_leverage` (default 1 = no leverage; only raise it if the user asks and understands the extra risk).

## Report
Quantity, value, margin, which limit decided it, every limit's share count, and the loss if the stop fills. Say clearly that nothing has been placed. Next: `/trader-risk`.

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
