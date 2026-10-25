"""Register Veltrix Telegram commands and point the bot at the webhook endpoint."""
from __future__ import annotations

import os
import re
import sys

import requests

from app.telegram_commands import COMMANDS

TELEGRAM_COMMANDS = [
    {"command": command.lstrip("/"), "description": description[:256]}
    for command, description in COMMANDS.items()
]


def configure(token: str, webhook_url: str, secret: str) -> None:
    if not token.strip():
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    if not re.fullmatch(r"https://[^\s]+/api/index/?", webhook_url.strip()):
        raise ValueError("TELEGRAM_WEBHOOK_URL must be an HTTPS URL ending in /api/telegram")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret):
        raise ValueError("TELEGRAM_WEBHOOK_SECRET must be 1–256 characters: letters, numbers, underscore, or hyphen")
    base = f"https://api.telegram.org/bot{token}"
    headers = {"Content-Type": "application/json"}
    try:
        commands_response = requests.post(
            f"{base}/setMyCommands",
            json={"commands": TELEGRAM_COMMANDS},
            headers=headers,
            timeout=15,
        )
        commands_payload = commands_response.json()
        if commands_response.status_code >= 400 or not commands_payload.get("ok"):
            raise RuntimeError("Telegram rejected setMyCommands")
        webhook_response = requests.post(
            f"{base}/setWebhook",
            json={
                "url": webhook_url.strip(),
                "secret_token": secret,
                "allowed_updates": ["message", "edited_message"],
                "drop_pending_updates": False,
            },
            headers=headers,
            timeout=15,
        )
        webhook_payload = webhook_response.json()
        if webhook_response.status_code >= 400 or not webhook_payload.get("ok"):
            raise RuntimeError("Telegram rejected setWebhook")
    except requests.RequestException as exc:
        raise RuntimeError(f"Telegram configuration request failed ({exc.__class__.__name__})") from None


def main() -> None:
    try:
        configure(
            os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            os.environ.get("TELEGRAM_WEBHOOK_URL", ""),
            os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
        )
        print(f"Registered {len(TELEGRAM_COMMANDS)} Telegram commands and configured webhook.")
    except (ValueError, RuntimeError) as exc:
        print(f"Telegram webhook configuration failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
