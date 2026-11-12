"""Read-only 5DollarFootballAPI client for per-fixture odds snapshots."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import json

from veltrix_v2.ingestion.fivedollar_odds import (
    FiveDollarOddsCapture,
    parse_fivedollar_fixture_odds,
)

BASE_URL = "https://api.5dollarfootballapi.com/v1"


class FiveDollarProviderError(RuntimeError):
    def __init__(self, status_code: int | None, code: str, retry_after: str | None = None):
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.retry_after = retry_after


def fetch_fixture_odds(
    *,
    api_key: str,
    fixture_id: str,
    kickoff_at: datetime,
    total_line: Decimal = Decimal("2.5"),
    bookmaker_slug: str = "bet365",
    timeout_seconds: float = 15.0,
    opener: Callable = urlopen,
    captured_at: datetime | None = None,
    source_observation_id: str,
) -> FiveDollarOddsCapture:
    """Fetch one fixture's full Bet365 odds payload and timestamp retrieval.

    No retries are performed here. The caller controls pacing to respect the
    provider's 20/minute burst and the active plan's hourly request ceiling.
    Every snapshot must be linked to the immutable response observation.
    """
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("FIVEDOLLAR_API_KEY_REQUIRED")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ValueError("FIVEDOLLAR_FIXTURE_ID_REQUIRED")
    if timeout_seconds <= 0:
        raise ValueError("FIVEDOLLAR_TIMEOUT_MUST_BE_POSITIVE")
    url = f"{BASE_URL}/fixtures/{quote(fixture_id, safe='')}/odds"
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "VELTRIX-FOOTBALL/2.0",
        },
        method="GET",
    )
    try:
        with opener(request, timeout=timeout_seconds) as response:
            body = response.read()
    except HTTPError as error:
        retry_after = error.headers.get("Retry-After") if error.headers else None
        code = {
            401: "FIVEDOLLAR_AUTHENTICATION_FAILED",
            403: "FIVEDOLLAR_PLAN_OR_PERMISSION_DENIED",
            404: "FIVEDOLLAR_FIXTURE_NOT_FOUND",
            429: "FIVEDOLLAR_RATE_LIMITED",
        }.get(error.code, "FIVEDOLLAR_HTTP_ERROR")
        raise FiveDollarProviderError(error.code, code, retry_after) from None
    except URLError:
        raise FiveDollarProviderError(None, "FIVEDOLLAR_NETWORK_ERROR") from None

    observed_at = captured_at or datetime.now(timezone.utc)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("FIVEDOLLAR_CAPTURE_TIMESTAMP_MUST_BE_AWARE")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise FiveDollarProviderError(None, "FIVEDOLLAR_INVALID_JSON_RESPONSE") from None
    return parse_fivedollar_fixture_odds(
        payload,
        fixture_id=fixture_id,
        kickoff_at=kickoff_at,
        captured_at=observed_at,
        bookmaker_slug=bookmaker_slug,
        total_line=total_line,
        source_observation_id=source_observation_id,
    )
