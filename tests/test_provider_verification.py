from scripts import verify_data_providers as providers


def test_rate_limited_primary_is_degraded_not_failed_when_odds_fallback_is_ready(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake-odds")
    calls = {"count": 0}

    def fake_request(url, headers=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise providers.ProviderCheckError("HTTP 429")
        return 200, {"x-requests-remaining": "476"}, [
            {"key": "soccer_england_premier_league", "active": True},
            {"key": "soccer_spain_la_liga", "active": True},
        ]

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.main() == 0
    output = capsys.readouterr().out
    assert "RATE_LIMITED_RETRYABLE" in output
    assert "KEY_ACCEPTED" in output
    assert "DEGRADED_FALLBACK_READY" in output


def test_invalid_primary_credentials_do_not_get_misreported_as_rate_limit(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake-odds")
    calls = {"count": 0}

    def fake_request(url, headers=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise providers.ProviderCheckError("HTTP 401")
        return 200, {}, [{"key": "soccer_england_premier_league", "active": True}]

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.main() == 1
    output = capsys.readouterr().out
    assert "FAILED (HTTP 401)" in output
    assert "DEGRADED_FALLBACK_READY" not in output


def test_both_provider_credentials_report_healthy(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake-odds")
    calls = {"count": 0}

    def fake_request(url, headers=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return 200, {"X-RateLimit-Remaining": "59"}, {"success": 1, "data": []}
        return 200, {"x-requests-remaining": "476"}, [
            {"key": "soccer_england_premier_league", "active": True}
        ]

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.main() == 0
    assert "HEALTHY" in capsys.readouterr().out
