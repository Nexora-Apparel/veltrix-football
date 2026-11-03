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
            {"status": "EXPERIMENTAL_ONLY", "kickoff_local": None, "probabilities": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}},
        ],
    }


def test_filter_keeps_all_same_day_rows_and_withholds_past_forecasts():
    now = datetime(2026, 10, 25, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    report = filter_report_for_delivery(sample_report(), now)
    assert len(report["predictions"]) == 4
    assert report["predictions_created"] == 1
    assert report["future_fixtures_considered"] == 2
    assert report["same_day_fixtures_retained"] == 4
    assert report["kickoff_unverified_fixtures"] == 1
    unverified = next(row for row in report["predictions"] if row.get("status") == "KICKOFF_UNVERIFIED")
    assert "probabilities" not in unverified
    assert report["past_kickoffs_excluded"] == 0
    assert report["past_kickoffs_retained"] == 1
    passed = next(row for row in report["predictions"] if row.get("status") == "KICKOFF_PASSED")
    assert "probabilities" not in passed
    assert "btts_yes" not in passed
    assert report["unsupported_competitions"] == 1
    assert report["insufficient_history"] == 0
    assert report["predictions_created"] == 1
    assert report["primary_model_counts"] == {"elo": 1}
    assert report["possible_team_name_mismatches"] == 1
    assert report["delivery_filter"]["missing_or_invalid_kickoff_rows_excluded"] == 0
    assert report["delivery_filter"]["kickoff_unverified_rows_retained"] == 1
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
    assert "probabilities" not in unsafe
    assert filtered["predictions_created"] == 0
    assert filtered["insufficient_history"] == 1
    assert filtered["delivery_filter"]["unsafe_team_identity_rows_withheld"] == 1


def test_reused_snapshot_is_marked_and_coverage_gap_is_preserved():
    report = sample_report()
    report["recent_results_sync"] = {
        "status": "PARTIAL",
        "requested_start": "2026-09-04",
        "requested_end": "2026-10-24",
        "covered_from": "2026-10-18",
        "covered_through": "2026-10-24",
        "ranges_succeeded": 1,
        "ranges_requested": 8,
    }
    report["historical_data_through"] = "2026-10-24"
    now = datetime(2026, 10, 25, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    filtered = filter_report_for_delivery(report, now)
    assert filtered["publication_status"] == "REUSED_SNAPSHOT_NOT_REFRESHED"
    assert "did not fetch fresh fixtures" in filtered["publication_notice"]
    assert filtered["historical_data_coverage"]["status"] == "GAPPED_OR_STALE"
    assert filtered["historical_data_coverage"]["contiguous_through"] == "2026-09-03"
    assert filtered["historical_data_coverage"]["ranges_succeeded"] == 1
    assert filtered["historical_data_coverage"]["ranges_requested"] == 8


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
    assert len(filtered["predictions"]) == 4
    assert (
        filtered["predictions_created"]
        + filtered["insufficient_history"]
        + filtered["unsupported_competitions"]
        + filtered["kickoff_unverified_fixtures"]
        + filtered["fixture_status_counts"]["KICKOFF_PASSED"]
    ) == len(filtered["predictions"])
    assert filtered["predictions_created"] == 1
    assert filtered["unsupported_competitions"] == 1
    assert filtered["unsupported_competition_breakdown"] == {"Unknown League": 1}



def test_filter_withholds_legacy_low_data_forecasts_and_keeps_fixture_visible():
    report = {
        "as_of_date": "2026-10-25",
        "timezone": "Africa/Lagos",
        "same_day_only": True,
        "predictions": [{
            "status": "EXPERIMENTAL_LOW_DATA",
            "home_team": "Unknown Home",
            "away_team": "Unknown Away",
            "kickoff_local": "2026-10-25T18:00:00+01:00",
            "model": "experimental_global_licensed_prior_poisson",
            "probabilities": {"home_win": .45, "draw": .28, "away_win": .27},
            "btts_yes": .6,
            "over_2_5": .55,
        }],
    }
    now = datetime(2026, 10, 25, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    filtered = filter_report_for_delivery(report, now)
    row = filtered["predictions"][0]
    assert filtered["same_day_fixtures_retained"] == 1
    assert filtered["predictions_created"] == 0
    assert filtered["low_data_forecasts"] == 0
    assert filtered["insufficient_history"] == 1
    assert row["status"] == "INSUFFICIENT_HISTORY"
    assert "probabilities" not in row
    assert "btts_yes" not in row
    assert "over_2_5" not in row
    assert filtered["fixture_status_counts"]["EXPERIMENTAL_LOW_DATA"] == 0
