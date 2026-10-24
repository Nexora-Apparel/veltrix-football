from __future__ import annotations

import json
from datetime import date

import pytest

from scripts import run_daily_predictions as daily_runner


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
    }


def _run_args(monkeypatch, output):
    monkeypatch.setattr(
        "sys.argv",
        ["run_daily_predictions.py", "--date", "2026-10-23", "--history", "history.csv", "--output", str(output)],
    )


def test_daily_runner_skips_extra_history_requests_when_no_future_fixtures(tmp_path, monkeypatch):
    output = tmp_path / "reports" / "daily.json"
    _run_args(monkeypatch, output)
    monkeypatch.setattr(daily_runner, "get_settings", lambda: object())

    class FakeAPI:
        def __init__(self, settings):
            pass
        def fixtures(self, target_date, timezone):
            return {"response": []}
        def fixtures_between(self, *args):
            pytest.fail("Recent history should not be queried without future fixtures.")

    monkeypatch.setattr(daily_runner, "FootballAPI", FakeAPI)
    monkeypatch.setattr(daily_runner, "load_historical_matches", lambda path: [])
    monkeypatch.setattr(daily_runner, "build_daily_report", lambda *args, **kwargs: _report(0))
    monkeypatch.setattr(
        daily_runner, "fetch_recent_results",
        lambda *args, **kwargs: pytest.fail("Recent history should not be refreshed."),
    )

    daily_runner.main()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["recent_results_sync"]["status"] == "SKIPPED_NO_FUTURE_FIXTURES"
    assert report["recent_results_sync"]["results_added"] == 0


def test_daily_runner_refreshes_history_only_when_future_fixtures_exist(tmp_path, monkeypatch):
    output = tmp_path / "reports" / "daily.json"
    _run_args(monkeypatch, output)
    monkeypatch.setattr(daily_runner, "get_settings", lambda: object())
    base_history = [{"date": date(2026, 10, 22)}]
    monkeypatch.setattr(daily_runner, "load_historical_matches", lambda path: base_history)

    class FakeAPI:
        def __init__(self, settings):
            pass
        def fixtures(self, target_date, timezone):
            return {"response": [{"fixture": {"id": 1}}]}

    monkeypatch.setattr(daily_runner, "FootballAPI", FakeAPI)
    calls = []
    def fake_build(payload, history_path, **kwargs):
        calls.append(kwargs)
        return _report(1)
    monkeypatch.setattr(daily_runner, "build_daily_report", fake_build)
    recent_rows = [{"date": date(2026, 10, 22), "home": "A", "away": "B"}]
    sync = {
        "status": "COMPLETE",
        "results_added": 1,
        "requested_start": "2026-10-23",
        "requested_end": "2026-10-22",
        "covered_from": "2026-10-23",
        "covered_through": "2026-10-22",
        "ranges_succeeded": 1,
        "warning": None,
    }
    monkeypatch.setattr(
        daily_runner, "fetch_recent_results",
        lambda api, history, end_date: (recent_rows, sync),
    )

    daily_runner.main()
    report = json.loads(output.read_text(encoding="utf-8"))
    assert len(calls) == 2
    assert calls[0].get("additional_historical_matches") is None
    assert calls[1]["additional_historical_matches"] == recent_rows
    assert report["recent_results_sync"]["status"] == "COMPLETE"
