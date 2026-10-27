from app.api_football_odds import APIFootballClient, APIFootballError


class FakeResponse:
    status_code = 200
    headers = {"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "97"}

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.headers = {}
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout, dict(self.headers)))
        return FakeResponse(self.payload)


def test_status_uses_api_sports_header_and_does_not_return_account_email():
    session = FakeSession({
        "errors": [],
        "response": {
            "account": {"firstname": "Private", "email": "private@example.invalid"},
            "subscription": {"active": True, "plan": "Free", "end": "2026-12-31"},
            "requests": {"current": 3, "limit_day": 100},
        },
    })
    client = APIFootballClient("test-key", session=session)
    result = client.status()
    assert session.calls[0][0] == "https://v3.football.api-sports.io/status"
    assert session.calls[0][3]["x-apisports-key"] == "test-key"
    assert result["authenticated"] is True
    assert result["subscription"]["active"] is True
    assert result["requests"]["daily_limit"] == 100
    assert "email" not in result["account"]
    assert "test-key" not in str(result)


def test_odds_flattens_fixture_bookmaker_and_common_markets():
    session = FakeSession({
        "errors": [],
        "paging": {"current": 1, "total": 1},
        "response": [{
            "fixture": {"id": 77, "date": "2026-10-27T18:00:00+00:00"},
            "league": {"name": "Example League"},
            "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
            "bookmakers": [{
                "name": "Example Book",
                "bets": [
                    {"name": "Match Winner", "values": [
                        {"value": "Home", "odd": "1.90"},
                        {"value": "Draw", "odd": "3.50"},
                        {"value": "Away", "odd": "4.20"},
                    ]},
                    {"name": "Both Teams Score", "values": [
                        {"value": "Yes", "odd": "1.80"},
                        {"value": "No", "odd": "2.00"},
                    ]},
                    {"name": "Goals Over/Under", "values": [
                        {"value": "Over 2.5", "odd": "1.95"},
                        {"value": "Under 2.5", "odd": "1.85"},
                    ]},
                ],
            }],
        }],
    })
    result = APIFootballClient("test-key", session=session).odds_for_date("2026-10-27")
    assert session.calls[0][0] == "https://v3.football.api-sports.io/odds"
    assert session.calls[0][1] == {"date": "2026-10-27", "timezone": "Africa/Lagos", "page": 1}
    assert len(result["response"]) == 1
    row = result["response"][0]
    assert row["home_team"] == "Arsenal" and row["away_team"] == "Chelsea"
    assert row["bookmaker"] == "Example Book"
    assert row["odds"]["home"] == 1.9
    assert row["odds"]["draw"] == 3.5
    assert row["odds"]["away"] == 4.2
    assert row["odds"]["yes"] == 1.8 and row["odds"]["no"] == 2.0
    assert row["odds"]["over_2_5"] == 1.95
    assert row["odds"]["under_2_5"] == 1.85
    assert result["_veltrix_meta"]["status"] == "AVAILABLE"


def test_missing_key_fails_closed_without_network_access():
    client = APIFootballClient(api_key="", session=FakeSession({"errors": [], "response": []}))
    try:
        client.status()
    except APIFootballError as exc:
        assert "API_FOOTBALL_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing API key to fail closed")


def test_empty_odds_is_not_misreported_as_authentication_failure():
    session = FakeSession({"errors": [], "paging": {"current": 1, "total": 1}, "response": []})
    result = APIFootballClient("test-key", session=session).odds_for_date("2026-10-27")
    assert result["results"] == 0
    assert result["_veltrix_meta"]["status"] == "NO_ODDS_RETURNED"


def test_provider_auth_error_is_sanitized():
    session = FakeSession({"errors": {"token": "secret-key rejected"}, "response": []})
    try:
        APIFootballClient("secret-key", session=session).status()
    except APIFootballError as exc:
        assert "token" in str(exc)
        assert "secret-key" not in str(exc)
    else:
        raise AssertionError("Expected provider error")


