from __future__ import annotations

import json
from datetime import date

from scripts import run_daily_predictions as daily_runner


def test_combined_odds_status_prefers_verified_api_sports_report_matches():
    assert daily_runner._combined_odds_status("NO_VALID_1X2_ODDS", 5) == "AVAILABLE"
    assert daily_runner._combined_odds_status("NO_VALID_1X2_ODDS", 0) == "NO_VALID_1X2_ODDS"
    assert daily_runner._combined_odds_status("UNAVAILABLE", 0) == "UNAVAILABLE"


def test_api_sports_odds_attach_by_local_date_and_team_names_not_provider_ids():
    report = {
        "predictions": [{
            "fixture_id": 11,
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "kickoff_local": "2026-10-27T19:00:00+01:00",
            "status": "EXPERIMENTAL_ONLY",
        }]
    }
    payload = {"response": [
        {"match_id": "9001", "home_team": "Arsenal", "away_team": "Chelsea",
         "date": "2026-10-27", "odds": {"home": 2.0, "draw": 3.0, "away": 4.0}},
        {"match_id": "9002", "home_team": "Arsenal", "away_team": "Chelsea",
         "date": "2026-10-27", "odds": {"home": 2.2, "draw": 3.1, "away": 3.8}},
        {"match_id": "9003", "home_team": "Arsenal", "away_team": "Chelsea",
         "date": "2026-10-28", "odds": {"home": 1.5, "draw": 3.0, "away": 5.0}},
    ]}
    attached = daily_runner._merge_api_sports_market_odds(report, payload)
    assert attached == 1
    market = report["predictions"][0]["market_probabilities"]
    assert set(market) == {"home_win", "draw", "away_win"}
    assert abs(sum(market.values()) - 1.0) < 1e-5
    assert report["predictions"][0]["market_bookmakers_count"] == 2
    assert report["predictions"][0]["market_model"] == "api_sports_bookmaker_consensus"


def test_api_sports_odds_reject_incomplete_or_invalid_1x2_prices():
    report = {"predictions": [{
        "home_team": "Arsenal", "away_team": "Chelsea",
        "kickoff_local": "2026-10-27T19:00:00+01:00", "status": "EXPERIMENTAL_ONLY",
    }]}
    payload = {"response": [{
        "home_team": "Arsenal", "away_team": "Chelsea", "date": "2026-10-27",
        "odds": {"home": 2.0, "draw": 3.0},
    }]}
    assert daily_runner._merge_api_sports_market_odds(report, payload) == 0
    assert "market_probabilities" not in report["predictions"][0]


def _report(future_fixtures: int) -> dict:
    return {
        "as_of_date": "2026-10-23",
        "model_status": "EXPERIMENTAL_NOT_VALIDATED",
        "fixtures_received": 1,
        "same_day_pre_match_fixtures": future_fixtures,
        "future_fixtures_considered": future_fixtures,
        "past_kickoffs_excluded": 0,
        "fixtures_excluded_other_date_or_status": 0,
        "predictions_created": 0,
        "insufficient_history": 0,
        "unsupported_competitions": 0,
        "unsupported_competition_breakdown": {},
        "possible_team_name_mismatches": 0,
        "historical_data_through": "2026-10-22",
        "historical_matches_available": 100,
        "predictions": [],
    }


def _run_args(monkeypatch, output):
    monkeypatch.setattr(
        "sys.argv",
        ["run_daily_predictions.py", "--date", "2026-10-23", "--history", "history.csv", "--output", str(output), "--recent-cache", str(output.parent / "recent_results_cache.json")],
    )


def _recent_row():
    return [{
        "date": date(2026, 10, 22), "division": "E0",
        "home": "A", "away": "B", "home_key": "a", "away_key": "b",
        "home_goals": 1, "away_goals": 0,
    }]


def _sync():
    return {
        "status": "COMPLETE",
        "results_added": 1,
        "requested_start": "2026-10-21",
        "requested_end": "2026-10-22",
        "covered_from": "2026-10-21",
        "covered_through": "2026-10-22",
        "ranges_succeeded": 1,
        "warning": None,
        "cache_state": {
            "backfill_complete": True,
            "latest_covered_through": "2026-10-22",
            "next_backfill_end_date": "2026-10-19",
            "backfill_anchor_end": "2026-10-22",
        },
    }


