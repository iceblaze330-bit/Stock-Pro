# Stock Analyst Render App

## Deploy on Render

Build command: leave blank or use:

```bash
pip install -r requirements.txt
```

Start command:

```bash
python server.py
```

## Required Environment Variables

Set these in Render → your Web Service → Environment:

```text
GEMINI_API_KEY=your Gemini API key
APP_PASSWORD=your login password
```

Optional:

```text
APP_SECRET=any random long text
GEMINI_MODEL=gemini-2.5-flash
```

## What this version does

- Keeps the same `/`, `/auth`, and `/api` flow as before.
- Adds `/market-data` on the backend.
- Before AI analysis, the backend tries to fetch:
  - latest Yahoo Finance quote data
  - Yahoo Finance fundamentals when available
  - recent Google News RSS headlines
- The frontend sends those real data points to Gemini, so the AI answer is based on the latest available external data instead of only model memory.
- AI results are cached in the browser for 1 hour by stock + tab to avoid repeated Gemini calls.
- Press **重新分析** to clear the current stock/tab cache and fetch fresh data again.

## Important note

Yahoo Finance and Google News are free public endpoints and can sometimes be delayed, rate-limited, or missing fields. The app shows N/A when a metric cannot be fetched.
