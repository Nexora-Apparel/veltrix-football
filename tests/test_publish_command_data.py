from scripts.publish_command_data import _valid_recent_cache


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
