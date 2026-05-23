import http.server
import urllib.request
import urllib.error
import json
import os
import hashlib
from pathlib import Path
from urllib.parse import urlparse

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
