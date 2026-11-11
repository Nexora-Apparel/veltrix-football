from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from urllib.error import HTTPError
from email.message import Message
import json

import pytest

from veltrix_v2.providers.fivedollar import (
    FiveDollarProviderError,
    fetch_fixture_odds,
)

UTC = timezone.utc
KICKOFF = datetime(2026, 11, 12, 19, 0, tzinfo=UTC)
CAPTURE = datetime(2026, 11, 12, 5, 0, tzinfo=UTC)


def payload():
    return {
        "success": 1,
        "data": {
            "fixture_id": "fixture-123",
            "bookmakers": [{
                "slug": "bet365",
                "odds": {
                    "1x2": {"closing": {"home": 2.0, "draw": 3.0, "away": 4.0}},
                    "btts": {"closing": {"yes": 1.8, "no": 2.0}},
                    "goal_line_fixed": [
                        {"line": 2.5, "closing": {"over": 1.9, "under": 1.9}}
                    ],
                },
            }],
        },
    }


class FakeResponse:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.body


def test_client_uses_bearer_auth_and_returns_captured_odds():
    seen = {}
    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return FakeResponse(json.dumps(payload()).encode())
    result = fetch_fixture_odds(
        api_key="secret-test-key",
        fixture_id="fixture-123",
        kickoff_at=KICKOFF,
        captured_at=CAPTURE,
        opener=opener,
    )
    assert seen["url"].endswith("/fixtures/fixture-123/odds")
    assert seen["auth"] == "Bearer secret-test-key"
    assert seen["timeout"] == 15.0
    assert len(result.snapshots) == 7


def test_client_rejects_missing_key():
    with pytest.raises(ValueError, match="API_KEY_REQUIRED"):
        fetch_fixture_odds(
            api_key="", fixture_id="fixture-123",
            kickoff_at=KICKOFF, opener=lambda *a, **k: None,
        )


def test_client_maps_rate_limit_without_retrying():
    headers = Message()
    headers["Retry-After"] = "60"
    def opener(request, timeout):
        raise HTTPError(request.full_url, 429, "rate limited", headers, BytesIO(b""))
    with pytest.raises(FiveDollarProviderError) as caught:
        fetch_fixture_odds(
            api_key="key", fixture_id="fixture-123",
            kickoff_at=KICKOFF, opener=opener,
        )
    assert caught.value.status_code == 429
    assert caught.value.code == "FIVEDOLLAR_RATE_LIMITED"
    assert caught.value.retry_after == "60"


def test_client_maps_permission_denial_without_leaking_body():
    headers = Message()
    def opener(request, timeout):
        raise HTTPError(request.full_url, 403, "forbidden", headers, BytesIO(b"secret response"))
    with pytest.raises(FiveDollarProviderError) as caught:
        fetch_fixture_odds(
            api_key="key", fixture_id="fixture-123",
            kickoff_at=KICKOFF, opener=opener,
        )
    assert caught.value.code == "FIVEDOLLAR_PLAN_OR_PERMISSION_DENIED"
    assert "secret response" not in str(caught.value)
