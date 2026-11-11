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
        if "/status" in url:
            return 200, {"X-RateLimit-Remaining": "59"}, {"success": 1, "data": {"plan": "free"}}
        if "/leagues?" in url:
            return 200, {"X-RateLimit-Remaining": "58"}, {"success": 1, "data": []}
        return 200, {"x-requests-remaining": "476"}, [
            {"key": "soccer_england_premier_league", "active": True}
        ]

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.main() == 0
    assert "HEALTHY" in capsys.readouterr().out


def test_optional_top_five_and_south_american_btts_probe_is_bounded_to_eight_credits(monkeypatch, capsys):
    from types import SimpleNamespace
    from veltrix_v2.providers import the_odds_api

    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake-odds")
    monkeypatch.setenv("PROBE_THE_ODDS_API_MARKETS", "true")
    target_sports = [
        "soccer_england_premier_league",
        "soccer_france_ligue_one",
        "soccer_germany_bundesliga",
        "soccer_italy_serie_a",
        "soccer_spain_la_liga",
        "soccer_argentina_primera_division",
        "soccer_brazil_campeonato",
        "soccer_brazil_serie_b",
    ]
    calls = []
    def fake_request(url, headers=None):
        if "/status" in url:
            return 200, {}, {"success": 1, "data": {"plan": "community"}}
        if "/leagues?" in url:
            return 200, {}, {"success": 1, "data": []}
        if "/v4/sports/?" in url:
            return 200, {"x-requests-remaining": "500"}, [
                {"key": key, "active": True} for key in target_sports
            ]
        if "/events/?" in url:
            return 200, {}, [{
                "id": "event-1",
                "commence_time": "2099-01-01T00:00:00Z",
            }]
        raise AssertionError("Unexpected provider request")

    def fake_fetch(**kwargs):
        calls.append(kwargs["sport_key"])
        return SimpleNamespace(
            snapshots=(object(), object()),
            missing_bookmakers=(),
            requests_remaining=495,
        )

    monkeypatch.setattr(providers, "request_json", fake_request)
    monkeypatch.setattr(the_odds_api, "fetch_event_btts_odds", fake_fetch)
    assert providers.main() == 0
    output = capsys.readouterr().out
    assert "plan=community" in output
    assert len(calls) == 8
    assert "leagues_probed=8" in output
    assert "maximum_odds_credits=8" in output
