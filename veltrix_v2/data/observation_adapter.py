"""Convert validated provider fixture contracts into model observations and targets.

Provider IDs are namespaced, not merged by display name. Historical rows with
an explicit retrieval timestamp may support future forecasts, but the
point_in_time_certifiable flag is carried through unchanged. Walk-forward
evaluation excludes rows whose source contract does not certify PIT eligibility.
"""
from __future__ import annotations

from hashlib import sha256
import json
from datetime import datetime

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


def historical_fixture_to_first_observed_observation(
    fixture: HistoricalFixture, *, recorded_at: datetime | None = None,
) -> MatchObservation | None:
    """Build a prospective-only observation using collector first-seen time.

    This does not assert provider publication time or PIT certification. The
    result becomes usable only at/after the exact retrieval time at which this
    collector first observed it. The conservative provider availability proxy
    is deliberately not reused as the observation time.
    """
    if not isinstance(fixture, HistoricalFixture):
        raise TypeError("HISTORICAL_FIXTURE_REQUIRED")
    if fixture.status is not FixtureStatus.FINISHED:
        return None
    if fixture.home_score is None or fixture.away_score is None:
        return None
    observed_at = fixture.retrieved_at_utc
    captured_at = recorded_at or observed_at
    if (observed_at.tzinfo is None or observed_at.utcoffset() is None
            or captured_at.tzinfo is None or captured_at.utcoffset() is None):
        raise ValueError("FIRST_OBSERVED_CLOCKS_MUST_BE_TIMEZONE_AWARE")
    if observed_at < fixture.kickoff_at_utc or captured_at < observed_at:
        raise ValueError("FIRST_OBSERVED_TEMPORAL_ORDER_INVALID")
    item = {
        "provider": fixture.provider,
        "source_id": fixture.source_id,
        "provider_fixture_id": fixture.provider_fixture_id,
        "provider_competition_id": fixture.provider_competition_id,
        "provider_home_team_id": fixture.provider_home_team_id,
        "provider_away_team_id": fixture.provider_away_team_id,
        "kickoff_at": fixture.kickoff_at_utc.isoformat(),
        "home_goals": fixture.home_score,
        "away_goals": fixture.away_score,
        "first_observed_at": observed_at.isoformat(),
        "recorded_at": captured_at.isoformat(),
        "payload_sha256": fixture.payload_sha256,
        "rights_approval_id": fixture.rights_approval_id,
    }
    canonical_item = json.dumps(
        item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    item_hash = sha256(canonical_item).hexdigest()
    manifest = {
        "schema": "veltrix-first-observed-result-v1",
        "provider": fixture.provider,
        "source_id": fixture.source_id,
        "first_observed_at": observed_at.isoformat(),
        "recorded_at": captured_at.isoformat(),
        "item_evidence_sha256": item_hash,
    }
    manifest_hash = sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return MatchObservation(
        fixture_id=f"{fixture.source_id}:{fixture.provider_fixture_id}",
        competition_id=f"{fixture.source_id}:{fixture.provider_competition_id}",
        home_team_id=f"{fixture.source_id}:{fixture.provider_home_team_id}",
        away_team_id=f"{fixture.source_id}:{fixture.provider_away_team_id}",
        kickoff_at=fixture.kickoff_at_utc,
        available_at=observed_at,
        recorded_at=captured_at,
        home_goals=fixture.home_score,
        away_goals=fixture.away_score,
        provider=fixture.provider,
        source_id=fixture.source_id,
        availability_basis="collector_first_observed_v1",
        point_in_time_certifiable=False,
        payload_sha256=fixture.payload_sha256,
        rights_approval_id=fixture.rights_approval_id,
        evidence_manifest_sha256=manifest_hash,
        capture_evidence_sha256=item_hash,
    )