def test_empty_odds_reports_fixture_and_bookmaker_coverage_diagnostics():
    session = FakeSession({
        "errors": [],
        "paging": {"current": 1, "total": 1},
        "response": [{
            "fixture": {"id": 1234, "date": "2026-10-27T18:00:00+00:00"},
            "league": {"name": "Example League"},
            "teams": {"home": {"name": "Alpha"}, "away": {"name": "Beta"}},
            "bookmakers": [],
        }],
    })
    result = APIFootballClient("test-key", session=session).odds_for_date("2026-10-27")
    meta = result["_veltrix_meta"]
    assert meta["status"] == "NO_ODDS_RETURNED"
    assert meta["raw_fixture_rows"] == 1
    assert meta["fixtures_with_bookmakers"] == 0
    assert meta["bookmaker_count"] == 0
    assert meta["fixture_examples"][0]["fixture_id"] == "1234"
    assert meta["fixture_examples"][0]["match"] == "Alpha vs Beta"



def test_odds_enriches_missing_team_names_using_fixture_ids():
    class QueuedSession:
        def __init__(self):
            self.headers = {}
            self.calls = []
            self.payloads = [
                {
                    "errors": [],
                    "paging": {"current": 1, "total": 1},
                    "response": [{
                        "fixture": {"id": 9001, "date": "2026-10-27T18:00:00+00:00"},
                        "league": {"name": "Example League"},
                        "bookmakers": [{
                            "name": "Example Book",
                            "bets": [
                                {"name": "Match Winner", "values": [
                                    {"value": "Home", "odd": "1.90"},
                                    {"value": "Draw", "odd": "3.50"},
                                    {"value": "Away", "odd": "4.20"},
                                ]},
                                {"name": "Both Teams Score", "values": [
                                    {"value": "Yes", "odd": "1.80"},
                                    {"value": "No", "odd": "2.00"},
                                ]},
                            ],
                        }],
                    }],
                },
                {
                    "errors": [],
                    "response": [{
                        "fixture": {"id": 9001},
                        "teams": {
                            "home": {"name": "Arsenal"},
                            "away": {"name": "Chelsea"},
                        },
                    }],
                },
            ]

        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params, timeout, dict(self.headers)))
            return FakeResponse(self.payloads.pop(0))

    session = QueuedSession()
    result = APIFootballClient("test-key", session=session).odds_for_date("2026-10-27")
    assert len(session.calls) == 2
    assert session.calls[1][0] == "https://v3.football.api-sports.io/fixtures"
    assert session.calls[1][1]["ids"] == "9001"
    assert result["results"] == 1
    assert result["response"][0]["home_team"] == "Arsenal"
    assert result["response"][0]["away_team"] == "Chelsea"
    assert result["_veltrix_meta"]["team_name_enrichment"] == "SUCCESS"


