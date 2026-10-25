import re

import pytest

from app.telegram_security import telegram_webhook_secret_token


def test_webhook_token_is_valid_telegram_format_and_deterministic():
    secret = "valid shared secret! with punctuation"
    first = telegram_webhook_secret_token(secret)
    assert first == telegram_webhook_secret_token(secret)
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,256}", first)
    assert first != secret


def test_webhook_token_trims_outer_whitespace():
    assert telegram_webhook_secret_token("  a-long-secret-value!  ") == telegram_webhook_secret_token("a-long-secret-value!")


def test_webhook_token_rejects_short_secret():
    with pytest.raises(ValueError, match="at least 16 characters"):
        telegram_webhook_secret_token("too-short")
