"""Telegram webhook secret normalization shared by registration and validation."""
from __future__ import annotations

import hashlib


def telegram_webhook_secret_token(secret: str) -> str:
    """Derive Telegram's allowed secret-token format from a stored shared secret.

    The configured shared secret may contain punctuation, while Telegram only
    accepts letters, digits, underscores, and hyphens for its header token.
    Hashing yields a fixed 64-character hexadecimal token without exposing the
    original secret to Telegram or logs.
    """
    value = str(secret or "").strip()
    if len(value) < 16:
        raise ValueError("TELEGRAM_WEBHOOK_SECRET must be at least 16 characters.")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
