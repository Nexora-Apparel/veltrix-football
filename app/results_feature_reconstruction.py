"""Leakage-controlled reconstruction of pre-kickoff features from settled results.

This module consumes normalized, provenance-bearing match records. For each target
fixture it uses only earlier fixtures that were settled before the target's
feature cutoff. It intentionally reconstructs results-derived rates, Elo, form,
rest and competition scoring baselines; it never fabricates or relabels xG.
"""
from __future__ import annotations

import hashlib
import json
import math

from app.source_payload_provenance import (
    SourcePayloadProvenanceError,
    validate_source_payload_evidence,
)
from datetime import datetime, timedelta, timezone
from typing import Any

FEATURE_SCHEMA_VERSION = "veltrix-results-features-v1"
DEFAULT_FORM_WINDOW = 10
DEFAULT_ELO = 1500.0
ELO_K = 24.0
HOME_ELO_ADVANTAGE = 55.0


class FeatureReconstructionError(ValueError):
    pass


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise FeatureReconstructionError(f"{field}_invalid")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise FeatureReconstructionError(f"{field}_invalid") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise FeatureReconstructionError(f"{field}_timezone_missing")
    return result.astimezone(timezone.utc)


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_match(row: Any, index: int) -> dict:
    required = {
        "fixture_id", "provider", "source_id", "competition_id", "kickoff_at",
        "settled_at", "home_team_id", "away_team_id", "home_score", "away_score",
        "endpoint", "retrieved_at", "payload_sha256", "run_id", "normalized_status",
        "source_payload",
    }
    if not isinstance(row, dict) or set(row) != required:
        raise FeatureReconstructionError(f"match_shape_invalid:{index}")
    for field in ("fixture_id", "competition_id", "home_team_id", "away_team_id"):
        if not isinstance(row[field], str) or not row[field].strip():
            raise FeatureReconstructionError(f"{field}_invalid:{index}")
    if row["home_team_id"] == row["away_team_id"]:
        raise FeatureReconstructionError(f"same_team_fixture:{row['fixture_id']}")
    for field in ("provider", "source_id", "endpoint", "run_id"):
        if not isinstance(row[field], str) or not row[field].strip():
            raise FeatureReconstructionError(f"{field}_invalid:{index}")
    if row["normalized_status"] != "finished":
        raise FeatureReconstructionError(f"historical_status_not_finished:{row['fixture_id']}")
    kickoff = _parse_time(row["kickoff_at"], f"kickoff_{index}")
    settled = _parse_time(row["settled_at"], f"settled_{index}")
    retrieved = _parse_time(row["retrieved_at"], f"retrieved_{index}")
    if settled <= kickoff or retrieved < settled:
        raise FeatureReconstructionError(f"source_temporal_order_invalid:{row['fixture_id']}")
    for field in ("home_score", "away_score"):
        value = row[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise FeatureReconstructionError(f"score_invalid:{row['fixture_id']}:{field}")
    evidence = row["source_payload"]
    try:
        evidence_integrity = validate_source_payload_evidence(evidence)
    except SourcePayloadProvenanceError as exc:
        raise FeatureReconstructionError(
            f"source_payload_evidence_invalid:{row['fixture_id']}:{exc}"
        ) from None
    normalized_record = {
        key: row[key] for key in (
            "fixture_id", "competition_id", "kickoff_at", "settled_at",
            "home_team_id", "away_team_id", "home_score", "away_score",
            "normalized_status",
        )
    }
    if evidence["normalized_record"] != normalized_record:
        raise FeatureReconstructionError(
            f"normalized_record_payload_binding_mismatch:{row['fixture_id']}"
        )
    if any(evidence_integrity[key] != row[key] for key in (
        "provider", "source_id", "endpoint", "run_id", "retrieved_at",
        "payload_sha256",
    )):
        raise FeatureReconstructionError(
            f"source_payload_metadata_binding_mismatch:{row['fixture_id']}"
        )
    digest = row["payload_sha256"]
    if digest != evidence_integrity["payload_sha256"]:
        raise FeatureReconstructionError(f"source_hash_invalid:{row['fixture_id']}")
    return {
        **row,
        "source_record_sha256": digest,
        "_kickoff": kickoff,
        "_settled": settled,
        "_retrieved": retrieved,
    }


def _points_for(team_id: str, row: dict) -> int:
    home, away = row["home_score"], row["away_score"]
    if home == away:
        return 1
    winner = row["home_team_id"] if home > away else row["away_team_id"]
    return 3 if winner == team_id else 0


def _team_goals(team_id: str, row: dict) -> tuple[int, int]:
    if row["home_team_id"] == team_id:
        return row["home_score"], row["away_score"]
    return row["away_score"], row["home_score"]


def _elo_ratings(history: list[dict], cutoff: datetime) -> dict[str, float]:
    ratings: dict[str, float] = {}
    for row in sorted(history, key=lambda item: (item["_kickoff"], item["fixture_id"])):
        if row["_settled"] > cutoff or row["_retrieved"] > cutoff:
            continue
        home = ratings.get(row["home_team_id"], DEFAULT_ELO)
        away = ratings.get(row["away_team_id"], DEFAULT_ELO)
        expected_home = 1.0 / (
            1.0 + 10.0 ** ((away - (home + HOME_ELO_ADVANTAGE)) / 400.0)
        )
        if row["home_score"] > row["away_score"]:
            actual_home = 1.0
        elif row["home_score"] == row["away_score"]:
            actual_home = 0.5
        else:
            actual_home = 0.0
        delta = ELO_K * (actual_home - expected_home)
        ratings[row["home_team_id"]] = home + delta
        ratings[row["away_team_id"]] = away - delta
    return ratings


def _team_window(team_id: str, history: list[dict], cutoff: datetime,
                 window: int) -> list[dict]:
    eligible = [
        row for row in history
        if row["_settled"] <= cutoff
        and row["_retrieved"] <= cutoff
        and row["_kickoff"] < cutoff
        and team_id in (row["home_team_id"], row["away_team_id"])
    ]
    return sorted(eligible, key=lambda item: (item["_kickoff"], item["fixture_id"]))[-window:]


def _rates(team_id: str, matches: list[dict]) -> tuple[float, float, float, datetime | None]:
    if not matches:
        raise FeatureReconstructionError(f"insufficient_team_history:{team_id}")
    scored, conceded, points = 0, 0, 0
    for row in matches:
        gf, ga = _team_goals(team_id, row)
        scored += gf
        conceded += ga
        points += _points_for(team_id, row)
    count = len(matches)
    return scored / count, conceded / count, points / (3.0 * count), matches[-1]["_kickoff"]


def _competition_rates(competition_id: str, history: list[dict],
                       cutoff: datetime) -> tuple[float, float]:
    rows = [
        row for row in history
        if row["competition_id"] == competition_id
        and row["_settled"] <= cutoff
        and row["_retrieved"] <= cutoff
        and row["_kickoff"] < cutoff
    ]
    if not rows:
        raise FeatureReconstructionError(
            f"insufficient_competition_history:{competition_id}"
        )
    return (
        sum(row["home_score"] for row in rows) / len(rows),
        sum(row["away_score"] for row in rows) / len(rows),
    )


def reconstruct_pre_match_features(*, historical_matches: list[dict],
                                   target_fixture: dict,
                                   cutoff_hours: int = 6,
                                   form_window: int = DEFAULT_FORM_WINDOW,
                                   minimum_team_matches: int = 3) -> dict:
    """Reconstruct one target's features without using its result or future data.

    Historical rows must be unique, settled, normalized and source-hash verified.
    A target is withheld if either team or its competition lacks the minimum
    evidence. No zero/default rates are substituted for missing history.
    """
    if not isinstance(historical_matches, list):
        raise FeatureReconstructionError("historical_matches_not_list")
    if (isinstance(cutoff_hours, bool) or not isinstance(cutoff_hours, int)
            or not 0 <= cutoff_hours <= 168):
        raise FeatureReconstructionError("cutoff_hours_out_of_range")
    if (isinstance(form_window, bool) or not isinstance(form_window, int)
            or not 3 <= form_window <= 30):
        raise FeatureReconstructionError("form_window_out_of_range")
    if (isinstance(minimum_team_matches, bool)
            or not isinstance(minimum_team_matches, int)
            or not 1 <= minimum_team_matches <= form_window):
        raise FeatureReconstructionError("minimum_team_matches_out_of_range")
    target_required = {"fixture_id", "competition_id", "kickoff_at",
                       "home_team_id", "away_team_id"}
    if not isinstance(target_fixture, dict) or set(target_fixture) != target_required:
        raise FeatureReconstructionError("target_fixture_shape_invalid")
    for field in target_required:
        if not isinstance(target_fixture[field], str) or not target_fixture[field].strip():
            raise FeatureReconstructionError(f"target_{field}_invalid")
    if target_fixture["home_team_id"] == target_fixture["away_team_id"]:
        raise FeatureReconstructionError("target_same_team_fixture")
    kickoff = _parse_time(target_fixture["kickoff_at"], "target_kickoff")
    cutoff = kickoff - timedelta(hours=cutoff_hours)

    history = [_validate_match(row, i) for i, row in enumerate(historical_matches)]
    ids = [row["fixture_id"] for row in history]
    if len(ids) != len(set(ids)):
        raise FeatureReconstructionError("duplicate_historical_fixture_id")
    if target_fixture["fixture_id"] in set(ids):
        raise FeatureReconstructionError("target_fixture_present_in_history")
    eligible = [
        row for row in history
        if (row["_kickoff"] < kickoff and row["_settled"] <= cutoff
                and row["_retrieved"] <= cutoff)
    ]
    if not eligible:
        raise FeatureReconstructionError("no_eligible_pre_kickoff_history")

    home_id, away_id = target_fixture["home_team_id"], target_fixture["away_team_id"]
    home_matches = _team_window(home_id, eligible, cutoff, form_window)
    away_matches = _team_window(away_id, eligible, cutoff, form_window)
    if len(home_matches) < minimum_team_matches:
        raise FeatureReconstructionError(f"home_history_below_minimum:{len(home_matches)}")
    if len(away_matches) < minimum_team_matches:
        raise FeatureReconstructionError(f"away_history_below_minimum:{len(away_matches)}")

    home_attack, home_defence, home_form, home_last = _rates(home_id, home_matches)
    away_attack, away_defence, away_form, away_last = _rates(away_id, away_matches)
    home_rest = (cutoff - home_last).total_seconds() / 86400.0
    away_rest = (cutoff - away_last).total_seconds() / 86400.0
    if not 0 <= home_rest <= 60 or not 0 <= away_rest <= 60:
        raise FeatureReconstructionError("rest_interval_out_of_range")

    competition_home, competition_away = _competition_rates(
        target_fixture["competition_id"], eligible, cutoff
    )
    elo = _elo_ratings(eligible, cutoff)
    features = {
        "home_attack_goals_rate": home_attack,
        "home_defence_conceded_rate": home_defence,
        "away_attack_goals_rate": away_attack,
        "away_defence_conceded_rate": away_defence,
        "elo_difference_home": (
            elo.get(home_id, DEFAULT_ELO) - elo.get(away_id, DEFAULT_ELO)
        ),
        "home_form_points_rate": home_form,
        "away_form_points_rate": away_form,
        "home_rest_days": home_rest,
        "away_rest_days": away_rest,
        "competition_home_goals_rate": competition_home,
        "competition_away_goals_rate": competition_away,
    }
    if any(not math.isfinite(value) for value in features.values()):
        raise FeatureReconstructionError("non_finite_feature")
    provenance_rows = sorted(
        eligible, key=lambda item: (item["_kickoff"], item["fixture_id"])
    )
    eligible_source_records = [
        {"fixture_id": row["fixture_id"], "provider": row["provider"],
         "source_id": row["source_id"], "endpoint": row["endpoint"],
         "payload_sha256": row["payload_sha256"], "run_id": row["run_id"],
         "settled_at": row["_settled"].isoformat(),
         "retrieved_at": row["_retrieved"].isoformat()}
        for row in provenance_rows
    ]
    source_provenance = {
        "source": "veltrix_results_feature_reconstruction",
        "source_id": "history:" + _digest(eligible_source_records),
        "payload_sha256": _digest(eligible_source_records),
        "observed_at": max(row["_kickoff"] for row in provenance_rows).isoformat(),
        "available_at": max(row["_settled"] for row in provenance_rows).isoformat(),
        "retrieved_at": max(row["_retrieved"] for row in provenance_rows).isoformat(),
    }
    provenance = {
        "schema_version": FEATURE_SCHEMA_VERSION,
        "target_fixture_id": target_fixture["fixture_id"],
        "target_kickoff_at": kickoff.isoformat(),
        "feature_as_of": cutoff.isoformat(),
        "cutoff_hours": cutoff_hours,
        "form_window": form_window,
        "minimum_team_matches": minimum_team_matches,
        "eligible_history_count": len(eligible),
        "home_history_count": len(home_matches),
        "away_history_count": len(away_matches),
        "eligible_fixture_ids_sha256": _digest(eligible_source_records),
        "source_provenance": source_provenance,
        "source": "settled_historical_results_only",
        "xg_used": False,
        "point_in_time_verified": True,
    }
    return {
        "fixture_id": target_fixture["fixture_id"],
        "competition_id": target_fixture["competition_id"],
        "kickoff_at": kickoff.isoformat(),
        "feature_as_of": cutoff.isoformat(),
        "features": features,
        "provenance": provenance,
        "feature_snapshot_sha256": _digest({
            "features": features, "provenance": provenance
        }),
        "publication_allowed": False,
    }
