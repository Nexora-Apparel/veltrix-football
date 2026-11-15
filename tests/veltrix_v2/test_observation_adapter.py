from datetime import datetime, timedelta, timezone

import pytest
import hashlib
import json

from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture
from veltrix_v2.data.observation_adapter import (
    historical_fixture_to_observation,
    historical_fixture_to_target,
)

UTC = timezone.utc
KICKOFF = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)
RETRIEVED = datetime(2026, 11, 14, 0, 30, tzinfo=UTC)


def historical_fixture(*, status=FixtureStatus.FINISHED, certifiable=False, retrieved=RETRIEVED, kickoff=KICKOFF):
    payload = {
        "id": 98765,
        "league": {"id": 4160026622, "name": "England Premier League"},
        "teams": {
            "home": {"id": 101, "name": "Arsenal"},
            "away": {"id": 102, "name": "Chelsea"},
        },
        "kickoff_utc": kickoff.isoformat(),
        "status": status.value,
        "goals": {"home": 2, "away": 1} if status is FixtureStatus.FINISHED else None,
    }
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    finished = status is FixtureStatus.FINISHED
    return HistoricalFixture(
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        provider_fixture_id="98765",
        provider_competition_id="4160026622",
        provider_home_team_id="101",
        provider_away_team_id="102",
        competition_name="England Premier League",
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        kickoff_at_utc=kickoff,
        season_key="2026-2027",
        status=status,
        home_score=2 if finished else None,
        away_score=1 if finished else None,
        payload=payload,
        payload_sha256=payload_hash,
        retrieved_at_utc=retrieved,
        source_event_time_utc=kickoff,
        available_at_utc=kickoff + timedelta(days=4) if finished else None,
        availability_basis="provider_finished_status_conservative_4d" if finished else "not_settled",
        point_in_time_certifiable=certifiable,
        rights_approval_id="5dollar-epl-approved",
    )


def test_finished_provider_fixture_converts_with_source_ids_and_provenance():
    result = historical_fixture_to_observation(historical_fixture())
    assert result is not None
    assert result.fixture_id == "5dollarfootballapi:98765"
    assert result.competition_id == "5dollarfootballapi:4160026622"
    assert result.home_team_id == "5dollarfootballapi:101"
    assert result.away_team_id == "5dollarfootballapi:102"
    assert result.kickoff_at == KICKOFF
    assert result.available_at == KICKOFF + timedelta(days=4)
    assert result.recorded_at == RETRIEVED
    assert result.home_goals == 2 and result.away_goals == 1
    assert result.provider == "5DollarFootballAPI"
    assert result.availability_basis == "provider_finished_status_conservative_4d"
    assert not result.point_in_time_certifiable
    assert result.payload_sha256 is not None
    assert result.rights_approval_id == "5dollar-epl-approved"


def test_certification_flag_is_carried_through_without_upgrading_source_evidence():
    result = historical_fixture_to_observation(historical_fixture(certifiable=True))
    assert result is not None
    assert result.point_in_time_certifiable


def test_unsettled_provider_fixtures_do_not_become_model_result_observations():
    result = historical_fixture_to_observation(historical_fixture(status=FixtureStatus.SCHEDULED))
    assert result is None


def test_result_is_not_emitted_before_conservative_availability_time():
    early_retrieval = KICKOFF + timedelta(days=1)
    result = historical_fixture_to_observation(
        historical_fixture(retrieved=early_retrieval)
    )
    assert result is None


def test_future_scheduled_provider_fixture_converts_to_prediction_target():
    future_kickoff = RETRIEVED + timedelta(days=2)
    result = historical_fixture_to_target(
        historical_fixture(status=FixtureStatus.SCHEDULED, kickoff=future_kickoff)
    )
    assert result is not None
    assert result.fixture_id == "5dollarfootballapi:98765"
    assert result.competition_id == "5dollarfootballapi:4160026622"
    assert result.home_team_id == "5dollarfootballapi:101"
    assert result.away_team_id == "5dollarfootballapi:102"
    assert result.home_team_name == "Arsenal"
    assert result.away_team_name == "Chelsea"
    assert result.kickoff_at == future_kickoff
    assert result.retrieved_at == RETRIEVED


def test_scheduled_fixture_already_kicked_off_is_not_a_prediction_target():
    assert historical_fixture_to_target(
        historical_fixture(status=FixtureStatus.SCHEDULED)
    ) is None



