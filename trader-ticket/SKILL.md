---
name: trader-ticket
description: >-
  Order Ticket (NSE). Turns a ticket that passed /trader-risk into plain step-by-step instructions
  the user places themselves in their broker app (buy limit, then a stop-loss order and a target
  limit or one GTT/OCO), records their yes word for word, logs fills to a journal, and builds the
  exit ticket to square off before the flat-by time. It never calls any broker API and cannot place,
  modify or cancel an order. Use when the user says "place the order", "buy it", "execute", "give me
  the ticket", "I got filled", "close my position", "square off", "flatten", or after /trader-risk
  passes.
---
# Order Ticket (NSE)

```bash
python3 trader-ticket/ticket.py show                                    # READY only with today's PASS for that exact ticket
python3 trader-ticket/ticket.py confirm --reply "yes buy 29 CHALET"     # their words, verbatim
python3 trader-ticket/ticket.py fill CHALET --side BUY --qty 29 --price 846.5
python3 trader-ticket/ticket.py close CHALET                            # exit ticket, never blocked
python3 trader-ticket/ticket.py log
```

## Rules
- Show the ticket, then ask the user to type yes with the symbol and the quantity. A yes with doubt words ("but", "wait", "maybe", "?") or a wrong quantity is not recorded: ask again.
- After a recorded yes, tell them to place it themselves in their broker app. Do not use any brokerage MCP tool or connector to send it, even if one is installed and even if they ask. Explain that this pack is ticket-only.
- When they report a fill, log it with `fill` so `/trader-risk` counts it against the day's limits.

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
