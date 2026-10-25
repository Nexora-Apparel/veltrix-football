"""Authenticated Telegram webhook routes for Veltrix Football."""
from __future__ import annotations

import hmac
import json
import os
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException, Request as FastAPIRequest
from fastapi.responses import JSONResponse

from app.telegram_commands import handle_command
from app.telegram_security import telegram_webhook_secret_token

app = FastAPI(title="Veltrix Football Telegram Command Centre")


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


@app.get("/api/telegram")
@app.get("/api/index")
def health() -> dict[str, str]:
    return {"service": "Veltrix Telegram Command Centre", "status": "ready"}


@app.post("/api/telegram")
@app.post("/api/index")
async def telegram_webhook(
    request: FastAPIRequest,
    secret_header: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> JSONResponse:
    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    allowed_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not expected_secret or not bot_token or not allowed_chat:
        raise HTTPException(status_code=503, detail="Webhook environment is not configured")
    try:
        expected_token = telegram_webhook_secret_token(expected_secret)
    except ValueError:
        raise HTTPException(status_code=503, detail="Webhook environment is not configured") from None
    if not secret_header or not hmac.compare_digest(secret_header, expected_token):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    text = str(message.get("text") or "")
    if chat_id != allowed_chat or not text.startswith("/"):
        return JSONResponse({"ok": True})
    try:
        _send_message(bot_token, chat_id, handle_command(text))
    except Exception:
        # Do not expose the update, chat id, token, or Telegram request URL.
        raise HTTPException(status_code=502, detail="Telegram reply delivery failed") from None
    return JSONResponse({"ok": True})
