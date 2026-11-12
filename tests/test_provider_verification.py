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
    fake_fetch_calls = []
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
        fake_fetch_calls.append(kwargs)
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
    probe_observation_ids = [row["source_observation_id"] for row in fake_fetch_calls]
    assert len(probe_observation_ids) == 8
    assert len(set(probe_observation_ids)) == 8
    assert all(value.startswith("provider-probe:") for value in probe_observation_ids)
    assert "leagues_probed=8" in output
    assert "maximum_odds_credits=8" in output



def test_fivedollar_smoke_probes_one_fixture_per_accessible_league_within_burst(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    leagues = [
        {"id": 1, "name": "Premier League", "country": {"code": "GB-ENG"}},
        {"id": 2, "name": "La Liga", "country": {"code": "ES"}},
        {"id": 3, "name": "Serie A", "country": {"code": "IT"}},
        {"id": 4, "name": "Bundesliga", "country": {"code": "DE"}},
        {"id": 5, "name": "Ligue 1", "country": {"code": "FR"}},
        {"id": 6, "name": "Argentina Liga Profesional", "country": {"code": "AR"}},
    ]
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



def test_fivedollar_community_acceptance_rejects_top_five_without_country_pack(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("FIVEDOLLAR_REQUIRED_PLAN", "community")
    monkeypatch.setenv("FIVEDOLLAR_MIN_ACCESSIBLE_LEAGUES", "6")

    def fake_request(url, headers=None):
        if "/status" in url:
            return 200, {}, {"success": 1, "data": {"plan": "community"}}
        if "/leagues?per_page=100" in url:
            return 200, {}, {
                "success": 1,
                "data": [{"id": index, "name": f"Top-five league {index}"} for index in range(1, 6)],
            }
        raise AssertionError(f"Unexpected request: {url}")

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.check_fivedollar() == "COMPETITION_COVERAGE_INCOMPLETE"
    output = capsys.readouterr().out
    assert "minimum=6; actual=5" in output


def test_community_acceptance_rejects_six_leagues_without_country_pack_identity(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("FIVEDOLLAR_REQUIRED_PLAN", "community")
    monkeypatch.setenv("FIVEDOLLAR_MIN_ACCESSIBLE_LEAGUES", "6")

    def fake_request(url, headers=None):
        if "/status" in url:
            return 200, {}, {"success": 1, "data": {"plan": "community"}}
        if "/leagues?per_page=100" in url:
            return 200, {}, {
                "success": 1,
                "data": [
                    {"id": 1, "name": "Premier League", "country": {"code": "GB-ENG"}},
                    {"id": 2, "name": "La Liga", "country": {"code": "ES"}},
                    {"id": 3, "name": "Serie A", "country": {"code": "IT"}},
                    {"id": 4, "name": "Bundesliga", "country": {"code": "DE"}},
                    {"id": 5, "name": "Ligue 1", "country": {"code": "FR"}},
                    {"id": 6, "name": "Unidentified pack league"},
                ],
            }
        raise AssertionError(f"Unexpected request: {url}")

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.check_fivedollar() == "COUNTRY_PACK_NOT_VERIFIED"
    assert "COUNTRY_PACK_NOT_VERIFIED" in capsys.readouterr().out


def test_community_acceptance_can_require_a_specific_country_pack(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("FIVEDOLLAR_REQUIRED_PLAN", "community")
    monkeypatch.setenv("FIVEDOLLAR_REQUIRED_COUNTRY_CODE", "AR")

    leagues = [
        {"id": 1, "name": "Premier League", "country": {"code": "GB-ENG"}},
        {"id": 2, "name": "La Liga", "country": {"code": "ES"}},
        {"id": 3, "name": "Serie A", "country": {"code": "IT"}},
        {"id": 4, "name": "Bundesliga", "country": {"code": "DE"}},
        {"id": 5, "name": "Ligue 1", "country": {"code": "FR"}},
        {"id": 6, "name": "Brazil Serie A", "country": {"code": "BR"}},
    ]

    def fake_request(url, headers=None):
        if "/status" in url:
            return 200, {}, {"success": 1, "data": {"plan": "community"}}
        if "/leagues?per_page=100" in url:
            return 200, {}, {"success": 1, "data": leagues}
        raise AssertionError(f"Unexpected request: {url}")

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.check_fivedollar() == "REQUIRED_COUNTRY_PACK_MISSING"
    assert "expected=AR" in capsys.readouterr().out


def test_historical_odds_entitlement_probe_preserves_provider_snapshot_timestamp(monkeypatch, capsys):
    calls = []

    def fake_request(url, headers=None):
        calls.append(url)
        assert "/historical/sports/soccer_epl/odds/" in url
        assert "regions=uk" in url
        assert "markets=h2h" in url
        return 200, {"x-requests-remaining": "490"}, {
            "timestamp": "2026-11-08T11:55:00Z",
            "data": [{
                "id": "event-1",
                "bookmakers": [{
                    "key": "bet365",
                    "markets": [{"key": "h2h", "last_update": "2026-11-08T11:54:12Z"}],
                }],
            }],
        }

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.probe_odds_api_historical_access("fake-odds") == "ACCESS_CONFIRMED"
    output = capsys.readouterr().out
    assert "ACCESS_CONFIRMED" in output
    assert "snapshot_timestamp=2026-11-08T11:55:00Z" in output
    assert "market_quotes=1" in output
    assert "maximum_credits=10" in output
    assert len(calls) == 1


def test_historical_odds_entitlement_probe_fails_closed_on_free_plan_403(monkeypatch, capsys):
    def fake_request(url, headers=None):
        raise providers.ProviderCheckError("HTTP 403")

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.probe_odds_api_historical_access("fake-odds") == "NOT_ENTITLED"
    output = capsys.readouterr().out
    assert "HISTORICAL_ODDS: NOT_ENTITLED" in output
    assert "maximum_credits=10" in output
    assert "ACCESS_CONFIRMED" not in output


def test_historical_odds_entitlement_probe_does_not_run_by_default(monkeypatch, capsys):
    monkeypatch.setenv("FIVEDOLLARFOOTBALL_API_KEY", "fake-primary")
    monkeypatch.setenv("THE_ODDS_API_KEY", "fake-odds")
    monkeypatch.delenv("PROBE_THE_ODDS_API_HISTORICAL", raising=False)
    calls = []

    def fake_request(url, headers=None):
        calls.append(url)
        if "/status" in url:
            return 200, {}, {"success": 1, "data": {"plan": "free"}}
        if "/leagues?" in url:
            return 200, {}, {"success": 1, "data": []}
        if "/v4/sports/?" in url:
            return 200, {}, [{"key": "soccer_england_premier_league", "active": True}]
        raise AssertionError(f"Unexpected request: {url}")

    monkeypatch.setattr(providers, "request_json", fake_request)
    assert providers.main() == 0
    assert not any("/historical/" in url for url in calls)
    assert "HISTORICAL_ODDS" not in capsys.readouterr().out
