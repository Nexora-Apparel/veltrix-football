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



def test_fivedollar_smoke_probes_one_fixture_per_accessible_league_within_burst(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    leagues = [{"id": index, "name": f"League {index}"} for index in range(1, 7)]
    calls = []

    def fake_request(url, headers=None):
        calls.append(url)
        if "/status" in url:
            return 200, {"X-RateLimit-Remaining": "299"}, {
                "success": 1, "data": {"plan": "community"}
            }
        if "/leagues?per_page=100" in url:
            return 200, {"X-RateLimit-Remaining": "298"}, {
                "success": 1, "data": leagues
            }
        if "/fixtures?" in url:
            league_id = url.split("/leagues/")[1].split("/")[0]
            return 200, {}, {"success": 1, "data": [{"id": f"fixture-{league_id}"}]}
        if "/fixtures/" in url and url.endswith("/odds"):
            return 200, {"X-RateLimit-Remaining": "280"}, {
                "success": 1,
                "data": {
                    "bookmakers": [{
                        "slug": "bet365",
                        "odds": {
                            "1x2": {"closing": {"home": 1.9, "draw": 3.2, "away": 4.0}},
                            "btts": {"closing": {"yes": 1.8, "no": 2.0}},
                            "goal_line_fixed": [{
                                "line": 2.5,
                                "closing": {"over": 1.9, "under": 1.9},
                            }],
                        },
                    }],
                },
            }
        raise AssertionError(f"Unexpected request: {url}")

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.check_fivedollar() == "AUTH_OK"
    output = capsys.readouterr().out
    assert "plan=community" in output
    assert "leagues_probed=6; fixtures=6" in output
    assert "1X2=6/6" in output
    assert "BTTS=6/6" in output
    assert "TOTALS_2_5=6/6" in output
    assert len(calls) == 14
    assert len(calls) <= 20



def test_community_acceptance_fails_closed_while_account_remains_on_free_plan(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("FIVEDOLLAR_REQUIRED_PLAN", "community")
    calls = []

    def fake_request(url, headers=None):
        calls.append(url)
        return 200, {}, {"success": 1, "data": {"plan": "free"}}

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.check_fivedollar() == "PLAN_MISMATCH"
    output = capsys.readouterr().out
    assert "PLAN_MISMATCH" in output
    assert "expected=community" in output
    assert "actual=free" in output
    assert len(calls) == 1
