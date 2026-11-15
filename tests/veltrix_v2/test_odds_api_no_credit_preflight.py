from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from scripts.veltrix_v2.probe_odds_api_no_credit import build_report


def test_brazil_serie_b_no_credit_preflight_passes_without_price_calls():
    envelope = SimpleNamespace(quota_evidence=SimpleNamespace(
        complete=True, requests_used=122, requests_remaining=878, requests_last=0
    ))
    def fetcher(key):
        assert key == "not-a-real-key"
        now = datetime(2026, 11, 15, tzinfo=timezone.utc)
        return now, now, b'[]', {}, envelope, ("soccer_epl", "soccer_brazil_serie_b")
    result = build_report(fetcher=fetcher, api_key="not-a-real-key")
    assert result["status"] == "PASS_NO_CREDIT"
    assert result["request_cost_credits"] == 0
    assert result["historical_odds_calls_made"] == 0
    assert result["database_writes"] == 0
    assert result["brazil_serie_b_available"] is True
    assert "not-a-real-key" not in str(result)


def test_preflight_fails_closed_without_brazil_or_quota_evidence():
    envelope = SimpleNamespace(quota_evidence=SimpleNamespace(
        complete=False, requests_used=None, requests_remaining=None, requests_last=None
    ))
    def fetcher(_key):
        now = datetime(2026, 11, 15, tzinfo=timezone.utc)
        return now, now, b'[]', {}, envelope, ("soccer_epl",)
    result = build_report(fetcher=fetcher, api_key="not-a-real-key")
    assert result["status"] == "UNVERIFIED"
    assert result["request_cost_credits"] is None
