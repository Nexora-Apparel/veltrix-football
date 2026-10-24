from app.football_api import FootballAPI


class FakeResponse:
    status_code = 200
    headers = {"x-ratelimit-requests-remaining": "99", "x-ratelimit-requests-limit": "100"}

    def json(self):
        return {"response": [{"fixture": {"id": 123}}]}


class FakeSession:
    def __init__(self):
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return FakeResponse()


def test_odds_for_date_uses_odds_endpoint_and_timezone():
    api = FootballAPI(
        settings=type("SettingsStub", (), {
            "api_key": "test-key",
            "base_url": "https://v3.football.api-sports.io",
        })()
    )
    session = FakeSession()
    api.session = session

    payload = api.odds_for_date("2026-10-25", "Africa/Lagos")

    assert session.calls == [(
        "https://v3.football.api-sports.io/odds",
        {"date": "2026-10-25", "timezone": "Africa/Lagos"},
        20,
    )]
    assert payload["response"] == [{"fixture": {"id": 123}}]
    assert payload["_veltrix_meta"]["http_status"] == 200
