"""Connectivity checks only. Ticket monitoring is NOT enabled."""
import json
import os
import threading
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

state = {"mode": "setup_only", "monitoring_active": False,
         "telegram": "not_configured", "bookmyshow": "not_checked"}
lock = threading.Lock()

def update(key, value):
    with lock:
        state[key] = value
    print(key + ": " + value, flush=True)

def check_connections():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        try:
            req = urllib.request.Request(
                "https://api.telegram.org/bot" + token + "/getMe",
                data=b"{}", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as response:
                payload = json.load(response)
            username = payload.get("result", {}).get("username", "")
            expected = os.environ.get("TELEGRAM_BOT_USERNAME", "NirmalDoomsdayAlertBot")
            update("telegram", "verified" if payload.get("ok") and username.lower() == expected.lower()
                   else "wrong_bot_or_invalid_token")
        except Exception:
            # Never log exception strings: they may contain the token-bearing URL.
            update("telegram", "connection_or_authentication_failed")
    day = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y%m%d")
    url = "https://in.bookmyshow.com/cinemas/coim/broadway-cinemas-coimbatore/buytickets/BWCB/" + day
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "DoomsdayTicketAlertSetup/0.1"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(2000000).decode("utf-8", errors="replace").lower()
        if any(marker in body for marker in ("cf-chl-", "attention required", "just a moment")):
            result = "blocked"
        elif "broadway" in body and "imax" in body:
            result = "page_received_booking_detection_not_verified"
        else:
            result = "unrecognized_page"
        update("bookmyshow", result)
    except urllib.error.HTTPError as error:
        update("bookmyshow", "http_" + str(error.code))
    except Exception:
        update("bookmyshow", "connection_failed")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_error(404)
            return
        with lock:
            body = json.dumps(state).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

if __name__ == "__main__":
    threading.Thread(target=check_connections, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler).serve_forever()
