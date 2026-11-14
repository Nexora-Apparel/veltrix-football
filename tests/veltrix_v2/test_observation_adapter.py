from datetime import datetime, timedelta, timezone
import hashlib
import json

from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture
from veltrix_v2.data.observation_adapter import (
    historical_fixture_to_first_observed_observation,
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


def test_first_observed_adapter_uses_retrieval_time_not_provider_proxy():
    fixture = historical_fixture()
    result = historical_fixture_to_first_observed_observation(fixture)
    assert result is not None
    assert result.available_at == RETRIEVED
    assert result.recorded_at == RETRIEVED
    assert result.available_at != fixture.available_at_utc
    assert result.availability_basis == "collector_first_observed_v1"
    assert result.point_in_time_certifiable is False
    assert len(result.evidence_manifest_sha256) == 64
    assert len(result.capture_evidence_sha256) == 64


def test_first_observed_adapter_never_backdates_before_retrieval():
    fixture = historical_fixture()
    result = historical_fixture_to_first_observed_observation(
        fixture, recorded_at=RETRIEVED - timedelta(seconds=1)
    )
    assert result is None or result.recorded_at >= result.available_at


def test_first_observed_adapter_requires_finished_source_result():
    assert historical_fixture_to_first_observed_observation(
        historical_fixture(status=FixtureStatus.SCHEDULED)
    ) is None
