---
name: trader-news
description: >-
  News Monitor (NSE). Tracks news for every stock on the watchlist: Google News (India edition) by
  company name and symbol plus NSE corporate announcements with their PDF links, tagged results /
  order win / deal / management / regulatory / rating / pledge / block deal, new items only, newest
  first, in IST, with each stock's move vs the previous close and the day's FII/DII cash flows.
  Stores titles, source, time and link only. Use when the user says "any news on TCS", "why is this
  stock moving", "news on my watchlist", "morning briefing", "what did the company announce", "NSE
  announcements", "FII DII data", or after /trader-scanner.
---
# News Monitor (NSE)

```bash
python3 trader-news/news.py                         # top 10 of trader/watchlist.json, last 2 days, new items only
python3 trader-news/news.py --symbols TCS,INFY --days 7 --all
```
Flags: `--top N`, `--days N`, `--all` (show already-seen items too), `--no-moves` (skip the quote per stock).

## What it reads
- Google News RSS, India edition (`"Company Name" OR "NSE:SYMBOL"`), cached 15 minutes. Headlines only: never open paywalled articles or download images.
- NSE corporate announcements (subject, first 140 characters, PDF link), cached for the day.
- NSE quote for the % move, and FII/DII net cash (₹ crore) for the market.

## How to report
Lead with items tagged results, deal, regulatory, rating, pledge or block deal; then the rest briefly. Give the time (IST), the source and the link. A tag is a keyword match, so say "tagged as", not "this is". If a stock is moving with no news, say that plainly.

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
