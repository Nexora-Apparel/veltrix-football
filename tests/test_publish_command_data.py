from datetime import datetime, timezone

from scripts.publish_command_data import _archive_report_path, _valid_recent_cache


def test_recent_cache_publisher_accepts_current_v2_schema():
    assert _valid_recent_cache({
        "version": 2,
        "matches": [{"date": "2026-10-27"}],
        "state": {"next_backfill_end_date": "2026-10-20"},
    })


def test_recent_cache_publisher_accepts_legacy_v1_schema():
    assert _valid_recent_cache({
        "version": 1,
        "matches": [],
        "state": {},
    })


def test_recent_cache_publisher_rejects_invalid_schema():
    assert not _valid_recent_cache({"version": 3, "matches": [], "state": {}})
    assert not _valid_recent_cache({"version": 2, "matches": []})
    assert not _valid_recent_cache({"version": 2, "matches": [], "state": None})



def test_daily_report_archive_path_is_date_scoped_and_immutable():
    report = {"as_of_date": "2026-10-31"}
    published = datetime(2026, 10, 31, 15, 30, 12, 123456, tzinfo=timezone.utc)
    assert _archive_report_path(report, published) == (
        "public-data/archive/2026-10-31/daily_predictions_20261031T153012123456Z.json"
    )


def test_daily_report_archive_path_rejects_invalid_report_date():
    import pytest

    with pytest.raises(ValueError):
        _archive_report_path({"as_of_date": "not-a-date"}, datetime.now(timezone.utc))
