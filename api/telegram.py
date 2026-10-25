"""Telegram webhook endpoint for Vercel Python Functions.

Required environment variables:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_WEBHOOK_SECRET (Telegram webhook secret_token)
- TELEGRAM_CHAT_ID (allow-list; only this chat receives replies)

Configure Telegram's webhook to POST to /api/telegram and use the same secret.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.request import Request, urlopen

from app.telegram_commands import handle_command


def _send_message(token: str, chat_id: str, text: str) -> None:
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": True,
    }).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=8) as response:
        result = json.loads(response.read().decode("utf-8"))
        if response.status >= 300 or not result.get("ok"):
            raise RuntimeError("Telegram rejected command reply")


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"service":"Veltrix Telegram Command Centre","status":"ready"}')

    def do_POST(self) -> None:
        expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        allowed_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
        received_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not expected_secret or not bot_token or not allowed_chat:
            self._respond(503, {"ok": False, "error": "Webhook environment is not configured"})
            return
        if received_secret != expected_secret:
            self._respond(403, {"ok": False})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                self._respond(400, {"ok": False})
                return
            update = json.loads(self.rfile.read(length).decode("utf-8"))
            message = update.get("message") or update.get("edited_message") or {}
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id", ""))
            text = str(message.get("text") or "")
            if chat_id != allowed_chat or not text.startswith("/"):
                self._respond(200, {"ok": True})
                return
            reply = handle_command(text)
            _send_message(bot_token, chat_id, reply)
            self._respond(200, {"ok": True})
        except (ValueError, TypeError, OSError, RuntimeError):
            # Avoid logging the update body, token, or Telegram request URL.
            self._respond(500, {"ok": False})

    def _respond(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args) -> None:
        # Do not log message contents, chat identifiers, or request details.
        return