def openplay_source_observation():
    saved_at = datetime(2026, 10, 29, 20, 44, 32, tzinfo=UTC)
    recorded_at = datetime(2026, 11, 15, 12, 50, 0, tzinfo=UTC)
    return {
        "provider": "OpenPlay / WhoScored / Opta",
        "source_id": "openplay-data-v0.1.0",
        "entity_type": "match_result_snapshot",
        "provider_entity_id": "123456",
        "payload_sha256": "a" * 64,
        "retrieved_at": recorded_at,
        "recorded_at": recorded_at,
        "available_at": saved_at,
        "source_published_at": saved_at,
        "source_timestamp_basis": "documented_guarantee",
        "availability_basis": "openplay_page_saved_at_utc_v1",
        "point_in_time_certifiable": True,
        "rights_approval_id": "approval-openplay-whoscored-opta-noncommercial-2026-11-15",
        "provider_response_id": 55,
        "payload": {
            "match_id": "123456",
            "competition_code": "eng",
            "season": "2425",
            "match_date": "2025-05-10",
            "home_team_id": "1001",
            "away_team_id": "1002",
            "home_score_90": 2,
            "away_score_90": 1,
            "xg_model": "openplay-xg-v1",
            "scraped_at_utc": saved_at.isoformat(),
            "timestamp_guarantee_evidence_id": "openplay-data-v0.1.0:DATA_DICTIONARY.md#matches.scraped_at",
            "timestamp_guarantee_evidence_sha256": "24a1037a948afa1759e3bc2babeb8b17b9e1e2dc3c8a8beea2e18f9b5b671279",
            "source_timestamp_semantics": "page_saved_at_utc",
            "rights_approval_id": "approval-openplay-whoscored-opta-noncommercial-2026-11-15",
            "capture_manifest_sha256": "b" * 64,
            "matches_parquet_sha256": "c" * 64,
            "temporal_use_scope": "only for cutoffs at or after actual VELTRIX recorded_at",
            "commercial_use_allowed": False,
        },
    }


def test_openplay_match_snapshot_converts_with_documented_capture_time():
    from veltrix_v2.data.observation_adapter import openplay_match_snapshot_to_observation

    row = openplay_source_observation()
    result = openplay_match_snapshot_to_observation(row)
    assert result is not None
    assert result.fixture_id == "openplay-data-v0.1.0:123456"
    assert result.competition_id == "openplay-data-v0.1.0:eng"
    assert result.kickoff_at is None
    assert result.kickoff_date.isoformat() == "2025-05-10"
    assert result.available_at == row["available_at"]
    assert result.recorded_at == row["recorded_at"]
    assert result.point_in_time_certifiable is True
    assert result.rights_approval_id == row["rights_approval_id"]
    assert result.evidence_manifest_sha256 == "b" * 64
    assert result.capture_evidence_sha256 == "c" * 64


def test_openplay_snapshot_is_eligible_only_after_actual_veltrix_recording_time():
    from veltrix_v2.data.observation_adapter import openplay_match_snapshot_to_observation
    from veltrix_v2.models.poisson import observation_eligible_as_of

    result = openplay_match_snapshot_to_observation(openplay_source_observation())
    assert result is not None
    assert observation_eligible_as_of(
        result, cutoff_at=datetime(2026, 11, 16, 6, 0, tzinfo=UTC)
    )
    assert not observation_eligible_as_of(
        result, cutoff_at=datetime(2026, 11, 14, 23, 59, tzinfo=UTC)
    )


@pytest.mark.parametrize("mutation", [
    lambda row: row["payload"].update(timestamp_guarantee_evidence_sha256="0" * 64),
    lambda row: row.update(point_in_time_certifiable=False),
    lambda row: row.update(source_timestamp_basis="unknown"),
    lambda row: row.update(rights_approval_id="wrong-approval"),
    lambda row: row.update(recorded_at=datetime(2026, 10, 1, tzinfo=UTC)),
    lambda row: row.update(available_at=datetime(2026, 10, 30, tzinfo=UTC)),
])
def test_openplay_snapshot_fails_closed_when_temporal_or_rights_evidence_is_invalid(mutation):
    from veltrix_v2.data.observation_adapter import openplay_match_snapshot_to_observation

    row = openplay_source_observation()
    mutation(row)
    assert openplay_match_snapshot_to_observation(row) is None
