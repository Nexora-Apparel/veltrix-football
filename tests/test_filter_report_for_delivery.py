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
            {"status": "EXPERIMENTAL_ONLY", "kickoff_local": "2026-10-25T10:00:00+01:00"},
            {"status": "EXPERIMENTAL_ONLY", "kickoff_local": "2026-10-25T07:00:00+01:00"},
            {"status": "UNSUPPORTED_COMPETITION", "kickoff_local": "2026-10-25T12:00:00+01:00"},
            {"status": "EXPERIMENTAL_ONLY", "kickoff_local": None},
        ],
    }


def test_filter_keeps_only_future_same_day_rows_and_recomputes_count():
    now = datetime(2026, 10, 25, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    report = filter_report_for_delivery(sample_report(), now)
    assert len(report["predictions"]) == 2
    assert report["predictions_created"] == 1
    assert report["future_fixtures_considered"] == 2
    assert report["past_kickoffs_excluded"] == 2
    assert report["delivery_filter"]["applied"] is True


def test_filter_rejects_stale_report_date():
    now = datetime(2026, 10, 26, 8, 0, tzinfo=ZoneInfo("Africa/Lagos"))
    with pytest.raises(ValueError, match="not today"):
        filter_report_for_delivery(sample_report(), now)


def test_filter_rejects_report_without_same_day_guard():
    report = sample_report()
    report["same_day_only"] = False
    with pytest.raises(ValueError, match="same-day"):
        filter_report_for_delivery(report)
