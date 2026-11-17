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


def telegram_call(token, method, data):
    req = urllib.request.Request("https://api.telegram.org/bot" + token + "/" + method,
        data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.load(response)
    if not payload.get("ok"):
        raise RuntimeError("Telegram request failed")
    return payload["result"]

def test_telegram_delivery(token):
    # Only match the user's already-sent request, before this code was published.
    # Never bind future strangers who discover the bot through the public repo.
    updates = telegram_call(token, "getUpdates", {"timeout": 0, "limit": 100})
    if len(updates) == 100:
        update("telegram_test", "inbox_requires_review")
        return
    matches = {}
    for item in updates:
        msg = item.get("message", {})
        chat = msg.get("chat", {})
        if (chat.get("type") == "private"
            and msg.get("text", "").strip().casefold() == "connect my doomsday alerts"
            and 1794822146 <= msg.get("date", 0) <= 1794908546):
            matches[chat["id"]] = item["update_id"]
    if len(matches) != 1:
        update("telegram_test", "no_matching_message" if not matches else "ambiguous_recipient")
        return
    chat_id, update_id = next(iter(matches.items()))
    telegram_call(token, "sendMessage", {
        "chat_id": chat_id,
        "text": "TEST ONLY: Your Doomsday alert bot can send messages to this chat. Ticket monitoring is NOT active. BookMyShow is currently blocking our cloud checks. This is not a ticket-availability alert.",
        "disable_notification": False})
    update("telegram_test", "message_accepted_by_telegram")
    # Confirm the matched update after successful sending to prevent replay on restart.
    telegram_call(token, "getUpdates", {"offset": update_id + 1, "timeout": 0, "limit": 1})

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
            if payload.get("ok") and username.lower() == expected.lower():
                try:
                    test_telegram_delivery(token)
                except Exception:
                    update("telegram_test", "send_or_inbox_check_failed")
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
