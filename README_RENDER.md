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

## Update: AI analysis cache

The main stock analyst page now keeps a short-term browser cache in `localStorage`.

- Same stock symbol + same analysis tab will reuse the saved AI answer for 6 hours.
- This reduces repeated Gemini API calls when searching the same stock again shortly after.
- Users can click **重新分析** to ignore the cache and call AI again.
- To change the cache duration, edit this line in `stock-analyst.html`:

```js
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;
```
