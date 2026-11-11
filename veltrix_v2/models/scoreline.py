"""Normalized joint scoreline distributions and coherent market derivation.

This module transforms a complete model scoreline distribution into market
probabilities. It does not fit a goal model or synthesize missing probability
mass. All markets are derived from the same joint scoreline support.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ScorelineProbability:
    home_goals: int
    away_goals: int
    probability: float

    def __post_init__(self) -> None:
        for name, value in (("home_goals", self.home_goals), ("away_goals", self.away_goals)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if isinstance(self.probability, bool) or not isinstance(self.probability, Real):
            raise ValueError("scoreline probability must be a real number")
        if not isfinite(float(self.probability)) or not 0.0 <= self.probability <= 1.0:
            raise ValueError("scoreline probability must be finite and within [0, 1]")


@dataclass(frozen=True, slots=True)
class MarketProbabilitySet:
    p_home_win: float
    p_draw: float
    p_away_win: float
    p_btts_yes: float
    p_btts_no: float
    total_line: float
    p_over: float
    p_under: float
    expected_home_goals: float
    expected_away_goals: float

    def __post_init__(self) -> None:
        pairs = (
            (self.p_home_win, self.p_draw, self.p_away_win),
            (self.p_btts_yes, self.p_btts_no),
            (self.p_over, self.p_under),
        )
        for pair in pairs:
            if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in pair):
                raise ValueError("market probabilities must be finite and within [0, 1]")
            if abs(sum(pair) - 1.0) > 1e-9:
                raise ValueError("each derived market must sum to one")
        if not isfinite(self.total_line) or self.total_line < 0:
            raise ValueError("total_line must be finite and non-negative")
        if abs((self.total_line % 1.0) - 0.5) > 1e-9:
            raise ValueError("total_line must be a half-goal line; integer lines require push handling")
        if not isfinite(self.expected_home_goals) or not isfinite(self.expected_away_goals):
            raise ValueError("expected goals must be finite")


@dataclass(frozen=True, slots=True)
class ScorelineDistribution:
    fixture_id: str
    model_version: str
    scorelines: tuple[ScorelineProbability, ...]

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.fixture_id.strip():
            raise ValueError("fixture_id is required")
        if not self.model_version or not self.model_version.strip():
            raise ValueError("model_version is required")
        rows = tuple(self.scorelines)
        object.__setattr__(self, "scorelines", rows)
        if not rows:
            raise ValueError("scoreline distribution cannot be empty")
        pairs = [(row.home_goals, row.away_goals) for row in rows]
        if len(pairs) != len(set(pairs)):
            raise ValueError("duplicate scoreline outcomes are not allowed")
        if abs(sum(row.probability for row in rows) - 1.0) > 1e-9:
            raise ValueError("scoreline probability mass must sum to one; no auto-normalization")

    @classmethod
    def from_rows(
        cls,
        fixture_id: str,
        model_version: str,
        scorelines: Iterable[ScorelineProbability],
    ) -> "ScorelineDistribution":
        return cls(fixture_id, model_version, tuple(scorelines))

    def derive_markets(self, *, total_line: float = 2.5) -> MarketProbabilitySet:
        """Derive 1X2, BTTS and one half-goal O/U line from joint mass."""
        if isinstance(total_line, bool) or not isinstance(total_line, Real):
            raise ValueError("total_line must be a real number")
        line = float(total_line)
        if not isfinite(line) or line < 0:
            raise ValueError("total_line must be finite and non-negative")
        if abs((line % 1.0) - 0.5) > 1e-9:
            raise ValueError("total_line must be a half-goal line; integer lines require push handling")

        home_win = draw = away_win = btts_yes = over = 0.0
        expected_home = expected_away = 0.0
        for row in self.scorelines:
            home = row.home_goals
            away = row.away_goals
            mass = row.probability
            if home > away:
                home_win += mass
            elif home == away:
                draw += mass
            else:
                away_win += mass
            if home > 0 and away > 0:
                btts_yes += mass
            if home + away > line:
                over += mass
            expected_home += home * mass
            expected_away += away * mass

        return MarketProbabilitySet(
            p_home_win=home_win,
            p_draw=draw,
            p_away_win=away_win,
            p_btts_yes=btts_yes,
            p_btts_no=1.0 - btts_yes,
            total_line=line,
            p_over=over,
            p_under=1.0 - over,
            expected_home_goals=expected_home,
            expected_away_goals=expected_away,
        )
