from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
import csv
from zoneinfo import ZoneInfo

from app.live_predictions import build_daily_report

from app.football_api import FootballAPIError
from app.recent_results import extract_completed_results, fetch_recent_results, fetch_recent_results_incremental, split_date_ranges


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
    assert rows[0]["home_key"] == "alpha"
    assert rows[0]["away_key"] == "beta"
    assert rows[0]["home_goals"] == 1


def test_completed_result_rows_retain_fixture_id_for_paper_tracking():
    match = _fixture("2026-10-20", status="FT", home_goals=2, away_goals=1)
    match["fixture"]["id"] = 987654
    rows = extract_completed_results({"response": [match]})
    assert len(rows) == 1
    assert rows[0]["fixture_id"] == 987654
    assert rows[0]["fixture_status"] == "FT"


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


def test_fetch_recent_results_can_limit_provider_calls_to_one_range():
    class FakeAPI:
        def __init__(self):
            self.calls = []
        def fixtures_between(self, start, end, timezone):
            self.calls.append((start, end, timezone))
            return {"response": [_fixture(end)]}

    base = [{
        "date": date(2026, 9, 3), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    api = FakeAPI()
    rows, meta = fetch_recent_results(
        api, base, date(2026, 10, 24), max_chunk_days=7, max_ranges=1
    )
    assert len(api.calls) == 1
    assert api.calls[0] == ("2026-10-18", "2026-10-24", "Africa/Lagos")
    assert len(rows) == 1
    assert meta["status"] == "PARTIAL"
    assert meta["ranges_succeeded"] == 1
    assert meta["ranges_requested"] == 8
    assert "limited to 1 of 8" in meta["warning"]


def test_incremental_refresh_backfills_one_range_per_run_and_preserves_recent_coverage():
    class FakeAPI:
        def __init__(self):
            self.calls = []
        def fixtures_between(self, start, end, timezone):
            self.calls.append((start, end, timezone))
            return {"response": [_fixture(end)]}

    base = [{
        "date": date(2026, 9, 3), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    api = FakeAPI()
    state = {}
    statuses = []
    for _ in range(8):
        rows, meta = fetch_recent_results_incremental(
            api, base, date(2026, 10, 24), state
        )
        assert len(rows) == 1
        state = meta["cache_state"]
        statuses.append(meta["status"])
    assert len(api.calls) == 8
    assert api.calls[0] == ("2026-10-18", "2026-10-24", "Africa/Lagos")
    assert api.calls[1] == ("2026-10-11", "2026-10-17", "Africa/Lagos")
    assert api.calls[-1] == ("2026-09-04", "2026-09-05", "Africa/Lagos")
    assert statuses[0] == "PARTIAL"
    assert statuses[-1] == "COMPLETE"
    assert state["backfill_complete"] is True
    assert state["latest_covered_through"] == "2026-10-24"

    # Once the historical gap is filled, the cursor advances to newly completed dates.
    _, next_meta = fetch_recent_results_incremental(
        api, base, date(2026, 10, 25), state
    )
    assert api.calls[-1] == ("2026-10-25", "2026-10-25", "Africa/Lagos")
    assert next_meta["cache_state"]["latest_covered_through"] == "2026-10-25"


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



def test_fetch_recent_results_falls_back_to_single_dates_when_range_parameters_are_rejected():
    class FakeAPI:
        def __init__(self):
            self.range_calls = []
            self.date_calls = []

        def fixtures_between(self, start, end, timezone):
            self.range_calls.append((start, end, timezone))
            raise FootballAPIError(
                "API reported errors: {'from': 'The From field need another parameter.', "
                "'to': 'The To field need another parameter.', "
                "'timezone': 'The Timezone field need another parameter.'}"
            )

        def fixtures(self, match_date, timezone):
            self.date_calls.append((match_date, timezone))
            return {"response": [_fixture(match_date, home=f"Home {match_date}", away=f"Away {match_date}")]}

    base = [{
        "date": date(2026, 9, 3), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    api = FakeAPI()
    rows, meta = fetch_recent_results(
        api, base, date(2026, 9, 5), max_chunk_days=7, timezone_name="Europe/London"
    )

    assert len(api.range_calls) == 1
    assert api.date_calls == [
        ("2026-09-04", "Europe/London"),
        ("2026-09-05", "Europe/London"),
    ]
    assert [row["date"] for row in rows] == [date(2026, 9, 4), date(2026, 9, 5)]
    assert meta["status"] == "COMPLETE"
    assert meta["results_added"] == 2
    assert meta["covered_from"] == "2026-09-04"
    assert meta["covered_through"] == "2026-09-05"


def test_incremental_refresh_keeps_accessible_dates_and_records_plan_gaps():
    class FakeAPI:
        def fixtures_between(self, start, end, timezone):
            return {
                "response": [_fixture(end, home="Recent Home", away="Recent Away")],
                "_veltrix_meta": {
                    "provider": "API-Football (API-Sports)",
                    "successful_dates": [
                        "2026-10-19", "2026-10-20", "2026-10-21",
                        "2026-10-22", "2026-10-23", "2026-10-24",
                    ],
                    "failed_dates": ["2026-10-18"],
                    "warning": "API-Football plan did not return historical fixtures for 2026-10-18.",
                },
            }

    base = [{
        "date": date(2026, 10, 10), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    rows, meta = fetch_recent_results_incremental(
        FakeAPI(), base, date(2026, 10, 24), {}
    )
    assert len(rows) == 1
    assert meta["status"] == "PARTIAL"
    assert meta["covered_from"] == "2026-10-19"
    assert meta["covered_through"] == "2026-10-24"
    assert meta["cache_state"]["history_plan_limited_dates"] == ["2026-10-18"]
    assert "history_gaps" not in meta["cache_state"]
    assert meta["cache_state"]["next_backfill_end_date"] == "2026-10-17"
    assert "plan did not return historical fixtures" in meta["warning"]



def test_incremental_refresh_retries_old_gaps_after_forward_coverage_is_current():
    class FakeAPI:
        def __init__(self):
            self.calls = []

        def fixtures_between(self, start, end, timezone):
            self.calls.append((start, end, timezone))
            return {
                "response": [_fixture(start, home="Gap Home", away="Gap Away")],
                "_veltrix_meta": {
                    "successful_dates": [start],
                    "failed_dates": [],
                },
            }

    base = [{
        "date": date(2026, 10, 10), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    state = {
        "coverage_state_version": 2,
        "backfill_anchor_end": "2026-10-24",
        "next_backfill_end_date": "2026-10-10",
        "latest_covered_through": "2026-10-24",
        "backfill_complete": True,
        "history_gaps": ["2026-10-18"],
    }
    api = FakeAPI()
    rows, meta = fetch_recent_results_incremental(api, base, date(2026, 10, 24), state)

    assert api.calls == [("2026-10-18", "2026-10-18", "Africa/Lagos")]
    assert [row["date"] for row in rows] == [date(2026, 10, 18)]
    assert "history_gaps" not in meta["cache_state"]
    assert meta["status"] == "COMPLETE"
    assert meta["cache_state"]["latest_covered_through"] == "2026-10-24"
    assert meta["cache_state"]["next_backfill_end_date"] == "2026-10-10"


def test_incremental_gap_retry_retains_subscription_blocked_dates_without_false_completion():
    class FakeAPI:
        def fixtures_between(self, start, end, timezone):
            return {
                "response": [],
                "_veltrix_meta": {
                    "successful_dates": [],
                    "failed_dates": [start],
                    "warning": f"API-Football plan did not return historical fixtures for {start}.",
                },
            }

    base = [{
        "date": date(2026, 10, 10), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    state = {
        "coverage_state_version": 2,
        "backfill_anchor_end": "2026-10-24",
        "next_backfill_end_date": "2026-10-10",
        "latest_covered_through": "2026-10-24",
        "backfill_complete": True,
        "history_gaps": ["2026-10-18"],
    }
    rows, meta = fetch_recent_results_incremental(FakeAPI(), base, date(2026, 10, 24), state)

    assert rows == []
    assert meta["status"] == "PARTIAL"
    assert "history_gaps" not in meta["cache_state"]
    assert meta["cache_state"]["history_plan_limited_dates"] == ["2026-10-18"]
    assert "plan did not return historical fixtures" in meta["warning"]
    assert meta["cache_state"]["backfill_complete"] is True



def test_gap_retry_throttle_allows_newer_history_to_catch_up_next_day():
    class FakeAPI:
        def __init__(self):
            self.calls = []

        def fixtures_between(self, start, end, timezone):
            self.calls.append((start, end, timezone))
            return {
                "response": [_fixture(end, home="Catchup Home", away="Catchup Away")],
                "_veltrix_meta": {
                    "successful_dates": [end],
                    "failed_dates": [],
                },
            }

    base = [{
        "date": date(2026, 10, 10), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    state = {
        "coverage_state_version": 2,
        "backfill_anchor_end": "2026-10-24",
        "next_backfill_end_date": "2026-10-10",
        "latest_covered_through": "2026-10-24",
        "backfill_complete": True,
        "history_gaps": ["2026-10-18"],
        "last_gap_retry_on": "2026-10-24",
    }
    api = FakeAPI()
    rows, meta = fetch_recent_results_incremental(api, base, date(2026, 10, 25), state)

    assert api.calls == [("2026-10-25", "2026-10-25", "Africa/Lagos")]
    assert [row["date"] for row in rows] == [date(2026, 10, 25)]
    assert meta["cache_state"]["history_gaps"] == ["2026-10-18"]
    assert meta["cache_state"]["latest_covered_through"] == "2026-10-25"



def test_legacy_plan_denied_dates_migrate_without_repeating_provider_requests():
    class FakeAPI:
        def fixtures_between(self, *args):
            pytest.fail("Known legacy plan-denied dates must not be retried")

    base = [{
        "date": date(2026, 10, 26), "division": "E0", "home": "Old", "away": "Older",
        "home_key": "old", "away_key": "older", "home_goals": 1, "away_goals": 0,
    }]
    legacy_state = {
        "backfill_anchor_end": "2026-10-26",
        "next_backfill_end_date": "2026-10-25",
        "latest_covered_through": "2026-10-26",
        "backfill_complete": True,
        "history_gaps": ["2026-09-21", "2026-09-22", "2026-10-11"],
    }
    rows, meta = fetch_recent_results_incremental(
        FakeAPI(), base, date(2026, 10, 26), legacy_state
    )
    assert rows == []
    assert meta["status"] == "GAPPED"
    assert "history_gaps" not in meta["cache_state"]
    assert meta["cache_state"]["history_plan_limited_dates"] == [
        "2026-09-21", "2026-09-22", "2026-10-11"
    ]
    assert meta["cache_state"]["coverage_state_version"] == 2


def test_provider_switch_retries_dates_blocked_by_previous_provider_plan():
    class NewProvider:
        provider_name = "5DollarFootballAPI"

        def __init__(self):
            self.calls = []

        def fixtures_between(self, start_date, end_date, timezone_name):
            self.calls.append((start_date, end_date, timezone_name))
            return {
                "response": [],
                "_veltrix_meta": {
                    "provider": "5DollarFootballAPI",
                    "successful_dates": [start_date],
                    "failed_dates": [],
                },
            }

    api = NewProvider()
    historical = [{"date": date(2026, 10, 10), "division": "E0"}]
    cache_state = {
        "source_provider": "API-Football",
        "coverage_state_version": 2,
        "backfill_anchor_end": "2026-10-20",
        "next_backfill_end_date": "2026-10-10",
        "latest_covered_through": "2026-10-20",
        "backfill_complete": True,
        "history_plan_limited_dates": ["2026-10-15"],
    }
    rows, sync = fetch_recent_results_incremental(
        api, historical, date(2026, 10, 20), cache_state,
    )
    assert rows == []
    assert api.calls == [("2026-10-15", "2026-10-15", "Africa/Lagos")]
    assert sync["cache_state"]["source_provider"] == "5DollarFootballAPI"
    assert "history_plan_limited_dates" not in sync["cache_state"]
    assert "history_gaps" not in sync["cache_state"]


def test_5dollar_empty_history_response_is_retryable_not_plan_limited():
    class NewProvider:
        provider_name = "5DollarFootballAPI"

        def fixtures_between(self, start_date, end_date, timezone_name):
            return {
                "response": [],
                "_veltrix_meta": {
                    "provider": "5DollarFootballAPI",
                    "successful_dates": [],
                    "failed_dates": [start_date],
                    "empty_response_dates": [start_date],
                    "warning": "No fixtures returned for 1 historical date(s); dates remain retryable.",
                },
            }

    cache_state = {
        "source_provider": "5DollarFootballAPI",
        "provider_error_classification_version": 1,
        "coverage_state_version": 2,
        "backfill_anchor_end": "2026-10-20",
        "next_backfill_end_date": "2026-10-10",
        "latest_covered_through": "2026-10-20",
        "backfill_complete": True,
        "history_gaps": ["2026-10-20"],
        "last_gap_retry_on": "2026-10-12",
    }
    _, sync = fetch_recent_results_incremental(
        NewProvider(), [{"date": date(2026, 10, 10), "division": "E0"}],
        date(2026, 10, 20), cache_state,
    )
    updated = sync["cache_state"]
    assert updated["history_gaps"] == ["2026-10-20"]
    assert "history_plan_limited_dates" not in updated
    assert sync["status"] == "PARTIAL"


def test_gap_retries_are_throttled_to_weekly_even_when_forward_coverage_is_current():
    class MustNotCall:
        provider_name = "5DollarFootballAPI"

        def fixtures_between(self, *args, **kwargs):
            raise AssertionError("Gap retry should be throttled.")

    cache_state = {
        "source_provider": "5DollarFootballAPI",
        "provider_error_classification_version": 1,
        "coverage_state_version": 2,
        "backfill_anchor_end": "2026-10-20",
        "next_backfill_end_date": "2026-10-10",
        "latest_covered_through": "2026-10-20",
        "backfill_complete": True,
        "history_gaps": ["2026-10-20"],
        "last_gap_retry_on": "2026-10-20",
    }
    _, sync = fetch_recent_results_incremental(
        MustNotCall(), [{"date": date(2026, 10, 10), "division": "E0"}],
        date(2026, 10, 20), cache_state,
    )
    assert sync["status"] == "GAPPED"
    assert sync["cache_state"]["history_gaps"] == ["2026-10-20"]


def test_idle_gap_state_never_reports_a_reversed_refresh_range():
    class MustNotCall:
        provider_name = "5DollarFootballAPI"

        def fixtures_between(self, *args, **kwargs):
            raise AssertionError("No forward dates exist; only the weekly gap retry is throttled.")

    historical = [{
        "date": date(2026, 10, 29), "division": "E0", "home": "Latest",
        "away": "Opponent", "home_key": "latest", "away_key": "opponent",
        "home_goals": 1, "away_goals": 0,
    }]
    state = {
        "source_provider": "5DollarFootballAPI",
        "provider_error_classification_version": 1,
        "coverage_state_version": 2,
        "backfill_anchor_end": "2026-10-28",
        "next_backfill_end_date": "2026-10-20",
        "latest_covered_through": "2026-10-28",
        "backfill_complete": True,
        "history_gaps": ["2026-10-10"],
        "last_gap_retry_on": "2026-10-28",
    }
    rows, sync = fetch_recent_results_incremental(
        MustNotCall(), historical, date(2026, 10, 29), state,
    )
    assert rows == []
    assert sync["status"] == "GAPPED"
    assert sync["requested_start"] is None
    assert sync["requested_end"] == "2026-10-29"
    assert sync["ranges_requested"] == 0
    assert sync["cache_state"]["history_gaps"] == ["2026-10-10"]


def test_gap_backfill_keeps_unverified_empty_dates_and_records_secondary_rows(tmp_path):
    import csv
    import json
    from scripts.backfill_history_gaps import run

    cache_path = tmp_path / "cache.json"
    fallback_path = tmp_path / "fallback.csv"
    output_path = tmp_path / "out.json"
    cache_path.write_text(json.dumps({
        "version": 2,
        "state": {"history_gaps": ["2026-09-28", "2026-09-29"]},
        "matches": [],
    }), encoding="utf-8")
    with fallback_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "match_date", "division", "home_team", "away_team", "home_goals", "away_goals",
        ])
        writer.writeheader()
        writer.writerow({
            "match_date": "2026-09-29", "division": "E0",
            "home_team": "Fallback FC", "away_team": "Other FC",
            "home_goals": 1, "away_goals": 0,
        })

    class FakeAPI:
        def leagues(self, page=1, per_page=100, active_since=None):
            return {"response": [{"id": 7, "name": "Premier League"}], "pagination": {"has_more": False}}

        def league_fixtures(self, league_id, start_date, end_date, timezone):
            return {
                "provider": "5DollarFootballAPI",
                "_veltrix_meta": {"pages_fetched": 1},
                "response": [{
                    "fixture": {"id": 124, "date": "2026-09-28T13:00:00Z", "status": {"short": "FT"}},
                    "teams": {"home": {"name": "League FC"}, "away": {"name": "League Away"}},
                    "goals": {"home": 3, "away": 1},
                    "league": {"code": "PL"},
                }],
            }

        def fixtures(self, day, timezone):
            if day == "2026-09-28":
                return {
                    "provider": "5DollarFootballAPI",
                    "_veltrix_meta": {"pages_fetched": 1},
                    "response": [{
                        "fixture": {"id": 123, "date": "2026-09-28T12:00:00Z", "status": {"short": "FT"}},
                        "teams": {"home": {"name": "Primary FC"}, "away": {"name": "Away FC"}},
                        "goals": {"home": 2, "away": 1},
                        "league": {"code": "PL"},
                    }],
                }
            return {"provider": "5DollarFootballAPI", "_veltrix_meta": {"pages_fetched": 1}, "response": []}

    class FakeSession:
        def get(self, url, timeout=30):
            import requests
            raise requests.ConnectionError("test disables external open-matchday access")

    report = run(cache_path, fallback_path, output_path, FakeAPI(), FakeSession())
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["primary_resolved_dates"] == len(report["all_resolved_dates"])
    assert set(report["all_resolved_dates"]).issubset({"2026-09-28", "2026-09-29"})
    assert saved["state"].get("history_gaps", []) == [
        day for day in ["2026-09-28", "2026-09-29"]
        if day not in report["all_resolved_dates"]
    ]
    assert len(saved["matches"]) >= 1
    assert all(row["source_provider"].startswith("5DollarFootballAPI") for row in saved["matches"])
    assert report["secondary_fallback_matches_added"] == 0


def test_historical_backfill_maps_country_prefixed_and_short_league_names():
    from scripts.backfill_history_gaps import _mapped_league_division

    assert _mapped_league_division({"id": 1, "name": "England - Premier League"}) == "PL"
    assert _mapped_league_division({"id": 2, "name": "La Liga"}) == "PD"
    assert _mapped_league_division({"id": 3, "short_name": "EPL"}) == "PL"
    assert _mapped_league_division({"id": 4, "league_name": "Bundesliga"}) == "BL1"
    assert _mapped_league_division({"id": 5, "name": "Unmapped competition"}) is None


def test_gap_backfill_rate_limit_does_not_advance_retry_cursor(tmp_path):
    import json
    from scripts.backfill_history_gaps import run
    from app.provider_adapters import ProviderAPIError

    cache_path = tmp_path / "cache.json"
    fallback_path = tmp_path / "fallback.csv"
    output_path = tmp_path / "out.json"
    cache_path.write_text(json.dumps({
        "version": 2,
        "state": {"history_gaps": ["2026-09-28"]},
        "matches": [],
    }), encoding="utf-8")
    fallback_path.write_text("match_date,division,home_team,away_team,home_goals,away_goals\n", encoding="utf-8")

    class RateLimitedAPI:
        def leagues(self, page=1, per_page=100):
            raise ProviderAPIError("Provider request failed with HTTP 429.")

        def fixtures(self, day, timezone):
            raise ProviderAPIError("Provider date endpoint returned HTTP 429.")
        def fixtures(self, day, timezone):
            raise ProviderAPIError("Provider date endpoint failed with HTTP 429.")

    class OfflineSession:
        def get(self, url, timeout=30):
            import requests
            raise requests.ConnectionError("offline unit test")

    report = run(cache_path, fallback_path, output_path, RateLimitedAPI(), OfflineSession())
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "PROVIDER_RATE_LIMITED"
    assert saved["state"]["history_gaps"] == ["2026-09-28"]
    assert "last_gap_retry_on" not in saved["state"]


def test_gap_backfill_daily_cooldown_skips_provider_calls(tmp_path):
    import json
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from scripts.backfill_history_gaps import run

    today = datetime.now(ZoneInfo("Africa/Lagos")).date()
    cache_path = tmp_path / "cache.json"
    fallback_path = tmp_path / "fallback.csv"
    output_path = tmp_path / "out.json"
    cache_path.write_text(json.dumps({
        "version": 2,
        "state": {"history_gaps": ["2026-09-28"], "last_gap_retry_on": today.isoformat()},
        "matches": [],
    }), encoding="utf-8")
    fallback_path.write_text("match_date,division,home_team,away_team,home_goals,away_goals\n", encoding="utf-8")

    class MustNotCallAPI:
        def leagues(self, **kwargs):
            raise AssertionError("Provider must not be called during retry cooldown.")

    class OfflineSession:
        def get(self, url, timeout=30):
            import requests
            raise requests.ConnectionError("offline unit test")

    report = run(cache_path, fallback_path, output_path, MustNotCallAPI(), OfflineSession())
    assert report["status"] == "PARTIAL_PROVIDER_RETRY_COOLDOWN"
    assert report["provider_retry_cooldown_active"] is True
    assert report["provider_retry_after_date"] == (today + timedelta(days=1)).isoformat()


def test_gap_backfill_excludes_noncommercial_feed_and_preserves_gaps_during_cooldown(tmp_path):
    import json
    from scripts.backfill_history_gaps import run

    gaps = ["2026-09-28", "2026-09-29"]
    cache_path = tmp_path / "cache.json"
    fallback_path = tmp_path / "fallback.csv"
    output_path = tmp_path / "out.json"
    cache_path.write_text(json.dumps({
        "version": 2,
        "state": {"history_gaps": gaps, "last_gap_retry_on": "2026-11-02"},
        "matches": [],
    }), encoding="utf-8")
    fallback_path.write_text(
        "match_date,division,home_team,away_team,home_goals,away_goals\\n",
        encoding="utf-8",
    )

    class ForbiddenPrimaryAPI:
        def __getattr__(self, name):
            raise AssertionError(f"Primary API should not be called during cooldown: {name}")

    class ForbiddenSession:
        def get(self, *args, **kwargs):
            raise AssertionError("Non-commercial historical feed must not be requested.")

    report = run(cache_path, fallback_path, output_path, ForbiddenPrimaryAPI(), ForbiddenSession())
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "PARTIAL_PROVIDER_RETRY_COOLDOWN"
    assert report["provider_retry_cooldown_active"] is True
    assert report["open_matchday"]["status"] == "SKIPPED_NONCOMMERCIAL_LICENSE"
    assert report["open_matchday_resolved_dates"] == []
    assert saved["state"]["history_gaps"] == gaps
    assert saved["matches"] == []


def test_noncommercial_open_matchday_source_is_never_ingested():
    from scripts.backfill_history_gaps import _open_matchday_backfill

    class ForbiddenSession:
        def get(self, *args, **kwargs):
            raise AssertionError("Non-commercial source must not be requested")

    rows, audit = _open_matchday_backfill(ForbiddenSession(), ["2026-09-28"])
    assert rows == []
    assert audit["status"] == "SKIPPED_NONCOMMERCIAL_LICENSE"
    assert audit["matches_added"] == 0



def test_gap_backfill_recovers_completed_dates_from_primary_date_endpoint(tmp_path):
    import json
    from scripts.backfill_history_gaps import run

    gaps = ["2026-09-28", "2026-09-29"]
    cache_path = tmp_path / "cache.json"
    fallback_path = tmp_path / "fallback.csv"
    output_path = tmp_path / "out.json"
    cache_path.write_text(json.dumps({
        "version": 2, "state": {"history_gaps": gaps}, "matches": [],
    }), encoding="utf-8")
    fallback_path.write_text(
        "match_date,division,home_team,away_team,home_goals,away_goals\n",
        encoding="utf-8",
    )

    class FakeSession:
        def get(self, *args, **kwargs):
            import requests
            raise requests.ConnectionError("offline test")

    class DateAPI:
        def leagues(self, **kwargs):
            return {"response": [], "pagination": {"has_more": False}}
        def fixtures(self, day, timezone):
            if day == "2026-09-28":
                return {
                    "_veltrix_meta": {"pages_fetched": 1},
                    "response": [{
                        "fixture": {"id": 987, "date": "2026-09-28T12:00:00Z", "status": {"short": "FT"}},
                        "teams": {"home": {"name": "Primary Home"}, "away": {"name": "Primary Away"}},
                        "goals": {"home": 2, "away": 0},
                        "league": {"code": "PL"},
                    }],
                }
            return {"_veltrix_meta": {"pages_fetched": 1}, "response": []}

    report = run(cache_path, fallback_path, output_path, DateAPI(), FakeSession())
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["date_endpoint"]["resolved_dates"] == ["2026-09-28"]
    assert report["date_endpoint"]["matches_added"] == 1
    assert report["primary_resolved_dates"] == 1
    assert saved["state"]["history_gaps"] == ["2026-09-29"]
    assert saved["matches"][0]["source_provider"] == "5DollarFootballAPI_DATE_FIXTURES"


def test_gap_backfill_uses_date_endpoint_after_league_catalogue_429(tmp_path):
    import json
    from scripts.backfill_history_gaps import run
    from app.provider_adapters import ProviderAPIError

    cache_path = tmp_path / "cache.json"
    fallback_path = tmp_path / "fallback.csv"
    output_path = tmp_path / "out.json"
    cache_path.write_text(json.dumps({
        "version": 2,
        "state": {"history_gaps": ["2026-09-28"]},
        "matches": [],
    }), encoding="utf-8")
    fallback_path.write_text(
        "match_date,division,home_team,away_team,home_goals,away_goals,full_time_result\\n",
        encoding="utf-8",
    )

    class DateEndpointAPI:
        def leagues(self, page=1, per_page=100):
            raise ProviderAPIError("League catalogue returned HTTP 429.")

        def fixtures(self, day, timezone):
            assert day == "2026-09-28"
            assert timezone == "Africa/Lagos"
            return {
                "provider": "5DollarFootballAPI",
                "_veltrix_meta": {"pages_fetched": 1},
                "response": [{
                    "fixture": {
                        "id": 987, "date": "2026-09-28T12:00:00Z",
                        "status": {"short": "FT"},
                    },
                    "teams": {
                        "home": {"name": "Primary Home"},
                        "away": {"name": "Primary Away"},
                    },
                    "goals": {"home": 2, "away": 0},
                    "league": {"code": "PL"},
                }],
            }

    report = run(cache_path, fallback_path, output_path, DateEndpointAPI())
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "COMPLETE"
    assert report["league_endpoint_scan"]["error_type"] == "HTTP_429"
    assert report["date_endpoint"]["resolved_dates"] == ["2026-09-28"]
    assert saved["state"].get("history_gaps") is None
    assert saved["matches"][0]["source_provider"] == "5DollarFootballAPI_DATE_FIXTURES"


def test_gap_backfill_probes_date_endpoint_after_league_catalogue_429(tmp_path):
    import json
    from scripts.backfill_history_gaps import run
    from app.provider_adapters import ProviderAPIError

    day = "2026-09-28"
    cache_path = tmp_path / "cache.json"
    fallback_path = tmp_path / "fallback.csv"
    output_path = tmp_path / "out.json"
    cache_path.write_text(json.dumps({
        "version": 2, "state": {"history_gaps": [day]}, "matches": [],
    }), encoding="utf-8")
    fallback_path.write_text(
        "match_date,division,home_team,away_team,home_goals,away_goals\n",
        encoding="utf-8",
    )

    class FakeSession:
        def get(self, *args, **kwargs):
            import requests
            raise requests.ConnectionError("offline test")

    class API:
        def leagues(self, **kwargs):
            raise ProviderAPIError("League catalogue HTTP 429.")
        def fixtures(self, requested_day, timezone):
            return {
                "_veltrix_meta": {"pages_fetched": 1},
                "response": [{
                    "fixture": {"id": 654, "date": f"{requested_day}T12:00:00Z", "status": {"short": "FT"}},
                    "teams": {"home": {"name": "Date Endpoint Home"}, "away": {"name": "Date Endpoint Away"}},
                    "goals": {"home": 1, "away": 0},
                    "league": {"code": "PL"},
                }],
            }

    report = run(cache_path, fallback_path, output_path, API(), FakeSession(), force=True)
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["date_endpoint"]["resolved_dates"] == [day]
    assert report["date_endpoint"]["matches_added"] == 1
    assert report["status"] == "COMPLETE"
    assert not saved["state"].get("history_gaps")
    assert saved["matches"][0]["source_provider"] == "5DollarFootballAPI_DATE_FIXTURES"
