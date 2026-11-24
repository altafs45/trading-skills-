---
name: trader-analyst
description: >-
  Results Analyst (NSE filings). Reads a company's quarterly results from NSE's integrated filings
  (consolidated first, else standalone): total income, PAT, PAT margin and EPS, quarter on quarter,
  year on year and trailing twelve months, with the quarter end and filing date; PE vs sector PE;
  promoter holding trend; insider (PIT) trades over 90 days and how fresh that feed is. Use when the
  user says "how were TCS results", "analyze the quarterly results", "is profit growing", "compare
  margins", "promoter holding", "insider trading in", or before trading around results.
---
# Results Analyst (NSE)

```bash
python3 trader-analyst/results.py INFY       # full data: trader/analysis/INFY-fundamentals.json
```

## Sources (cached for the IST day)
- `GetQuoteApi getIntegratedFilingData`: quarterly total income, PBT, PAT, EPS (2025 on). Only total income is filed there, so say "total income", not "revenue".
- `results-comparision`: older standalone data with revenue from operations. Used only when the integrated feed is empty. When checked on 2026-11-24 it stopped at Dec 2024, and the script marks it STALE.
- Shareholding master: promoter % per quarter. The FII/DII split and pledge % live in the XBRL filing linked in the output, which this skill does not parse, so say so.
- `corporates-pit`: insider trades. If it shows none, report the newest record date the script prints. The feed can lag.

## Report
Quarter end, basis and filing date first. Then income, PAT, margin and EPS with QoQ and YoY, then TTM, PE vs sector, holding and insiders. Money is shown in ₹ crore (filed in lakhs).

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
