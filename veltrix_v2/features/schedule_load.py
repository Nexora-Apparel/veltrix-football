"""Leakage-safe team schedule-load features for pre-match forecasting.

Counts prior settled fixtures across competitions for workload context. The
module is deterministic and has no provider, persistence, model or legacy
prediction dependencies.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from veltrix_v2.features.snapshot import FeatureSnapshot, FeatureValue
from veltrix_v2.features.team_form import SettledMatch


def build_team_schedule_load_snapshot(
    matches: Iterable[SettledMatch],
    *,
    provider: str,
    fixture_provider_id: str,
    team_provider_id: str,
    cutoff_utc: datetime,
    feature_set_version: str = "team-schedule-load-0.1",
) -> FeatureSnapshot:
    """Compute rest days and recent match counts using only available prior results.

    Workload is intentionally cross-competition and season-agnostic: a team's
    domestic and continental fixtures both contribute to recent schedule load.
    """
    if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
        raise ValueError("cutoff_utc must be timezone-aware")
    cutoff = cutoff_utc.astimezone(timezone.utc)
    if not all((provider, fixture_provider_id, team_provider_id)):
        raise ValueError("provider, fixture and team identities are required")

    eligible = [
        match for match in matches
        if match.provider == provider
        and team_provider_id in (match.home_provider_team_id, match.away_provider_team_id)
        and match.kickoff_utc < cutoff
        and match.available_at_utc <= cutoff
        and match.status == "FINISHED"
    ]
    eligible.sort(key=lambda item: (item.kickoff_utc, item.provider_fixture_id))

    fixture_ids = [match.provider_fixture_id for match in eligible]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("duplicate provider fixture IDs in schedule-load input")
    observation_ids = [match.source_observation_id for match in eligible]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("duplicate source observation IDs in schedule-load input")

    if not eligible:
        features = tuple(
            FeatureValue(
                name=name,
                value=None,
                source_observation_ids=(),
                computed_at_utc=cutoff,
                cutoff_utc=cutoff,
                sample_size=0,
                quality_state="missing",
                missing_reason="no settled, point-in-time-available prior fixtures",
            )
            for name in (
                "days_since_last_match",
                "matches_last_7_days",
                "matches_last_14_days",
                "matches_last_30_days",
            )
        )
        return FeatureSnapshot(provider, fixture_provider_id, cutoff, feature_set_version, features)

    latest = eligible[-1]
    days_since_last = (cutoff - latest.kickoff_utc).total_seconds() / 86400.0
    counts = {
        days: sum(
            1 for match in eligible
            if match.kickoff_utc >= cutoff - timedelta(days=days)
        )
        for days in (7, 14, 30)
    }
    source_ids = tuple(match.source_observation_id for match in eligible)
    values = (
        ("days_since_last_match", days_since_last),
        ("matches_last_7_days", float(counts[7])),
        ("matches_last_14_days", float(counts[14])),
        ("matches_last_30_days", float(counts[30])),
    )
    features = tuple(
        FeatureValue(
            name=name,
            value=value,
            source_observation_ids=source_ids,
            computed_at_utc=cutoff,
            cutoff_utc=cutoff,
            sample_size=len(eligible),
            quality_state="valid",
        )
        for name, value in values
    )
    return FeatureSnapshot(provider, fixture_provider_id, cutoff, feature_set_version, features)
