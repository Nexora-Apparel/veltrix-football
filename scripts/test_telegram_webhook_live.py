"""Perform a real Telegram webhook round-trip using a synthetic /status update."""
from __future__ import annotations

import json
import os
import sys
import time

import requests

from app.telegram_security import telegram_webhook_secret_token


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    url = os.environ.get(
        "TELEGRAM_WEBHOOK_URL",
        "https://veltrix-football-commands.vercel.app/api/index",
    ).strip()
    if not token or not chat_id or not secret:
        raise SystemExit("Telegram webhook verification requires bot token, chat ID, and shared secret.")
    try:
        numeric_chat_id = int(chat_id)
        secret_token = telegram_webhook_secret_token(secret)
    except ValueError:
        raise SystemExit("Telegram chat ID must be numeric and the webhook secret must be at least 16 characters.") from None
    update = {
        "update_id": int(time.time()),
        "message": {
            "message_id": 1,
            "date": int(time.time()),
            "chat": {"id": numeric_chat_id, "type": "private"},
            "text": "/status",
        },
    }
    try:
        response = requests.post(
            url,
            headers={"X-Telegram-Bot-Api-Secret-Token": secret_token},
            json=update,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise SystemExit(f"Webhook request failed ({exc.__class__.__name__}).") from None
    try:
        payload = response.json()
    except ValueError:
        raise SystemExit(f"Webhook returned non-JSON HTTP {response.status_code}.") from None
    if response.status_code != 200 or payload.get("ok") is not True:
        raise SystemExit(f"Webhook verification failed with HTTP {response.status_code}.")
    print("Telegram webhook /status round-trip succeeded; the configured chat received the status reply.")


if __name__ == "__main__":
    main()
