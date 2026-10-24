from app.football_api import FootballAPI, normalize_match


class FakeResponse:
    status_code = 200
    headers = {"X-Requests-Available-Minute": "9", "X-RequestCounter-Reset": "25"}

    def json(self):
        return {"matches": [{
            "id": 123,
            "utcDate": "2026-10-25T16:00:00Z",
            "status": "SCHEDULED",
            "competition": {"id": 2021, "name": "Premier League", "code": "PL"},
            "homeTeam": {"id": 1, "name": "Arsenal"},
            "awayTeam": {"id": 2, "name": "Chelsea"},
            "score": {"fullTime": {"home": None, "away": None}},
        }]}


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return FakeResponse()


def test_fixtures_uses_football_data_v4_and_normalizes_matches():
    api = FootballAPI(settings=type("SettingsStub", (), {
        "api_key": "test-key",
        "base_url": "https://api.football-data.org/v4",
    })())
    session = FakeSession()
    api.session = session

    payload = api.fixtures("2026-10-25", "Africa/Lagos")

    assert session.calls == [(
        "https://api.football-data.org/v4/matches",
        {"dateFrom": "2026-10-25", "dateTo": "2026-10-26"},
        20,
    )]
    assert session.headers["X-Auth-Token"] == "test-key"
    fixture = payload["response"][0]
    assert fixture["fixture"]["id"] == 123
    assert fixture["fixture"]["status"]["short"] == "NS"
    assert fixture["teams"]["home"]["name"] == "Arsenal"
    assert fixture["league"]["code"] == "PL"
    assert payload["_veltrix_meta"]["http_status"] == 200


def test_normalize_finished_match_preserves_full_time_score():
    match = {
        "id": 5,
        "utcDate": "2026-10-24T15:00:00Z",
        "status": "FINISHED",
        "competition": {"id": 2002, "name": "Bundesliga", "code": "BL1"},
        "homeTeam": {"name": "Home FC"},
        "awayTeam": {"name": "Away FC"},
        "score": {"fullTime": {"home": 2, "away": 1}},
    }
    normalized = normalize_match(match)
    assert normalized["fixture"]["status"]["short"] == "FT"
    assert normalized["goals"] == {"home": 2, "away": 1}
    assert normalized["league"]["code"] == "BL1"


def test_odds_are_explicitly_unavailable_not_fabricated():
    api = FootballAPI(settings=type("SettingsStub", (), {
        "api_key": "test-key",
        "base_url": "https://api.football-data.org/v4",
    })())
    payload = api.odds_for_date("2026-10-25", "Africa/Lagos")
    assert payload["response"] == []
    assert payload["_veltrix_meta"]["odds_status"] == "UNAVAILABLE"
