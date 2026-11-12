from datetime import datetime, timezone

import pytest

from veltrix_v2.ingestion.statsbomb_events import adapt_event
from veltrix_v2.ingestion.statsbomb_match_metadata import (
    adapt_match_metadata, availability_at_cutoff, build_coverage_manifest,
)


def metadata(**overrides):
    row = {
        "match_id": 2781,
        "competition_id": 2,
        "competition_name": "Premier League",
        "season_id": 27,
        "season_name": "2020/2021",
        "match_date": "2021-03-01",
        "kick_off": "20:00:00.000",
        "home_team": {"home_team_id": 1, "home_team_name": "Alpha"},
        "away_team": {"away_team_id": 2, "away_team_name": "Beta"},
        "home_score": 2,
        "away_score": 1,
        "match_available": "2021-03-02T01:00:00Z",
        "match_updated": "2021-03-03T02:00:00+01:00",
        "match_week": 25,
    }
    row.update(overrides)
    return row


def event():
    return adapt_event({
        "id": "0052d1b5-e2b0-4629-bbea-c18c884ab103",
        "index": 1, "period": 1, "timestamp": "00:00:01.000",
        "type": {"id": 1, "name": "Pass"},
    }, match_id="2781")


def test_metadata_preserves_kickoff_and_parses_only_offset_aware_availability():
    item = adapt_match_metadata(metadata())
    assert item.match_id == "2781"
    assert item.match_date_raw == "2021-03-01"
    assert item.kick_off_raw == "20:00:00.000"
    assert item.match_available_utc == datetime(2021, 3, 2, 1, tzinfo=timezone.utc)
    assert item.match_updated_utc == datetime(2021, 3, 3, 1, tzinfo=timezone.utc)


def test_naive_availability_is_preserved_but_not_treated_as_utc():
    item = adapt_match_metadata(metadata(match_available="2021-03-02T01:00:00"))
    assert item.match_available_raw == "2021-03-02T01:00:00"
    assert item.match_available_utc is None
    assert availability_at_cutoff(item, cutoff=datetime(2021, 3, 4, tzinfo=timezone.utc)) == "availability_time_unverified"


def test_cutoff_eligibility_uses_source_availability_not_match_clock():
    item = adapt_match_metadata(metadata())
    assert availability_at_cutoff(item, cutoff=datetime(2021, 3, 1, tzinfo=timezone.utc)) == "available_after_cutoff"
    assert availability_at_cutoff(item, cutoff=datetime(2021, 3, 4, tzinfo=timezone.utc)) == "available_by_cutoff"


def test_coverage_manifest_does_not_claim_completeness():
    item = adapt_match_metadata(metadata())
    manifest = build_coverage_manifest(item, [event()])
    assert manifest.observed_event_count == 1
    assert manifest.event_coverage_state == "events_present_completeness_unverified"
    assert manifest.event_payload_sha256


def test_missing_events_and_mismatched_ids_are_explicit():
    item = adapt_match_metadata(metadata())
    assert build_coverage_manifest(item, []).event_coverage_state == "events_missing"
    wrong = adapt_event({
        "id": "1052d1b5-e2b0-4629-bbea-c18c884ab103",
        "index": 1, "period": 1, "timestamp": "00:00:01.000",
        "type": {"id": 1, "name": "Pass"},
    }, match_id="other")
    with pytest.raises(ValueError, match="MATCH_ID_MISMATCH"):
        build_coverage_manifest(item, [wrong])


def test_invalid_cutoff_is_rejected():
    item = adapt_match_metadata(metadata())
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        availability_at_cutoff(item, cutoff=datetime(2021, 3, 4))
