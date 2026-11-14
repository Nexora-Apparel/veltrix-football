from datetime import date, datetime, timezone

from scripts.phase5_capture_odds_api_quota import (
    _canonical_hash,
    _internal_budget_period,
    _quota_integer,
    _safe_headers,
)


def test_quota_capture_keeps_only_documented_non_secret_headers():
    headers = {
        "Date": "Sat, 14 Nov 2026 22:00:00 GMT",
        "Content-Type": "application/json",
        "X-Requests-Used": "21",
        "X-Requests-Remaining": "479",
        "X-Requests-Last": "0",
        "Set-Cookie": "session=private",
        "Authorization": "Bearer do-not-store",
    }
    assert _safe_headers(headers) == {
        "date": "Sat, 14 Nov 2026 22:00:00 GMT",
        "content-type": "application/json",
        "x-requests-used": "21",
        "x-requests-remaining": "479",
        "x-requests-last": "0",
    }


def test_quota_integer_rejects_missing_negative_and_malformed_values():
    assert _quota_integer({"x-requests-used": "21"}, "x-requests-used") == 21
    assert _quota_integer({}, "x-requests-used") is None
    assert _quota_integer({"x-requests-used": "-1"}, "x-requests-used") is None
    assert _quota_integer({"x-requests-used": "21.5"}, "x-requests-used") is None


def test_internal_budget_period_is_rolling_30_days_not_provider_reset_inference():
    assert _internal_budget_period(datetime(2026, 11, 14, tzinfo=timezone.utc)) == (
        date(2026, 11, 14), date(2026, 12, 14)
    )
    assert _internal_budget_period(datetime(2026, 12, 31, tzinfo=timezone.utc)) == (
        date(2026, 12, 31), date(2027, 1, 30)
    )


def test_quota_evidence_hash_is_deterministic_and_scope_sensitive():
    first = {"provider": "the_odds_api", "remaining": 479, "used": 21}
    second = {"used": 21, "remaining": 479, "provider": "the_odds_api"}
    changed = {"provider": "the_odds_api", "remaining": 478, "used": 21}
    assert _canonical_hash(first) == _canonical_hash(second)
    assert _canonical_hash(first) != _canonical_hash(changed)
