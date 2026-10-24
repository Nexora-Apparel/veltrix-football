from datetime import date

from app.recent_results import fetch_recent_results


def test_fetch_recent_results_uses_configured_timezone():
    class FakeAPI:
        def __init__(self):
            self.calls = []

        def fixtures_between(self, start, end, timezone):
            self.calls.append((start, end, timezone))
            return {"response": []}

    history = [{
        "date": date(2026, 10, 19),
        "division": "E0",
        "home": "Old FC",
        "away": "Older FC",
        "home_key": "oldfc",
        "away_key": "olderfc",
        "home_goals": 1,
        "away_goals": 0,
    }]
    api = FakeAPI()

    rows, metadata = fetch_recent_results(
        api,
        history,
        date(2026, 10, 20),
        timezone_name="Europe/London",
    )

    assert rows == []
    assert metadata["status"] == "COMPLETE"
    assert api.calls == [("2026-10-20", "2026-10-20", "Europe/London")]
