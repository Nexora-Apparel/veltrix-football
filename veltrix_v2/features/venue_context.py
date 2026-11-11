"""Point-in-time venue context from explicit fixture metadata only.

No venue is inferred from the nominal home team. Unknown neutral status remains
missing, and only observations available by the forecast cutoff are eligible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from veltrix_v2.features.snapshot import FeatureSnapshot, FeatureValue


@dataclass(frozen=True, slots=True)
class VenueContextObservation:
    provider: str
    provider_fixture_id: str
    venue_id: str | None
    is_neutral: bool | None
    available_at_utc: datetime
    source_observation_id: str

    def __post_init__(self) -> None:
        value = self.available_at_utc
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("available_at_utc must be timezone-aware")
        object.__setattr__(self, "available_at_utc", value.astimezone(timezone.utc))
        if not self.provider.strip() or not self.provider_fixture_id.strip():
            raise ValueError("provider and fixture identity are required")
        if not self.source_observation_id.strip():
            raise ValueError("source observation identity is required")
        if self.venue_id is not None and not self.venue_id.strip():
            raise ValueError("venue_id must be non-empty or None")
        if self.is_neutral is not None and not isinstance(self.is_neutral, bool):
            raise ValueError("is_neutral must be an explicit boolean or None")


def build_venue_context_snapshot(
    observations: Iterable[VenueContextObservation],
    *,
    provider: str,
    fixture_provider_id: str,
    cutoff_utc: datetime,
    feature_set_version: str = "venue-context-0.1",
) -> FeatureSnapshot:
    """Build explicit neutral-ground and venue-identity indicators."""
    if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
        raise ValueError("cutoff_utc must be timezone-aware")
    cutoff = cutoff_utc.astimezone(timezone.utc)
    if not provider.strip() or not fixture_provider_id.strip():
        raise ValueError("provider and fixture identity are required")

    eligible = [
        item for item in observations
        if item.provider == provider
        and item.provider_fixture_id == fixture_provider_id
        and item.available_at_utc <= cutoff
    ]
    if len(eligible) > 1:
        ids = [item.source_observation_id for item in eligible]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate source observation IDs are not allowed")
        raise ValueError("multiple eligible venue observations require upstream resolution")
    if not eligible:
        neutral_value = venue_value = None
        source_ids: tuple[str, ...] = ()
        neutral_state = venue_state = "missing"
        neutral_reason = venue_reason = "no matching venue observation available by cutoff"
    else:
        item = eligible[0]
        source_ids = (item.source_observation_id,)
        neutral_value = None if item.is_neutral is None else float(item.is_neutral)
        venue_value = float(item.venue_id is not None)
        neutral_state = "missing" if neutral_value is None else "valid"
        venue_state = "valid"
        neutral_reason = "provider did not supply explicit neutral-ground status" if neutral_value is None else None
        venue_reason = None

    features = (
        FeatureValue(
            name="is_neutral_venue",
            value=neutral_value,
            source_observation_ids=source_ids,
            computed_at_utc=cutoff,
            cutoff_utc=cutoff,
            sample_size=len(source_ids),
            quality_state=neutral_state,
            missing_reason=neutral_reason,
        ),
        FeatureValue(
            name="venue_identity_available",
            value=venue_value,
            source_observation_ids=source_ids,
            computed_at_utc=cutoff,
            cutoff_utc=cutoff,
            sample_size=len(source_ids),
            quality_state=venue_state,
            missing_reason=venue_reason,
        ),
    )
    return FeatureSnapshot(provider, fixture_provider_id, cutoff, feature_set_version, features)