def test_daily_runner_refreshes_history_even_when_no_future_fixtures(tmp_path, monkeypatch):
    output = tmp_path / "reports" / "daily.json"
    _run_args(monkeypatch, output)
    monkeypatch.setattr(daily_runner, "get_settings", lambda: object())
    base_history = [{"date": date(2026, 10, 20)}]
    recent_rows = _recent_row()
    monkeypatch.setattr(daily_runner, "load_historical_matches", lambda path: base_history)

    class FakeAPI:
        def __init__(self, settings):
            pass
        def fixtures(self, target_date, timezone):
            return {"response": []}
        def odds_for_date(self, *args):
            raise AssertionError("Odds should not be requested when no future fixtures remain.")

    monkeypatch.setattr(daily_runner, "FootballAPI", FakeAPI)
    refresh_calls = []
    monkeypatch.setattr(
        daily_runner, "fetch_recent_results_incremental",
        lambda api, history, end_date, **kwargs: (
            refresh_calls.append((history, end_date, kwargs)) or (recent_rows, _sync())
        ),
    )
    build_calls = []
    monkeypatch.setattr(
        daily_runner, "build_daily_report",
        lambda *args, **kwargs: (build_calls.append(kwargs) or _report(0)),
    )

    daily_runner.main()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(refresh_calls) == 1
    assert refresh_calls[0][1] == date(2026, 10, 22)
    assert refresh_calls[0][2]["timezone_name"] == "Africa/Lagos"
    assert len(build_calls) == 1
    assert build_calls[0]["additional_historical_matches"] == recent_rows
    assert report["recent_results_sync"]["status"] == "COMPLETE"
    assert report["recent_results_sync"]["results_added"] == 1
    assert report["historical_data_coverage"]["status"] == "CONTIGUOUS_THROUGH_TARGET_MINUS_ONE"
    assert report["historical_data_coverage"]["contiguous_through"] == "2026-10-22"
    assert report["historical_data_coverage"]["latest_available_match_date"] == "2026-10-22"
    assert report["live_odds_sync"]["status"] == "SKIPPED_NO_FUTURE_FIXTURES"


def test_daily_runner_refreshes_history_and_requests_odds_for_future_fixtures(tmp_path, monkeypatch):
    output = tmp_path / "reports" / "daily.json"
    _run_args(monkeypatch, output)
    monkeypatch.setattr(daily_runner, "get_settings", lambda: object())
    base_history = [{"date": date(2026, 10, 20)}]
    recent_rows = _recent_row()
    monkeypatch.setattr(daily_runner, "load_historical_matches", lambda path: base_history)

    class FakeAPI:
        def __init__(self, settings):
            pass
        def fixtures(self, target_date, timezone):
            # Deliberately malformed fixture data means it cannot be counted as a future match.
            return {"response": []}
        def odds_for_date(self, target_date, timezone):
            return {"response": []}

    monkeypatch.setattr(daily_runner, "FootballAPI", FakeAPI)
    monkeypatch.setattr(
        daily_runner, "_has_future_fixtures", lambda payload, target_date, timezone_name: True
    )
    monkeypatch.setattr(
        daily_runner, "fetch_recent_results_incremental",
        lambda api, history, end_date, **kwargs: (recent_rows, _sync()),
    )
    build_calls = []
    monkeypatch.setattr(
        daily_runner, "build_daily_report",
        lambda *args, **kwargs: (build_calls.append(kwargs) or _report(1)),
    )

    daily_runner.main()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(build_calls) == 1
    assert build_calls[0]["additional_historical_matches"] == recent_rows
    assert report["recent_results_sync"]["status"] == "COMPLETE"
    assert report["historical_data_coverage"]["status"] == "CONTIGUOUS_THROUGH_TARGET_MINUS_ONE"
    assert report["live_odds_sync"]["status"] == "NO_VALID_1X2_ODDS"
    assert report["live_odds_sync"]["football_api_status"] == "NO_VALID_1X2_ODDS"
    assert report["live_odds_sync"]["football_api_fixtures_with_odds"] == 0
