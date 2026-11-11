"""Tests for explicit, point-in-time venue context."""
from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.features.venue_context import (
    VenueContextObservation,
    build_venue_context_snapshot,
)

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 11, 6, tzinfo=UTC)


def observation(*, available_at=CUTOFF - timedelta(hours=1), neutral=False, venue="stadium-1", fixture="fx-1", source="obs-1"):
    return VenueContextObservation(
        provider="strikerapi",
        provider_fixture_id=fixture,
        venue_id=venue,
        is_neutral=neutral,
        available_at_utc=available_at,
        source_observation_id=source,
    )


def build(rows, **overrides):
    args = dict(
        provider="strikerapi",
        fixture_provider_id="fx-1",
        cutoff_utc=CUTOFF,
    )
    args.update(overrides)
    return {item.name: item for item in build_venue_context_snapshot(rows, **args).features}


def test_explicit_neutral_status_and_venue_identity_are_encoded():
    result = build([observation(neutral=True)])
    assert result["is_neutral_venue"].value == 1.0
    assert result["venue_identity_available"].value == 1.0
    assert result["is_neutral_venue"].source_observation_ids == ("obs-1",)


def test_home_designation_does_not_imply_non_neutral_when_status_missing():
    row = observation()
    row = VenueContextObservation(
        provider=row.provider,
        provider_fixture_id=row.provider_fixture_id,
        venue_id=row.venue_id,
        is_neutral=None,
        available_at_utc=row.available_at_utc,
        source_observation_id=row.source_observation_id,
    )
    result = build([row])
    assert result["is_neutral_venue"].value is None
    assert result["is_neutral_venue"].quality_state == "missing"
    assert result["venue_identity_available"].value == 1.0


def test_future_observation_is_excluded():
    result = build([observation(available_at=CUTOFF + timedelta(seconds=1))])
    assert result["is_neutral_venue"].value is None
    assert result["venue_identity_available"].value is None


def test_other_fixture_or_provider_is_excluded():
    row = observation(fixture="different-fixture")
    result = build([row])
    assert result["is_neutral_venue"].value is None


def test_missing_venue_id_is_not_invented():
    result = build([observation(venue=None)])
    assert result["venue_identity_available"].value == 0.0


def test_multiple_eligible_observations_fail_closed():
    with pytest.raises(ValueError, match="multiple eligible"):
        build([observation(), observation(source="obs-2", neutral=True)])


def test_naive_observation_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        observation(available_at=datetime(2026, 11, 11, 5))
