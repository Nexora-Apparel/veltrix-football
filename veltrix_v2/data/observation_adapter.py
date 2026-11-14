"""Convert validated provider fixture contracts into model observations and targets.

Provider IDs are namespaced, not merged by display name. Historical rows with
an explicit retrieval timestamp may support future forecasts, but the
point_in_time_certifiable flag is carried through unchanged. Walk-forward
evaluation excludes rows whose source contract does not certify PIT eligibility.
"""
from __future__ import annotations

from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture
from veltrix_v2.models.poisson import MatchObservation
from veltrix_v2.models.engine import PredictionTarget


def historical_fixture_to_observation(
    fixture: HistoricalFixture,
) -> MatchObservation | None:
    """Convert a settled, timestamped fixture; return None for unsettled rows."""
    if not isinstance(fixture, HistoricalFixture):
        raise TypeError("HISTORICAL_FIXTURE_REQUIRED")
    if fixture.status is not FixtureStatus.FINISHED:
        return None
    if fixture.home_score is None or fixture.away_score is None:
        return None
    if fixture.available_at_utc is None or fixture.available_at_utc > fixture.retrieved_at_utc:
        return None
    return MatchObservation(
        fixture_id=f"{fixture.source_id}:{fixture.provider_fixture_id}",
        competition_id=f"{fixture.source_id}:{fixture.provider_competition_id}",
        home_team_id=f"{fixture.source_id}:{fixture.provider_home_team_id}",
        away_team_id=f"{fixture.source_id}:{fixture.provider_away_team_id}",
        kickoff_at=fixture.kickoff_at_utc,
        available_at=fixture.available_at_utc,
        recorded_at=fixture.retrieved_at_utc,
        home_goals=fixture.home_score,
        away_goals=fixture.away_score,
        provider=fixture.provider,
        source_id=fixture.source_id,
        availability_basis=fixture.availability_basis,
        point_in_time_certifiable=fixture.point_in_time_certifiable,
        payload_sha256=fixture.payload_sha256,
        rights_approval_id=fixture.rights_approval_id,
    )


def historical_fixture_to_target(fixture: HistoricalFixture) -> PredictionTarget | None:
    """Convert a known future scheduled provider fixture into a prediction target."""
    if not isinstance(fixture, HistoricalFixture):
        raise TypeError("HISTORICAL_FIXTURE_REQUIRED")
    if fixture.status is not FixtureStatus.SCHEDULED:
        return None
    if fixture.kickoff_at_utc <= fixture.retrieved_at_utc:
        return None
    return PredictionTarget(
        fixture_id=f"{fixture.source_id}:{fixture.provider_fixture_id}",
        competition_id=f"{fixture.source_id}:{fixture.provider_competition_id}",
        home_team_id=f"{fixture.source_id}:{fixture.provider_home_team_id}",
        away_team_id=f"{fixture.source_id}:{fixture.provider_away_team_id}",
        kickoff_at=fixture.kickoff_at_utc,
        provider=fixture.provider,
        source_id=fixture.source_id,
        source_fixture_id=fixture.provider_fixture_id,
        retrieved_at=fixture.retrieved_at_utc,
        payload_sha256=fixture.payload_sha256,
        rights_approval_id=fixture.rights_approval_id,
        home_team_name=fixture.home_team_name,
        away_team_name=fixture.away_team_name,
    )
