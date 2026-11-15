from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from scripts.veltrix_v2.probe_odds_api_brazil_serie_b_history import discover, normalize_team


def _sports(remaining=295):
    envelope = SimpleNamespace(quota_evidence=SimpleNamespace(
        complete=True, requests_used=205, requests_remaining=remaining, requests_last=0
    ))
    def fetcher(_key):
        now = datetime(2026, 11, 15, tzinfo=timezone.utc)
        return now, now, b"[]", {}, envelope, ("soccer_brazil_serie_b",)
    return fetcher


def test_team_normalization_only_removes_accents_and_case():
    assert normalize_team("Náutico") == normalize_team("NAUTICO")
    assert normalize_team("Londrina") == "londrina"


def test_historical_discovery_uses_two_credits_and_no_prices():
    calls = []
    def request(path, _key):
        calls.append(path)
        if "/events?" in path:
            return {
                "timestamp": "2026-11-11T21:55:00Z",
                "data": [{
                    "id": "event-123", "home_team": "Londrina",
                    "away_team": "Nautico", "commence_time": "2026-11-11T22:00:00Z"
                }]
            }, {"x-requests-used": 206, "x-requests-remaining": 294,
                "x-requests-last": 1, "response_sha256": "a" * 64}
        return {
            "timestamp": "2026-11-11T21:55:00Z",
            "data": {"bookmakers": [{"key": "pinnacle", "title": "Pinnacle", "markets": [{"key": "h2h", "last_update": "2026-11-11T21:50:00Z"}, {"key": "totals", "last_update": "2026-11-11T21:50:00Z"}]}]}
        }, {"x-requests-used": 207, "x-requests-remaining": 293,
            "x-requests-last": 1, "response_sha256": "b" * 64}
    result = discover("not-a-real-key", _sports(), request)
    assert result["status"] == "EVENT_AND_MARKETS_DISCOVERED"
    assert result["credits_spent"] == 2
    assert result["historical_price_calls"] == 0
    assert result["database_writes"] == 0
    assert result["bookmakers"][0]["bookmaker_key"] == "pinnacle"
    assert result["market_keys"] == ["h2h", "totals"]
    assert result["bookmakers"][0]["markets"][0]["last_update"] == "2026-11-11T21:50:00Z"
    assert len(calls) == 2


def test_discovery_skips_when_remaining_quota_is_below_guard():
    calls = []
    result = discover("not-a-real-key", _sports(remaining=99),
                      lambda path, key: calls.append(path))
    assert result["status"] == "SKIPPED_LOW_QUOTA"
    assert result["credits_spent"] == 0
    assert calls == []
