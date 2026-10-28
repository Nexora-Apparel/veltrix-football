from datetime import date

from app.open_matchday import OpenMatchdayClient


class FakeResponse:
    def __init__(self, text="", status_code=200, payload=None):
        self.text = text
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, mapping):
        self.mapping = mapping
        self.headers = {}

    def get(self, url, timeout):
        return self.mapping.get(url, FakeResponse(status_code=404))


def test_open_matchday_parses_fixtures_and_finished_results():
    base = OpenMatchdayClient.BASE_URL
    session = FakeSession({
        f"{base}/ENG_1_premier-league/fixtures_2627.csv": FakeResponse(
            "gw,date,time,home,away\n9,2026-10-31,13:30,Chelsea,Man Utd\n"
        ),
        f"{base}/ENG_1_premier-league/results_2627.csv": FakeResponse(
            "gw,date,time,home,away,ft_home,ft_away\n8,2026-10-24,16:00,Arsenal,Leeds,2,1\n"
            "8,2026-10-24,16:00,Bad Row,Team,,\n"
        ),
    })
    client = OpenMatchdayClient(session=session)
    rows = client.fetch_records(
        ["ENG_1_premier-league"], date(2026, 10, 24), date(2026, 10, 31)
    )

    assert len(rows) == 2
    fixture = next(row for row in rows if row.status == "NS")
    result = next(row for row in rows if row.status == "FT")
    assert fixture.home == "Chelsea"
    assert fixture.kickoff == "2026-10-31T12:30:00Z"
    assert result.home_goals == 2
    assert result.away_goals == 1
    assert result.source == "open-matchday"


def test_open_matchday_date_range_is_validated():
    client = OpenMatchdayClient(session=FakeSession({}))
    try:
        client.fetch_records(["ENG_1_premier-league"], date(2026, 10, 31), date(2026, 10, 30))
    except ValueError as exc:
        assert "end_date" in str(exc)
    else:
        raise AssertionError("Expected invalid date range to be rejected")


def test_competition_discovery_filters_current_season_csvs():
    payload = {"tree": [
        {"path": "data/ENG_1_premier-league/fixtures_2627.csv", "type": "blob"},
        {"path": "data/ENG_1_premier-league/results_2627.csv", "type": "blob"},
        {"path": "data/ENG_1_premier-league/results_2526.csv", "type": "blob"},
        {"path": "README.md", "type": "blob"},
    ]}
    session = FakeSession({OpenMatchdayClient.TREE_URL: FakeResponse(payload=payload)})
    assert OpenMatchdayClient(session=session).competition_paths() == ["ENG_1_premier-league"]
