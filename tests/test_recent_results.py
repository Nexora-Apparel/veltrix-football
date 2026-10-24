from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
import csv
from zoneinfo import ZoneInfo

from app.live_predictions import build_daily_report

from app.football_api import FootballAPIError
from app.recent_results import extract_completed_results, fetch_recent_results, split_date_ranges


def _fixture(match_date: str, *, status: str = "FT", league_id: int = 39,
             home: str = "Alpha FC", away: str = "Beta FC",
             home_goals: int = 1, away_goals: int = 0):
    return {
        "fixture": {"date": f"{match_date}T15:00:00+01:00", "status": {"short": status}},
        "league": {"id": league_id},
        "teams": {"home": {"name": home}, "away": {"name": away}},
        "goals": {"home": home_goals, "away": away_goals},
    }


def test_split_date_ranges_is_non_overlapping_and_newest_first():
    ranges = split_date_ranges(date(2026, 9, 4), date(2026, 10, 23), max_days=7)
    assert ranges[0][1] == date(2026, 10, 23)
    assert ranges[-1][0] == date(2026, 9, 4)
    assert all((end - start).days < 7 for start, end in ranges)
    for previous, current in zip(ranges, ranges[1:]):
        assert current[1] + timedelta(days=1) == previous[0]


def test_extract_completed_results_maps_competition_and_ignores_unfinished():
    rows = extract_completed_results({
        "response": [
            _fixture("2026-10-20", league_id=39),
            _fixture("2026-10-21", status="NS"),
            _fixture("2026-10-22", status="FT", home_goals=None),
        ]
    })
    assert len(rows) == 1
    assert rows[0]["date"] == date(2026, 10, 20)
    assert rows[0]["division"] == "E0"
    assert rows[0]["home_key"] == "alphafc"
    assert rows[0]["away_key"] == "betafc"
    assert rows[0]["home_goals"] == 1


def test_fetch_recent_results_uses_only_dates_after_base_history_and_end_date():
    class FakeAPI:
        def __init__(self):
            self.calls = []
        def fixtures_between(self, start, end, timezone):
            self.calls.append((start, end, timezone))
            return {"response": [
                _fixture("2026-09-04"),
                _fixture("2026-09-05"),
            ]}

    base = [{
        "date": date(2026, 9, 3), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    api = FakeAPI()
    rows, meta = fetch_recent_results(api, base, date(2026, 9, 4))
    assert api.calls == [("2026-09-04", "2026-09-04", "Africa/Lagos")]
    assert [row["date"] for row in rows] == [date(2026, 9, 4)]
    assert meta["status"] == "COMPLETE"
    assert meta["results_added"] == 1
    assert meta["covered_through"] == "2026-09-04"


def test_fetch_recent_results_keeps_newest_successful_ranges_if_older_range_fails():
    class FakeAPI:
        def __init__(self):
            self.calls = []
        def fixtures_between(self, start, end, timezone):
            self.calls.append((start, end))
            if len(self.calls) == 2:
                raise FootballAPIError("historical range unavailable")
            return {"response": [_fixture("2026-09-19")]}

    base = [{
        "date": date(2026, 9, 1), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    api = FakeAPI()
    rows, meta = fetch_recent_results(api, base, date(2026, 9, 20), max_chunk_days=7)
    assert len(api.calls) == 2
    assert [row["date"] for row in rows] == [date(2026, 9, 19)]
    assert meta["status"] == "PARTIAL"
    assert meta["covered_from"] == "2026-09-14"
    assert meta["covered_through"] == "2026-09-20"
    assert "historical range unavailable" in meta["warning"]


def test_fetch_recent_results_skips_api_when_history_is_current():
    class FakeAPI:
        def fixtures_between(self, *args):
            pytest.fail("API should not be called when history is already current")

    base = [{
        "date": date(2026, 10, 23), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    rows, meta = fetch_recent_results(FakeAPI(), base, date(2026, 10, 23))
    assert rows == []
    assert meta["status"] == "UP_TO_DATE"



def test_daily_report_merges_recent_results_and_reports_freshness(tmp_path):
    history_path = tmp_path / "history.csv"
    with history_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["match_date", "home_team", "away_team", "home_goals", "away_goals"],
        )
        writer.writeheader()
        for day in range(1, 13):
            writer.writerow({
                "match_date": f"2026-10-{day:02d}",
                "home_team": "Alpha FC" if day % 2 else f"Opponent {day}",
                "away_team": f"Opponent {day}" if day % 2 else "Beta FC",
                "home_goals": 2 if day % 2 else 0,
                "away_goals": 0 if day % 2 else 1,
            })
    recent = [{
        "date": date(2026, 10, 20),
        "division": "E0",
        "home": "Alpha FC",
        "away": "Recent Opponent",
        "home_key": "alphafc",
        "away_key": "recentopponent",
        "home_goals": 3,
        "away_goals": 1,
    }]
    payload = {"response": [{
        "fixture": {"id": 901, "date": "2026-10-23T15:00:00+01:00", "status": {"short": "NS"}},
        "league": {"id": 39, "name": "Premier League"},
        "teams": {"home": {"name": "Alpha FC"}, "away": {"name": "Beta FC"}},
    }]}
    report = build_daily_report(
        payload,
        history_path,
        as_of=date(2026, 10, 23),
        now=datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Africa/Lagos")),
        additional_historical_matches=recent,
    )
    assert report["historical_matches_available"] == 13
    assert report["historical_data_through"] == "2026-10-20"
    assert report["predictions_created"] == 1
