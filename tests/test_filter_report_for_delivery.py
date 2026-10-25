from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.filter_report_for_delivery import filter_report_for_delivery


def sample_report():
    return {
        "as_of_date": "2026-10-25",
        "timezone": "Africa/Lagos",
        "same_day_only": True,
        "past_kickoffs_excluded": 0,
        "predictions": [
            {"status": "EXPERIMENTAL_ONLY", "kickoff_local": "2026-10-25T10:00:00+01:00", "model": "elo", "probabilities": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "team_name_matches": {"home": {"fixture_name": "Alph FC", "historical_key": "alpha", "auto_matched": True}, "away": {"fixture_name": "Beta FC", "historical_key": "beta", "auto_matched": False}}},
            {"status": "EXPERIMENTAL_ONLY", "kickoff_local": "2026-10-25T07:00:00+01:00", "model": "poisson", "probabilities": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}},
            {"status": "UNSUPPORTED_COMPETITION", "kickoff_local": "2026-10-25T12:00:00+01:00", "league": "Unknown League"},
            {"status": "EXPERIMENTAL_ONLY", "kickoff_local": None},
        ],
    }


def test_filter_keeps_only_future_same_day_rows_and_recomputes_count():
    now = datetime(2026, 10, 25, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    report = filter_report_for_delivery(sample_report(), now)
    assert len(report["predictions"]) == 2
    assert report["predictions_created"] == 1
    assert report["future_fixtures_considered"] == 2
    assert report["past_kickoffs_excluded"] == 1
    assert report["unsupported_competitions"] == 1
    assert report["insufficient_history"] == 0
    assert report["predictions_created"] == 1
    assert report["primary_model_counts"] == {"elo": 1}
    assert report["possible_team_name_mismatches"] == 1
    assert report["delivery_filter"]["missing_or_invalid_kickoff_rows_excluded"] == 1
    assert report["delivery_filter"]["applied"] is True


def test_filter_withholds_legacy_forecast_with_unsafe_team_identity():
    report = sample_report()
    report["predictions"][0]["team_name_matches"] = {
        "home": {
            "fixture_name": "Konyaspor U19",
            "historical_key": "konyaspor",
            "auto_matched": True,
        },
        "away": {
            "fixture_name": "Model FC",
            "historical_key": "model",
            "auto_matched": False,
        },
    }
    now = datetime(2026, 10, 25, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    filtered = filter_report_for_delivery(report, now)
    unsafe = next(row for row in filtered["predictions"] if row.get("team_identity_withheld"))
    assert unsafe["status"] == "INSUFFICIENT_HISTORY"
    assert "unsafe fuzzy team-name match" in unsafe["reason"]
    assert filtered["predictions_created"] == 0
    assert filtered["insufficient_history"] == 1
    assert filtered["delivery_filter"]["unsafe_team_identity_rows_withheld"] == 1


def test_filter_rejects_stale_report_date():
    now = datetime(2026, 10, 26, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    with pytest.raises(ValueError, match="not today"):
        filter_report_for_delivery(sample_report(), now)


def test_filter_rejects_report_without_same_day_guard():
    report = sample_report()
    report["same_day_only"] = False
    with pytest.raises(ValueError, match="same-day"):
        filter_report_for_delivery(report)


def test_filter_recomputes_status_counts_after_removing_rows():
    report = sample_report()
    report.update({
        "predictions_created": 99,
        "insufficient_history": 88,
        "unsupported_competitions": 77,
        "primary_model_counts": {"stale": 99},
    })
    now = datetime(2026, 10, 25, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    filtered = filter_report_for_delivery(report, now)
    assert len(filtered["predictions"]) == 2
    assert (
        filtered["predictions_created"]
        + filtered["insufficient_history"]
        + filtered["unsupported_competitions"]
    ) == len(filtered["predictions"])
    assert filtered["predictions_created"] == 1
    assert filtered["unsupported_competitions"] == 1
    assert filtered["unsupported_competition_breakdown"] == {"Unknown League": 1}
