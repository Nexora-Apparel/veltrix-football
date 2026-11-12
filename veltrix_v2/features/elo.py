"""Competition-scoped, point-in-time Elo ratings from settled match results.

Elo is exposed as a descriptive strength feature, not as a calibrated match
probability. Teams with no eligible history remain missing; no rating is
fabricated for a cold-start team.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Iterable

from veltrix_v2.features.snapshot import FeatureSnapshot, FeatureValue
from veltrix_v2.features.team_form import SettledMatch


def build_elo_snapshot(
    matches: Iterable[SettledMatch],
    *,
    provider: str,
    fixture_provider_id: str,
    competition_key: str,
    home_team_provider_id: str,
    away_team_provider_id: str,
    cutoff_utc: datetime,
    feature_set_version: str = "competition-elo-0.1",
    initial_rating: float = 1500.0,
    k_factor: float = 20.0,
    home_advantage: float = 60.0,
    minimum_matches: int = 5,
) -> FeatureSnapshot:
    """Build ratings using only competition results available by cutoff.

    Ratings carry across seasons within one competition, but never across
    competitions. Historical matches are replayed in kickoff order. For each
    match, both expected scores are computed from pre-match ratings and the
    two rating changes are applied simultaneously.
    """
    if cutoff_utc.tzinfo is None or cutoff_utc.utcoffset() is None:
        raise ValueError("cutoff_utc must be timezone-aware")
    cutoff = cutoff_utc.astimezone(timezone.utc)
    required = (provider, fixture_provider_id, competition_key,
                home_team_provider_id, away_team_provider_id)
    if any(not value or not value.strip() for value in required):
        raise ValueError("provider, fixture, competition and team IDs are required")
    if home_team_provider_id == away_team_provider_id:
        raise ValueError("home and away team identities must differ")
    if not all(isfinite(float(value)) for value in (initial_rating, k_factor, home_advantage)):
        raise ValueError("Elo parameters must be finite")
    if k_factor <= 0 or minimum_matches < 1:
        raise ValueError("K-factor and minimum_matches must be positive")

    eligible = [
        match for match in matches
        if match.provider == provider
        and match.competition_key == competition_key
        and match.kickoff_utc < cutoff
        and match.available_at_utc <= cutoff
        and match.status == "FINISHED"
    ]
    fixture_ids = [match.provider_fixture_id for match in eligible]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("duplicate provider fixture IDs in Elo input")
    observation_ids = [match.source_observation_id for match in eligible]
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("duplicate source observation IDs in Elo input")
    eligible.sort(key=lambda item: (item.kickoff_utc, item.provider_fixture_id))

    ratings: dict[str, float] = {}
    appearances: dict[str, int] = {}
    for match in eligible:
        home = match.home_provider_team_id
        away = match.away_provider_team_id
        home_rating = ratings.get(home, initial_rating)
        away_rating = ratings.get(away, initial_rating)
        expected_home = 1.0 / (1.0 + 10.0 ** ((away_rating - (home_rating + home_advantage)) / 400.0))
        expected_away = 1.0 - expected_home
        actual_home = 1.0 if match.home_goals > match.away_goals else 0.5 if match.home_goals == match.away_goals else 0.0
        change = k_factor * (actual_home - expected_home)
        ratings[home] = home_rating + change
        ratings[away] = away_rating - change
        appearances[home] = appearances.get(home, 0) + 1
        appearances[away] = appearances.get(away, 0) + 1

    home_count = appearances.get(home_team_provider_id, 0)
    away_count = appearances.get(away_team_provider_id, 0)
    home_rating = ratings.get(home_team_provider_id)
    away_rating = ratings.get(away_team_provider_id)
    both_known = home_rating is not None and away_rating is not None
    source_ids = tuple(match.source_observation_id for match in eligible)

    def value(name: str, number: float | None, sample: int, reason: str) -> FeatureValue:
        if number is None:
            return FeatureValue(
                name=name, value=None, source_observation_ids=source_ids,
                computed_at_utc=cutoff, cutoff_utc=cutoff, sample_size=sample,
                quality_state="missing", missing_reason=reason,
            )
        return FeatureValue(
            name=name, value=number, source_observation_ids=source_ids,
            computed_at_utc=cutoff, cutoff_utc=cutoff, sample_size=sample,
            quality_state="valid" if sample >= minimum_matches else "low_sample",
        )

    features = (
        value("elo_home_rating", home_rating, home_count,
              "home team has no eligible settled history in this competition"),
        value("elo_away_rating", away_rating, away_count,
              "away team has no eligible settled history in this competition"),
        value("elo_rating_difference", home_rating - away_rating if both_known else None,
              min(home_count, away_count),
              "both teams require eligible settled history for a rating difference"),
        value("elo_home_expected_score",
              1.0 / (1.0 + 10.0 ** ((away_rating - (home_rating + home_advantage)) / 400.0))
              if both_known else None,
              min(home_count, away_count),
              "both teams require eligible settled history for an Elo expected score"),
    )
    return FeatureSnapshot(provider, fixture_provider_id, cutoff, feature_set_version, features)
