# Render deployment

Start command:

```bash
python server.py
```

Environment variables on Render:

- `GEMINI_API_KEY` = your Google Gemini API key
- `APP_PASSWORD` = login password for the web app
- Optional: `APP_SECRET` = any random secret string. If omitted, the app still works.

Main page:

- `/` or `/stock-analyst.html` = AI stock analyst
- `/index.html` = MarketPulse news page
- `/us_stock_analyzer_v3.html` = technical analyzer page
- `/healthz` = quick health check
