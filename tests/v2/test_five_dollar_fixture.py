import json
from datetime import datetime, timezone

import pytest

from veltrix_v2.ingestion.ports import RawProviderRecord
from veltrix_v2.ingestion.providers.five_dollar_fixture import (
    FiveDollarFixtureStatus,
    parse_fixture_record,
)


def payload(status="finished", goals=None):
    return {
        "success": 1,
        "data": [{
            "id": 987, "league": {"id": 55, "name": "Example League"},
            "teams": {
                "home": {"id": 11, "name": "Home FC"},
                "away": {"id": 22, "name": "Away FC"},
            },
            "kickoff_utc": "2026-11-06T15:00:00+00:00",
            "kickoff_ts": 1793977200,
            "status": status, "status_reason": None, "status_code": "full",
            "goals": goals if goals is not None else {"home": 2, "away": 1},
        }],
    }


def raw(body=None, **changes):
    values = dict(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_record_id="987", provider_fixture_id="987",
        provider_competition_id="55", data_class="fixtures",
        raw_payload=json.dumps(body if body is not None else payload()).encode(),
        provider_home_team_id="11", provider_away_team_id="22",
    )
    values.update(changes)
    return RawProviderRecord(**values)


def test_finished_fixture_with_complete_score_is_settled():
    record = parse_fixture_record(raw())
    assert record.status is FiveDollarFixtureStatus.FINISHED
    assert record.is_settled_result
    assert (record.completed_home_goals, record.completed_away_goals) == (2, 1)
    assert record.source_identity.provider_fixture_id == "987"


def test_scheduled_fixture_does_not_expose_completed_score():
    record = parse_fixture_record(raw(payload("scheduled", {"home": 0, "away": 0})))
    assert record.status is FiveDollarFixtureStatus.SCHEDULED
    assert record.completed_home_goals is None
    assert record.is_settled_result is False


def test_in_play_score_is_not_misclassified_as_final_result():
    record = parse_fixture_record(raw(payload("in_play", {"home": 2, "away": 1})))
    assert record.status is FiveDollarFixtureStatus.IN_PLAY
    assert record.completed_home_goals is None


def test_finished_without_complete_score_becomes_unknown():
    record = parse_fixture_record(raw(payload("finished", {"home": 2, "away": None})))
    assert record.status is FiveDollarFixtureStatus.UNKNOWN
    assert record.status_reason == "result_unconfirmed"
    assert record.is_settled_result is False


def test_unknown_or_unrecognized_status_is_not_guessed():
    record = parse_fixture_record(raw(payload("postponed")))
    assert record.status is FiveDollarFixtureStatus.UNKNOWN
    assert record.raw_status == "postponed"


def test_provider_fixture_id_mismatch_is_rejected():
    with pytest.raises(ValueError, match="NOT_FOUND"):
        parse_fixture_record(raw(provider_fixture_id="other"))


def test_provider_team_or_competition_id_mismatch_is_rejected():
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        parse_fixture_record(raw(provider_home_team_id="999"))


def test_epoch_and_iso_kickoff_must_agree():
    body = payload()
    body["data"][0]["kickoff_ts"] = 1
    with pytest.raises(ValueError, match="TIMESTAMP_CONFLICT"):
        parse_fixture_record(raw(body))


def test_raw_source_ids_are_preserved_and_squad_is_not_guessed():
    record = parse_fixture_record(raw())
    assert record.source_identity.provider_home_team_id == "11"
    assert record.source_identity.provider_away_team_id == "22"
    assert record.source_identity.squad_category is None
