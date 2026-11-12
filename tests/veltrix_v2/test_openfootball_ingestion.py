from datetime import date, time

import pytest

from veltrix_v2.ingestion.openfootball import parse_dataset, parse_match


def test_parse_preserves_date_only_precision_without_fabricating_timezone():
    item = parse_match(
        {"date": "2026-11-07", "team1": "Arsenal FC", "team2": "Chelsea FC", "score": {"ft": [2, 1]}},
        0,
    )
    assert item.match_date == date(2026, 11, 7)
    assert item.local_time is None
    assert item.timestamp_precision == "date_only"
    assert item.has_full_time_score
    assert (item.full_time_home, item.full_time_away) == (2, 1)


def test_parse_retains_unzoned_local_clock_without_converting_to_utc():
    item = parse_match(
        {"date": "2026-11-07", "time": "17:30", "team1": "A", "team2": "B", "score": {}},
        3,
    )
    assert item.local_time == time(17, 30)
    assert item.timestamp_precision == "local_datetime_unzoned"
    assert item.raw_time == "17:30"
    assert not item.has_full_time_score


def test_invalid_score_fails_closed():
    with pytest.raises(ValueError):
        parse_match({"date": "2026-11-07", "team1": "A", "team2": "B", "score": {"ft": [1, -1]}}, 0)


def test_dataset_requires_all_rows_to_be_objects():
    with pytest.raises(ValueError):
        parse_dataset({"name": "League", "matches": [{"date": "2026-11-07", "team1": "A", "team2": "B"}, None]})



def test_explicit_clock_offset_is_preserved_without_inventing_iana_zone():
    match = parse_match(
        {"date": "2026-10-01", "time": "20:00:00+02:00", "team1": "A", "team2": "B"},
        0,
    )
    assert match.timestamp_precision == "local_datetime_with_utc_offset"
    assert match.local_time is not None
    assert match.local_time.utcoffset().total_seconds() == 7200
