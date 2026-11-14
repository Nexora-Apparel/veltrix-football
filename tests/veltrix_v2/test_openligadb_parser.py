from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from veltrix_v2.data.openligadb import parse_openligadb_response

UTC = timezone.utc
RETRIEVED = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def match(**changes):
    row = {
        "matchID": 7001,
        "matchDateTimeUTC": "2026-11-12T19:30:00Z",
        "matchDateTime": "2026-11-12T20:30:00",
        "leagueId": 3,
        "leagueName": "Example League",
        "leagueShortcut": "ex1",
        "leagueSeason": 2026,
        "lastUpdateDateTime": "2026-11-12T22:00:00+01:00",
        "matchIsFinished": True,
        "team1": {"teamId": 11, "teamName": "Home FC"},
        "team2": {"teamId": 22, "teamName": "Away FC"},
        "matchResults": [
            {"resultTypeID": 2, "resultTypeKind": "After90Minutes",
             "resultName": "Endergebnis", "resultOrderID": 1, "points": 2},
            {"resultTypeID": 3, "resultTypeKind": "HalfTime",
             "resultName": "Halbzeit", "resultOrderID": 2, "points": 1},
        ],
    }
    row.update(changes)
    return row


def raw(rows):
    return json.dumps(rows, separators=(",", ":")).encode("utf-8")


def test_parses_match_and_preserves_all_result_types_and_raw_hash():
    payload = raw([match()])
    report = parse_openligadb_response(payload, retrieved_at=RETRIEVED)
    assert report.accepted_count == 1
    parsed = report.matches[0]
    assert parsed.provider_match_id == 7001
    assert parsed.kickoff_at == datetime(2026, 11, 12, 19, 30, tzinfo=UTC)
    assert [result.result_type_kind for result in parsed.results] == [
        "After90Minutes", "HalfTime"
    ]
    assert parsed.raw_response_sha256 == sha256(payload).hexdigest()
    assert parsed.retrieved_at == RETRIEVED


def test_provider_update_time_is_not_promoted_to_publication_or_availability():
    parsed = parse_openligadb_response(raw([match()]), retrieved_at=RETRIEVED).matches[0]
    assert parsed.provider_update_at == datetime(2026, 11, 12, 21, 0, tzinfo=timezone(timedelta(hours=1)))
    assert not hasattr(parsed, "source_published_at")
    assert not hasattr(parsed, "available_at")


@pytest.mark.parametrize("kickoff", [None, "", "2026-11-12T19:30:00", "not-a-date"])
def test_missing_or_naive_utc_kickoff_is_rejected(kickoff):
    report = parse_openligadb_response(raw([match(matchDateTimeUTC=kickoff)]), retrieved_at=RETRIEVED)
    assert report.accepted_count == 0
    assert report.rejected_rows[0].reason_code == "UTC_KICKOFF_MISSING_OR_UNTRUSTED"


def test_duplicate_provider_match_ids_reject_all_duplicate_rows():
    report = parse_openligadb_response(raw([match(), match()]), retrieved_at=RETRIEVED)
    assert report.accepted_count == 0
    assert [row.reason_code for row in report.rejected_rows] == [
        "DUPLICATE_PROVIDER_MATCH_ID", "DUPLICATE_PROVIDER_MATCH_ID"
    ]


def test_bad_result_row_rejects_match_instead_of_guessing_full_time_score():
    bad = {"resultTypeKind": "After90Minutes", "points": "2"}
    report = parse_openligadb_response(raw([match(matchResults=[bad])]), retrieved_at=RETRIEVED)
    assert report.accepted_count == 0
    assert report.rejected_rows[0].reason_code == "RESULT_ROWS_INVALID"


def test_result_order_is_preserved_and_no_result_type_is_selected_as_final():
    parsed = parse_openligadb_response(raw([match()]), retrieved_at=RETRIEVED).matches[0]
    assert [result.points for result in parsed.results] == [2, 1]
    assert len(parsed.results) == 2


def test_malformed_root_and_invalid_json_are_reported():
    malformed = parse_openligadb_response(b"{bad", retrieved_at=RETRIEVED)
    assert malformed.root_error == "JSON_DECODE_FAILED"
    root = parse_openligadb_response(b"{}", retrieved_at=RETRIEVED)
    assert root.root_error == "ROOT_MUST_BE_ARRAY"


def test_naive_retrieval_clock_is_rejected():
    with pytest.raises(ValueError, match="RETRIEVED_AT_MUST_BE_TIMEZONE_AWARE"):
        parse_openligadb_response(b"[]", retrieved_at=datetime(2026, 11, 14, 12, 0))
