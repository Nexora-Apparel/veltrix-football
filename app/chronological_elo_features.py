"""Chronological, competition-scoped Elo ratings for VELTRIX model features.

Ratings are reconstructed only from matches settled before each target cutoff.
This module creates a strength feature; it is not itself a calibrated market
probability model and cannot publish predictions.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any


class EloFeatureError(ValueError):
    pass


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise EloFeatureError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise EloFeatureError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EloFeatureError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _expected(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _margin_multiplier(goal_difference: int) -> float:
    margin = max(1, abs(goal_difference))
    return math.log1p(margin) * (2.2 / (2.2 + 0.001 * abs(goal_difference)))


def reconstruct_elo_features(*, history: list[dict], targets: list[dict],
                             initial_rating: float = 1500.0,
                             k_factor: float = 20.0,
                             home_advantage: float = 60.0) -> dict:
    """Return leakage-safe Elo differences for target fixtures.

    History records require competition_key, fixture_id, kickoff_at, settled_at,
    home_team_id, away_team_id, home_score, away_score and source_record_sha256.
    Target records require fixture_id, competition_key, kickoff_at,
    feature_as_of, home_team_id and away_team_id.
    """
    if not isinstance(history, list) or not isinstance(targets, list) or not targets:
        raise EloFeatureError("history_and_targets_must_be_lists")
    for name, value, low, high in (
        ("initial_rating", initial_rating, 1000, 2000),
        ("k_factor", k_factor, 1, 100),
        ("home_advantage", home_advantage, 0, 200),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise EloFeatureError(f"{name}_out_of_range")

    clean_history = []
    seen = set()
    required_history = {"competition_key", "fixture_id", "kickoff_at", "settled_at",
                        "home_team_id", "away_team_id", "home_score", "away_score",
                        "source_record_sha256"}
    for i, row in enumerate(history):
        if not isinstance(row, dict) or set(row) != required_history:
            raise EloFeatureError(f"history_shape_invalid:{i}")
        if any(not isinstance(row[key], str) or not row[key].strip()
               for key in ("competition_key", "fixture_id", "home_team_id", "away_team_id")):
            raise EloFeatureError(f"history_identity_invalid:{i}")
        if row["home_team_id"] == row["away_team_id"]:
            raise EloFeatureError(f"history_same_team:{row['fixture_id']}")
        if row["fixture_id"] in seen:
            raise EloFeatureError(f"history_duplicate_fixture:{row['fixture_id']}")
        seen.add(row["fixture_id"])
        kickoff = _time(row["kickoff_at"], f"history_{i}_kickoff")
        settled = _time(row["settled_at"], f"history_{i}_settled")
        if settled <= kickoff:
            raise EloFeatureError(f"history_settlement_order_invalid:{row['fixture_id']}")
        for key in ("home_score", "away_score"):
            if isinstance(row[key], bool) or not isinstance(row[key], int) or not 0 <= row[key] <= 20:
                raise EloFeatureError(f"history_score_invalid:{row['fixture_id']}")
        digest = row["source_record_sha256"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise EloFeatureError(f"history_source_digest_invalid:{row['fixture_id']}")
        clean_history.append({**row, "_kickoff": kickoff, "_settled": settled})

    clean_targets = []
    target_ids = set()
    for i, row in enumerate(targets):
        required = {"fixture_id", "competition_key", "kickoff_at", "feature_as_of",
                    "home_team_id", "away_team_id"}
        if not isinstance(row, dict) or set(row) != required:
            raise EloFeatureError(f"target_shape_invalid:{i}")
        if row["fixture_id"] in target_ids or row["fixture_id"] in seen:
            raise EloFeatureError(f"target_fixture_duplicate:{row['fixture_id']}")
        target_ids.add(row["fixture_id"])
        if row["home_team_id"] == row["away_team_id"]:
            raise EloFeatureError(f"target_same_team:{row['fixture_id']}")
        kickoff = _time(row["kickoff_at"], f"target_{i}_kickoff")
        cutoff = _time(row["feature_as_of"], f"target_{i}_feature_as_of")
        if cutoff >= kickoff:
            raise EloFeatureError(f"target_feature_cutoff_invalid:{row['fixture_id']}")
        clean_targets.append({**row, "_kickoff": kickoff, "_cutoff": cutoff})

    # Each competition has an isolated rating pool; no unverified cross-league
    # rating transfer or promoted-team prior is silently introduced.
    by_competition: dict[str, list[dict]] = {}
    for row in clean_history:
        by_competition.setdefault(row["competition_key"], []).append(row)
    output = []
    for target in sorted(clean_targets, key=lambda item: (item["_cutoff"], item["fixture_id"])):
        ratings = {}
        relevant = by_competition.get(target["competition_key"], [])
        eligible = [row for row in relevant if row["_settled"] < target["_cutoff"]]
        eligible.sort(key=lambda item: (item["_settled"], item["fixture_id"]))
        for match in eligible:
            home = match["home_team_id"]
            away = match["away_team_id"]
            rh = ratings.get(home, float(initial_rating)) + float(home_advantage)
            ra = ratings.get(away, float(initial_rating))
            expected_home = _expected(rh, ra)
            expected_away = 1.0 - expected_home
            if match["home_score"] > match["away_score"]:
                actual_home, actual_away = 1.0, 0.0
            elif match["home_score"] < match["away_score"]:
                actual_home, actual_away = 0.0, 1.0
            else:
                actual_home = actual_away = 0.5
            margin = _margin_multiplier(match["home_score"] - match["away_score"])
            change = float(k_factor) * margin * (actual_home - expected_home)
            ratings[home] = ratings.get(home, float(initial_rating)) + change
            ratings[away] = ratings.get(away, float(initial_rating)) - change

        home_rating = ratings.get(target["home_team_id"], float(initial_rating))
        away_rating = ratings.get(target["away_team_id"], float(initial_rating))
        output.append({
            "fixture_id": target["fixture_id"],
            "competition_key": target["competition_key"],
            "feature_as_of": target["feature_as_of"],
            "home_elo": home_rating,
            "away_elo": away_rating,
            "elo_difference_home": home_rating + float(home_advantage) - away_rating,
            "history_match_count": len(eligible),
            "home_team_history_count": sum(
                target["home_team_id"] in (row["home_team_id"], row["away_team_id"])
                for row in eligible
            ),
            "away_team_history_count": sum(
                target["away_team_id"] in (row["home_team_id"], row["away_team_id"])
                for row in eligible
            ),
            "history_source_digest": _digest([
                {"fixture_id": row["fixture_id"],
                 "source_record_sha256": row["source_record_sha256"]}
                for row in eligible
            ]),
            "rating_model": "veltrix-competition-scoped-chronological-elo-v1",
            "probability_model": False,
            "publication_allowed": False,
        })
    return {
        "schema_version": 1,
        "model_family": "veltrix-competition-scoped-chronological-elo-v1",
        "target_count": len(output),
        "features": output,
        "publication_allowed": False,
        "side_effects": {"database_writes": 0, "prediction_publications": 0},
    }
