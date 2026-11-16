"""Feature-aware OpenPlay xG Poisson challenger for prospective V2 research.

No legacy prediction code, priors, calibration or fallback probabilities are used.
The model requires eligible recent xG-for and xG-against features for both teams.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

MODEL_VERSION = "veltrix-openplay-xg-poisson-v1"
FORMULA_VERSION = "symmetric_recent_xg_attack_defence_v1"
MAX_GOALS = 12


@dataclass(frozen=True)
class OpenPlayXGPrediction:
    model_version: str
    formula_version: str
    expected_home_goals: float
    expected_away_goals: float
    home_win: float
    draw: float
    away_win: float
    btts_yes: float
    over_2_5: float
    home_sample_count: int
    away_sample_count: int


def _finite_nonnegative(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"OPENPLAY_XG_{field}_INVALID")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"OPENPLAY_XG_{field}_MISSING_OR_INVALID") from None
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"OPENPLAY_XG_{field}_OUT_OF_RANGE")
    return result


def _team_xg(rows: Sequence[Mapping[str, Any]], metric: str) -> float:
    if not rows:
        raise ValueError("OPENPLAY_XG_TEAM_HISTORY_MISSING")
    values = []
    for row in rows:
        metrics = row.get("metrics")
        team = metrics.get("team") if isinstance(metrics, Mapping) else None
        if not isinstance(team, Mapping):
            raise ValueError("OPENPLAY_XG_TEAM_METRICS_MISSING")
        values.append(_finite_nonnegative(team.get(metric), metric.upper()))
    return sum(values) / len(values)


def _poisson_distribution(mean: float) -> tuple[float, ...]:
    if not math.isfinite(mean) or mean <= 0 or mean > 6:
        raise ValueError("OPENPLAY_XG_EXPECTED_GOALS_OUT_OF_RANGE")
    values = [math.exp(-mean)]
    for goals in range(1, MAX_GOALS + 1):
        values.append(values[-1] * mean / goals)
    total = sum(values)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("OPENPLAY_XG_POISSON_NORMALISATION_FAILED")
    return tuple(value / total for value in values)


def predict_from_recent_features(
    *,
    home_features: Sequence[Mapping[str, Any]],
    away_features: Sequence[Mapping[str, Any]],
) -> OpenPlayXGPrediction:
    """Estimate independent expected goals from each side's recent xG profile.

    Expected home goals = mean(home xG-for, away xG-against).
    Expected away goals = mean(away xG-for, home xG-against).
    At least one eligible row per side is required; there is no league-only
    prior, generic fallback, home-default output or bookmaker input.
    """
    if not home_features or not away_features:
        raise ValueError("OPENPLAY_XG_BOTH_TEAMS_REQUIRE_HISTORY")

    home_attack = _team_xg(home_features, "xg")
    home_defence = _team_xg(home_features, "xg_against")
    away_attack = _team_xg(away_features, "xg")
    away_defence = _team_xg(away_features, "xg_against")

    expected_home = (home_attack + away_defence) / 2.0
    expected_away = (away_attack + home_defence) / 2.0
    home_pmf = _poisson_distribution(expected_home)
    away_pmf = _poisson_distribution(expected_away)

    home_win = draw = away_win = btts = over_2_5 = 0.0
    for home_goals, home_probability in enumerate(home_pmf):
        for away_goals, away_probability in enumerate(away_pmf):
            probability = home_probability * away_probability
            if home_goals > away_goals:
                home_win += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away_win += probability
            if home_goals > 0 and away_goals > 0:
                btts += probability
            if home_goals + away_goals >= 3:
                over_2_5 += probability

    total = home_win + draw + away_win
    if not math.isfinite(total) or total <= 0:
        raise ValueError("OPENPLAY_XG_1X2_NORMALISATION_FAILED")
    home_win, draw, away_win = home_win / total, draw / total, away_win / total

    return OpenPlayXGPrediction(
        model_version=MODEL_VERSION,
        formula_version=FORMULA_VERSION,
        expected_home_goals=expected_home,
        expected_away_goals=expected_away,
        home_win=home_win,
        draw=draw,
        away_win=away_win,
        btts_yes=btts,
        over_2_5=over_2_5,
        home_sample_count=len(home_features),
        away_sample_count=len(away_features),
    )
