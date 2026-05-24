import http.server
import urllib.request
import urllib.error
import json
import os
import hashlib
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse, quote

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()
APP_SECRET = os.environ.get("APP_SECRET", API_KEY or APP_PASSWORD or "local-dev-secret")
PORT = int(os.environ.get("PORT", 8888))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={API_KEY}"
BASE_DIR = Path(__file__).resolve().parent

# Keep Render/GitHub deployment simple: stdlib only, no Flask dependency.
def make_token():
    if not APP_PASSWORD:
        return ""
    raw = f"{APP_PASSWORD}:{APP_SECRET}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

SESSION_TOKEN = make_token()

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "", "/stock-analyst.html"):
            return self._serve_file("stock-analyst.html", "text/html; charset=utf-8")
        if path == "/index.html":
            return self._serve_file("index.html", "text/html; charset=utf-8")
        if path == "/us_stock_analyzer_v3.html":
            return self._serve_file("us_stock_analyzer_v3.html", "text/html; charset=utf-8")
        if path == "/healthz":
            return self._json({"ok": True, "gemini_key_configured": bool(API_KEY), "auth_required": bool(APP_PASSWORD)})
        self.send_error(404, "Not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/auth":
            return self._handle_auth()
        if path == "/api":
            return self._handle_api()
        if path == "/market-data":
            return self._handle_market_data()
        self.send_error(404, "Not found")

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON body")

    def _handle_auth(self):
        try:
            body = self._read_json()
        except ValueError as e:
            return self._json({"ok": False, "error": str(e)}, status=400)

        # If APP_PASSWORD is not set on Render, allow local/demo use instead of locking the app.
        if not APP_PASSWORD:
            return self._json({"ok": True, "token": "", "authRequired": False})

        ok = body.get("password", "") == APP_PASSWORD
        return self._json({"ok": ok, "token": SESSION_TOKEN if ok else "", "authRequired": True})

    def _handle_api(self):
        if APP_PASSWORD and not self._is_authorized():
            return self._json({"error": "Unauthorized. Please login again."}, status=401)
        if not API_KEY:
            return self._json({"error": "GEMINI_API_KEY is not configured on Render."}, status=500)

        try:
            body = self._read_json()
        except ValueError as e:
            return self._json({"error": str(e)}, status=400)

        system_text = str(body.get("system", ""))
        user_text = str(body.get("user", ""))
        temperature = body.get("temperature", 0.4)
        max_tokens = body.get("maxOutputTokens", 4000)

        strict_suffix = "\n\n重要：你的回覆必須是純 JSON 物件，所有 value 都必須是純文字字串（string），不可以是物件、陣列或巢狀結構。不可包含任何 markdown、代碼塊標記或說明文字。直接輸出 { 開頭的 JSON 物件。"
        system_text = system_text + strict_suffix

        gemini_body = {
            "system_instruction": {"parts": [{"text": system_text}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }

        req = urllib.request.Request(
            GEMINI_URL,
            data=json.dumps(gemini_body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return self._json({"text": text})
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8"))
            except Exception:
                err = {"error": f"Gemini API HTTP {e.code}"}
            return self._json(err, status=e.code)
        except Exception as e:
            return self._json({"error": str(e)}, status=500)


    def _handle_market_data(self):
        if APP_PASSWORD and not self._is_authorized():
            return self._json({"error": "Unauthorized. Please login again."}, status=401)
        try:
            body = self._read_json()
        except ValueError as e:
            return self._json({"error": str(e)}, status=400)

        symbol = str(body.get("symbol", "")).strip().upper()
        if not symbol:
            return self._json({"error": "Missing stock symbol."}, status=400)

        data = {
            "symbol": symbol,
            "fetchedAt": int(time.time() * 1000),
            "quote": {},
            "fundamentals": {},
            "news": [],
            "warnings": [],
            "sources": [
                "Yahoo Finance quote API",
                "Yahoo Finance quoteSummary API when available",
                "Google News RSS"
            ]
        }

        quote_data = self._fetch_yahoo_quote(symbol)
        if quote_data:
            data["quote"] = quote_data
        else:
            data["warnings"].append("Unable to fetch latest Yahoo quote data.")

        fundamentals = self._fetch_yahoo_fundamentals(symbol)
        if fundamentals:
            data["fundamentals"] = fundamentals
        else:
            data["warnings"].append("Unable to fetch Yahoo fundamentals. Some metrics may be unavailable.")

        news = self._fetch_google_news(symbol)
        if news:
            data["news"] = news
        else:
            data["warnings"].append("Unable to fetch Google News headlines.")

        return self._json(data)

    def _http_json(self, url, timeout=12):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json,text/plain,*/*",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _fetch_yahoo_quote(self, symbol):
        try:
            url = "https://query1.finance.yahoo.com/v7/finance/quote?symbols=" + quote(symbol)
            js = self._http_json(url)
            rows = js.get("quoteResponse", {}).get("result", [])
            if not rows:
                return {}
            r = rows[0]
            keys = [
                "shortName", "longName", "regularMarketPrice", "regularMarketChange",
                "regularMarketChangePercent", "regularMarketTime", "regularMarketDayHigh",
                "regularMarketDayLow", "regularMarketVolume", "regularMarketPreviousClose",
                "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "marketCap", "trailingPE",
                "forwardPE", "epsTrailingTwelveMonths", "epsForward", "priceToBook",
                "currency", "exchange", "quoteType"
            ]
            return {k: r.get(k) for k in keys if k in r}
        except Exception as e:
            print("Yahoo quote error:", e)
            return {}

    def _fetch_yahoo_fundamentals(self, symbol):
        try:
            modules = "defaultKeyStatistics,financialData,summaryDetail"
            url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{quote(symbol)}?modules={modules}"
            js = self._http_json(url)
            result = js.get("quoteSummary", {}).get("result") or []
            if not result:
                return {}
            root = result[0]
            def raw(path):
                cur = root
                for part in path.split('.'):
                    if not isinstance(cur, dict):
                        return None
                    cur = cur.get(part)
                if isinstance(cur, dict) and "raw" in cur:
                    return cur.get("raw")
                return cur
            fields = {
                "profitMargins": raw("financialData.profitMargins"),
                "grossMargins": raw("financialData.grossMargins"),
                "operatingMargins": raw("financialData.operatingMargins"),
                "returnOnEquity": raw("financialData.returnOnEquity"),
                "revenueGrowth": raw("financialData.revenueGrowth"),
                "earningsGrowth": raw("financialData.earningsGrowth"),
                "totalRevenue": raw("financialData.totalRevenue"),
                "freeCashflow": raw("financialData.freeCashflow"),
                "totalDebt": raw("financialData.totalDebt"),
                "debtToEquity": raw("financialData.debtToEquity"),
                "currentRatio": raw("financialData.currentRatio"),
                "targetMeanPrice": raw("financialData.targetMeanPrice"),
                "recommendationKey": raw("financialData.recommendationKey"),
                "dividendYield": raw("summaryDetail.dividendYield"),
                "beta": raw("summaryDetail.beta"),
                "bookValue": raw("defaultKeyStatistics.bookValue"),
                "enterpriseValue": raw("defaultKeyStatistics.enterpriseValue"),
            }
            return {k:v for k,v in fields.items() if v is not None}
        except Exception as e:
            print("Yahoo fundamentals error:", e)
            return {}

    def _fetch_google_news(self, symbol):
        try:
            rss = "https://news.google.com/rss/search?q=" + quote(f"{symbol} stock") + "&hl=en-US&gl=US&ceid=US:en"
            req = urllib.request.Request(rss, headers={"User-Agent":"Mozilla/5.0"}, method="GET")
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
            root = ET.fromstring(xml_text)
            items = []
            for item in root.findall(".//item")[:8]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                source = item.find("source")
                source_name = source.text.strip() if source is not None and source.text else "Google News"
                if title:
                    items.append({"title": title, "source": source_name, "published": pub, "link": link})
            return items
        except Exception as e:
            print("Google News error:", e)
            return []

    def _is_authorized(self):
        auth = self.headers.get("Authorization", "")
        token = ""
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1].strip()
        token = token or self.headers.get("X-App-Token", "").strip()
        return bool(token) and token == SESSION_TOKEN

    def _serve_file(self, filename, content_type):
        try:
            content = (BASE_DIR / filename).read_bytes()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, f"{filename} not found")

    def _json(self, data, status=200):
        out = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def _cors(self):
        # Keep wildcard for Render compatibility and simple static hosting.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-App-Token")

if __name__ == "__main__":
    print(f"✅ 伺服器啟動：http://localhost:{PORT}")
    print(f"🔐 Password protection: {'ON' if APP_PASSWORD else 'OFF'}")
    print(f"🤖 Gemini key configured: {'YES' if API_KEY else 'NO'}")
    httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.serve_forever()
