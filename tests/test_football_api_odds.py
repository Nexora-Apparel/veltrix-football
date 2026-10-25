from app.football_api import FootballAPI, FootballAPIError, normalize_match


class FakeResponse:
    status_code = 200
    headers = {
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "98",
    }

    def json(self):
        return {
            "data": [{
                "id": 123,
                "date": "2026-10-25T16:00:00.000Z",
                "state": {"description": "Not started", "clock": None,
                          "score": {"current": None, "penalties": None}},
                "league": {"id": 133, "name": "Premier League", "season": 2026},
                "homeTeam": {"id": 1, "name": "Arsenal"},
                "awayTeam": {"id": 2, "name": "Chelsea"},
            }],
            "pagination": {"totalCount": 1, "offset": 0, "limit": 100},
            "plan": {"tier": "BASIC", "message": "Example"},
        }


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return FakeResponse()


def _api():
    return FootballAPI(settings=type("SettingsStub", (), {
        "api_key": "test-key",
        "base_url": "https://soccer.highlightly.net",
    })())


def test_fixtures_uses_highlightly_and_normalizes_match_shape():
    api = _api()
    session = FakeSession()
    api.session = session

    payload = api.fixtures("2026-10-25", "Africa/Lagos")

    assert session.headers["x-rapidapi-key"] == "test-key"
    assert session.calls == [(
        "https://soccer.highlightly.net/matches",
        {"date": "2026-10-25", "timezone": "Africa/Lagos", "limit": 100, "offset": 0},
        20,
    )]
    fixture = payload["response"][0]
    assert fixture["fixture"]["id"] == 123
    assert fixture["fixture"]["status"]["short"] == "NS"
    assert fixture["teams"]["home"]["name"] == "Arsenal"
    assert fixture["league"]["code"] == "PL"
    assert payload["_veltrix_meta"]["provider"] == "Highlightly"
    assert payload["_veltrix_meta"]["requests_remaining"] == "98"


def test_normalize_finished_match_preserves_score_and_maps_status():
    match = {
        "id": 5,
        "date": "2026-10-24T15:00:00.000Z",
        "state": {"description": "Finished", "score": {"current": "2 - 1"}},
        "league": {"id": 2002, "name": "Bundesliga", "season": 2026},
        "homeTeam": {"name": "Home FC"},
        "awayTeam": {"name": "Away FC"},
    }
    normalized = normalize_match(match)
    assert normalized["fixture"]["status"]["short"] == "FT"
    assert normalized["goals"] == {"home": 2, "away": 1}
    assert normalized["league"]["code"] == "BL1"


def test_odds_are_explicitly_unavailable_without_making_a_request():
    api = _api()
    session = FakeSession()
    api.session = session
    payload = api.odds_for_date("2026-10-25", "Africa/Lagos")
    assert payload["response"] == []
    assert payload["_veltrix_meta"]["odds_status"] == "UNAVAILABLE"
    assert session.calls == []


def test_fixture_range_uses_one_request_per_day():
    api = _api()
    session = FakeSession()
    api.session = session
    payload = api.fixtures_between("2026-10-24", "2026-10-25")
    assert len(session.calls) == 2
    assert payload["_veltrix_meta"]["requests_made"] == 2


def test_highlightly_auth_errors_are_actionable():
    class UnauthorizedResponse(FakeResponse):
        status_code = 401
        def json(self):
            return {"message": "Unauthorized"}

    class UnauthorizedSession(FakeSession):
        def get(self, url, params=None, timeout=None):
            return UnauthorizedResponse()

    api = _api()
    api.session = UnauthorizedSession()
    try:
        api.fixtures("2026-10-25")
    except FootballAPIError as exc:
        assert "API key was rejected" in str(exc)
    else:
        raise AssertionError("Expected an actionable auth error")
