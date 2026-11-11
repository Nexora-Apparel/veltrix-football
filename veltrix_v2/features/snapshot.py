"""Point-in-time feature lineage contracts; no model fitting in this module."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class FeatureValue:
    name: str
    value: float | None
    source_observation_ids: tuple[str, ...]
    computed_at_utc: datetime
    cutoff_utc: datetime
    sample_size: int
    quality_state: str
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("feature name is required")
        if not isinstance(self.source_observation_ids, (tuple, list)):
            raise ValueError("source observation IDs must be a sequence")
        object.__setattr__(self, "source_observation_ids", tuple(self.source_observation_ids))
        if not self.name.strip():
            raise ValueError("feature name is required")
        computed = _utc(self.computed_at_utc, "computed_at_utc")
        cutoff = _utc(self.cutoff_utc, "cutoff_utc")
        object.__setattr__(self, "computed_at_utc", computed)
        object.__setattr__(self, "cutoff_utc", cutoff)
        if computed > cutoff:
            raise ValueError("feature cannot be computed after its cutoff")
        if isinstance(self.sample_size, bool) or not isinstance(self.sample_size, int) or self.sample_size < 0:
            raise ValueError("sample_size must be a non-negative integer")
        if self.value is not None and (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not isfinite(float(self.value))
        ):
            raise ValueError("feature value must be a finite numeric value")
        if self.value is not None and (self.sample_size < 1 or not self.source_observation_ids):
            raise ValueError("observed feature requires positive sample size and source provenance")
        if self.value is None and (not isinstance(self.missing_reason, str) or not self.missing_reason.strip()):
            raise ValueError("missing feature requires a reason code")
        if self.value is not None and self.missing_reason is not None:
            raise ValueError("observed feature cannot carry a missing reason")
        if self.quality_state not in {"valid", "low_sample", "missing", "quarantined"}:
            raise ValueError("unknown feature quality state")
        if self.value is None and self.quality_state != "missing":
            raise ValueError("missing feature must have quality_state=missing")
        if len(set(self.source_observation_ids)) != len(self.source_observation_ids):
            raise ValueError("duplicate source observation IDs are not allowed")
        if any(not isinstance(item, str) or not item.strip() for item in self.source_observation_ids):
            raise ValueError("source observation IDs must be non-empty strings")


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    fixture_provider: str
    fixture_provider_id: str
    cutoff_utc: datetime
    feature_set_version: str
    features: tuple[FeatureValue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", tuple(self.features))
        cutoff = _utc(self.cutoff_utc, "cutoff_utc")
        object.__setattr__(self, "cutoff_utc", cutoff)
        if not self.fixture_provider or not self.fixture_provider_id or not self.feature_set_version:
            raise ValueError("fixture and feature-set identifiers are required")
        if any(not isinstance(feature, FeatureValue) for feature in self.features):
            raise ValueError("snapshot features must be FeatureValue instances")
        names = [feature.name for feature in self.features]
        if len(set(names)) != len(names):
            raise ValueError("feature names must be unique within a snapshot")
        for feature in self.features:
            if feature.cutoff_utc != cutoff:
                raise ValueError("all features must share the snapshot cutoff")
            if feature.computed_at_utc > cutoff:
                raise ValueError("feature computation cannot occur after the forecast cutoff")
