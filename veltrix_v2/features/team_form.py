"""Point-in-time team form features built only from settled, available results.

Pure deterministic feature engineering. No model fitting, priors, prediction
fallbacks, provider calls, persistence or legacy imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp, isfinite, log
from typing import Iterable

from veltrix_v2.features.snapshot import FeatureSnapshot, FeatureValue


@dataclass(frozen=True, slots=True)
class SettledMatch:
    provider: str
    provider_fixture_id: str
    competition_key: str
    season: str
    kickoff_utc: datetime
    available_at_utc: datetime
    status: str
    home_provider_team_id: str
    away_provider_team_id: str
    home_goals: int
    away_goals: int
    source_observation_id: str

    def __post_init__(self) -> None:
        for field in ("kickoff_utc", "available_at_utc"):
            value = getattr(self, field)
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware")
            object.__setattr__(self, field, value.astimezone(timezone.utc))
        required = (
            self.provider, self.provider_fixture_id, self.competition_key,
            self.season, self.home_provider_team_id, self.away_provider_team_id,
            self.source_observation_id,
        )
        if any(not value.strip() for value in required):
            raise ValueError("settled-match identity and provenance fields are required")
        if self.home_provider_team_id == self.away_provider_team_id:
            raise ValueError("home and away team identities must differ")
        if self.status != "FINISHED":
            raise ValueError("only FINISHED matches can enter settled form features")
        for value in (self.home_goals, self.away_goals):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("settled goals must be non-negative integers")
        if self.available_at_utc < self.kickoff_utc:
            raise ValueError("a settled result cannot be available before kickoff")


def build_team_form_snapshot(
    matches: Iterable[SettledMatch],
    *,
    provider: str,
    fixture_provider_id: str,
    team_provider_id: str,
    competition_key: str,
    season: str,
    cutoff_utc: datetime,
    feature_set_version: str = "team-form-0.1",
    window_matches: int = 5,
    minimum_sample: int = 3,
    half_life_matches: float = 3.0,
) -> FeatureSnapshot:
    """Build leakage-safe rolling form for one team and one competition-season."""
    if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
        raise ValueError("cutoff_utc must be timezone-aware")
    cutoff = cutoff_utc.astimezone(timezone.utc)
    if not all((provider, fixture_provider_id, team_provider_id, competition_key, season)):
        raise ValueError("fixture, team and competition scope are required")
    if (isinstance(window_matches, bool) or not isinstance(window_matches, int)
            or isinstance(minimum_sample, bool) or not isinstance(minimum_sample, int)
            or window_matches < 1 or minimum_sample < 1
            or not isfinite(float(half_life_matches)) or half_life_matches <= 0):
        raise ValueError("window, minimum sample and finite positive half-life are required")

    eligible = [
        match for match in matches
        if match.provider == provider
        and match.competition_key == competition_key
        and match.season == season
        and team_provider_id in (match.home_provider_team_id, match.away_provider_team_id)
        and match.kickoff_utc < cutoff
        and match.available_at_utc <= cutoff
        and match.status == "FINISHED"
    ]
    fixture_ids = [match.provider_fixture_id for match in eligible]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("duplicate provider fixture IDs in team-form input")
    observation_ids = [match.source_observation_id for match in eligible]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("duplicate source observation IDs in team-form input")

    eligible.sort(key=lambda item: (item.kickoff_utc, item.provider_fixture_id))
    selected = eligible[-window_matches:]
    count = len(selected)
    if count == 0:
        names = ("goals_for_per_match", "goals_against_per_match", "points_per_match")
        features = tuple(
            FeatureValue(
                name=name, value=None, source_observation_ids=(),
                computed_at_utc=cutoff, cutoff_utc=cutoff,
                sample_size=0, quality_state="missing",
                missing_reason="no settled, point-in-time-available matches in competition-season scope",
            )
            for name in names
        )
        return FeatureSnapshot(provider, fixture_provider_id, cutoff, feature_set_version, features)

    weighted = []
    for age, match in enumerate(reversed(selected)):
        weight = exp(-log(2.0) * age / half_life_matches)
        is_home = match.home_provider_team_id == team_provider_id
        goals_for = match.home_goals if is_home else match.away_goals
        goals_against = match.away_goals if is_home else match.home_goals
        points = 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0
        weighted.append((weight, goals_for, goals_against, points, match.source_observation_id))
    total_weight = sum(row[0] for row in weighted)
    means = {
        "goals_for_per_match": sum(w * gf for w, gf, _, _, _ in weighted) / total_weight,
        "goals_against_per_match": sum(w * ga for w, _, ga, _, _ in weighted) / total_weight,
        "points_per_match": sum(w * pts for w, _, _, pts, _ in weighted) / total_weight,
    }
    quality = "valid" if count >= minimum_sample else "low_sample"
    source_ids = tuple(row[4] for row in weighted)
    features = tuple(
        FeatureValue(
            name=name, value=value,
            source_observation_ids=source_ids,
            computed_at_utc=cutoff, cutoff_utc=cutoff,
            sample_size=count, quality_state=quality,
        )
        for name, value in means.items()
    )
    return FeatureSnapshot(provider, fixture_provider_id, cutoff, feature_set_version, features)
