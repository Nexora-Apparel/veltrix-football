"""Leakage-safe recent team form summaries for VELTRIX forecasts.

Input rows are oldest-to-newest tuples of (goals_for, goals_against, venue).
This module is descriptive only: it does not alter model probabilities.
"""
from __future__ import annotations

from typing import Iterable


def summarize_team_form(
    history: Iterable[tuple[int, int, str]],
    *,
    venue: str | None = None,
) -> dict[str, object]:
    """Summarize last-five/last-ten results, goals and points for one team."""
    rows = list(history)
    if venue in {"home", "away"}:
        rows = [row for row in rows if row[2] == venue]
    rows = rows[-10:]

    def summarize(sample: list[tuple[int, int, str]]) -> dict[str, object]:
        if not sample:
            return {
                "matches": 0, "form": "", "points": 0, "points_per_game": None,
                "goals_for": 0, "goals_against": 0, "goal_difference": 0,
                "clean_sheets": 0, "failed_to_score": 0, "wins": 0,
                "draws": 0, "losses": 0,
            }
        outcomes = [
            "W" if gf > ga else "D" if gf == ga else "L"
            for gf, ga, _ in sample
        ]
        wins = outcomes.count("W")
        draws = outcomes.count("D")
        losses = outcomes.count("L")
        goals_for = sum(row[0] for row in sample)
        goals_against = sum(row[1] for row in sample)
        points = wins * 3 + draws
        count = len(sample)
        return {
            "matches": count,
            "form": "".join(outcomes),
            "points": points,
            "points_per_game": round(points / count, 3),
            "goals_for": goals_for,
            "goals_against": goals_against,
            "goal_difference": goals_for - goals_against,
            "clean_sheets": sum(row[1] == 0 for row in sample),
            "failed_to_score": sum(row[0] == 0 for row in sample),
            "wins": wins,
            "draws": draws,
            "losses": losses,
        }

    return {
        "scope": venue or "all_venues",
        "last_5": summarize(rows[-5:]),
        "last_10": summarize(rows[-10:]),
    }