def test_odds_falls_back_to_date_lookup_when_batch_ids_are_plan_restricted():
    class QueuedSession:
        def __init__(self):
            self.headers = {}
            self.calls = []
            self.payloads = [
                {
                    "errors": [],
                    "paging": {"current": 1, "total": 1},
                    "response": [{
                        "fixture": {"id": 9002, "date": "2026-10-27T18:00:00+00:00"},
                        "league": {"name": "Example League"},
                        "bookmakers": [{
                            "name": "Example Book",
                            "bets": [{
                                "name": "Match Winner",
                                "values": [
                                    {"value": "Home", "odd": "1.90"},
                                    {"value": "Draw", "odd": "3.50"},
                                    {"value": "Away", "odd": "4.20"},
                                ],
                            }],
                        }],
                    }],
                },
                {"errors": {"plan": "batch IDs not available"}, "response": []},
                {
                    "errors": [],
                    "response": [{
                        "fixture": {"id": 9002, "date": "2026-10-27T18:00:00+00:00"},
                        "teams": {
                            "home": {"name": "Alpha"},
                            "away": {"name": "Beta"},
                        },
                    }],
                },
            ]

        def get(self, url, params=None, timeout=None):
            self.calls.append((url, params, timeout, dict(self.headers)))
            payload = self.payloads.pop(0)
            return FakeResponse(payload)

    session = QueuedSession()
    result = APIFootballClient("test-key", session=session).odds_for_date("2026-10-27")

    assert len(session.calls) == 3
    assert session.calls[1][1]["ids"] == "9002"
    assert session.calls[2][1] == {"date": "2026-10-27", "timezone": "Africa/Lagos"}
    assert result["results"] == 1
    assert result["response"][0]["home_team"] == "Alpha"
    assert result["response"][0]["away_team"] == "Beta"
    assert result["_veltrix_meta"]["team_name_enrichment"] == "SUCCESS"
    assert "team_name_enrichment_detail" not in result["_veltrix_meta"]



def test_primary_fixtures_normalize_to_veltrix_shape_and_use_api_football():
    session = FakeSession({
        "errors": [],
        "paging": {"current": 1, "total": 1},
        "response": [{
            "fixture": {
                "id": 123, "date": "2026-10-27T18:00:00+00:00",
                "status": {"short": "NS", "long": "Not Started"},
            },
            "league": {"id": 39, "name": "Premier League", "season": 2026},
            "teams": {"home": {"id": 1, "name": "Arsenal"}, "away": {"id": 2, "name": "Chelsea"}},
            "goals": {"home": None, "away": None},
        }],
    })
    client = APIFootballClient("test-key", session=session)
    result = client.fixtures("2026-10-27", "Africa/Lagos")
    assert session.calls[0][0] == "https://v3.football.api-sports.io/fixtures"
    assert session.calls[0][1] == {"date": "2026-10-27", "timezone": "Africa/Lagos", "page": 1}
    fixture = result["response"][0]
    assert fixture["fixture"]["id"] == 123
    assert fixture["fixture"]["status"]["short"] == "NS"
    assert fixture["teams"]["home"]["name"] == "Arsenal"
    assert fixture["league"]["code"] == "PL"
    assert result["provider"] == "API-Football (API-Sports)"


def test_primary_historical_range_uses_from_to_and_normalizes_final_scores():
    session = FakeSession({
        "errors": [],
        "paging": {"current": 1, "total": 1},
        "response": [{
            "fixture": {
                "id": 456, "date": "2026-10-20T15:00:00+01:00",
                "status": {"short": "FT", "long": "Match Finished"},
            },
            "league": {"id": 39, "name": "Premier League", "season": 2026},
            "teams": {"home": {"id": 1, "name": "Arsenal"}, "away": {"id": 2, "name": "Chelsea"}},
            "goals": {"home": 2, "away": 1},
        }],
    })
    client = APIFootballClient("test-key", session=session)
    result = client.fixtures_between("2026-10-20", "2026-10-26", "Africa/Lagos")
    assert session.calls[0][0] == "https://v3.football.api-sports.io/fixtures"
    assert session.calls[0][1] == {
        "from": "2026-10-20", "to": "2026-10-26",
        "timezone": "Africa/Lagos", "page": 1,
    }
    fixture = result["response"][0]
    assert fixture["fixture"]["status"]["short"] == "FT"
    assert fixture["goals"] == {"home": 2, "away": 1}
    assert fixture["league"]["code"] == "PL"


def test_primary_fixture_queries_reject_ranges_over_seven_days():
    client = APIFootballClient("test-key", session=FakeSession({"errors": [], "response": []}))
    try:
        client.fixtures_between("2026-10-01", "2026-10-08")
    except APIFootballError as exc:
        assert "capped at 7 calendar days" in str(exc)
    else:
        raise AssertionError("Expected oversized historical range to be rejected")
