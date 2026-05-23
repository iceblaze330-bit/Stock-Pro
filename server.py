import http.server
import urllib.request
import urllib.error
import json
import os

API_KEY = os.environ.get("GEMINI_API_KEY", "")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
PORT = int(os.environ.get("PORT", 8888))
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={API_KEY}"

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.address_string()}] {format % args}")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            with open("stock-analyst.html", "rb") as f:
                content = f.read()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "stock-analyst.html not found")

    def do_POST(self):
        if self.path == "/auth":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            ok = body.get("password", "") == APP_PASSWORD
            out = json.dumps({"ok": ok}).encode("utf-8")
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(out)
            return

        if self.path != "/api":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        system_text = body.get("system", "")
        user_text = body.get("user", "")

        # Reinforce JSON-only output
        strict_suffix = "\n\n重要：你的回覆必須是純 JSON 物件，所有 value 都必須是純文字字串（string），不可以是物件、陣列或巢狀結構。不可包含任何 markdown、代碼塊標記或說明文字。直接輸出 { 開頭的 JSON 物件。"
        system_text = system_text + strict_suffix

        gemini_body = {
            "system_instruction": {
                "parts": [{"text": system_text}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": user_text}]}
            ],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 4000,
                "responseMimeType": "application/json",
            }
        }

        req = urllib.request.Request(
            GEMINI_URL,
            data=json.dumps(gemini_body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            out = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")

            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        except urllib.error.HTTPError as e:
            err = e.read()
            self.send_response(e.code)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(err)

        except Exception as e:
            msg = json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(msg)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

if __name__ == "__main__":
    print(f"✅ 伺服器啟動：http://localhost:{PORT}")
    httpd = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    httpd.serve_forever()
