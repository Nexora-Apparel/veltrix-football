"""Point-in-time feature snapshot contract for leakage-safe football modelling.

No prediction or model training occurs here. This module validates that every
candidate predictor was observable and available by the declared prediction
cutoff, with source provenance and an immutable snapshot digest.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any


FEATURE_CATALOGUE = {
    "home_team_elo": {"max_age_seconds": 7 * 86400},
    "away_team_elo": {"max_age_seconds": 7 * 86400},
    "home_attack_goals_rate": {"max_age_seconds": 60 * 86400},
    "home_defence_conceded_rate": {"max_age_seconds": 60 * 86400},
    "away_attack_goals_rate": {"max_age_seconds": 60 * 86400},
    "away_defence_conceded_rate": {"max_age_seconds": 60 * 86400},
    "elo_difference_home": {"max_age_seconds": 60 * 86400},
    "home_form_points_rate": {"max_age_seconds": 60 * 86400},
    "away_form_points_rate": {"max_age_seconds": 60 * 86400},
    "home_rest_days": {"max_age_seconds": 60 * 86400},
    "away_rest_days": {"max_age_seconds": 60 * 86400},
    "competition_home_goals_rate": {"max_age_seconds": 60 * 86400},
    "competition_away_goals_rate": {"max_age_seconds": 60 * 86400},
    "home_attack_strength": {"max_age_seconds": 14 * 86400},
    "away_attack_strength": {"max_age_seconds": 14 * 86400},
    "home_defence_strength": {"max_age_seconds": 14 * 86400},
    "away_defence_strength": {"max_age_seconds": 14 * 86400},
    "home_rolling_xg_for": {"max_age_seconds": 14 * 86400},
    "home_rolling_xg_against": {"max_age_seconds": 14 * 86400},
    "away_rolling_xg_for": {"max_age_seconds": 14 * 86400},
    "away_rolling_xg_against": {"max_age_seconds": 14 * 86400},
    "home_rest_days": {"max_age_seconds": 14 * 86400},
    "away_rest_days": {"max_age_seconds": 14 * 86400},
    "home_travel_km": {"max_age_seconds": 14 * 86400},
    "away_travel_km": {"max_age_seconds": 14 * 86400},
    "home_lineup_strength": {"max_age_seconds": 6 * 3600},
    "away_lineup_strength": {"max_age_seconds": 6 * 3600},
    "odds_home_decimal": {"max_age_seconds": 15 * 60},
    "odds_draw_decimal": {"max_age_seconds": 15 * 60},
    "odds_away_decimal": {"max_age_seconds": 15 * 60},
    "odds_btts_yes_decimal": {"max_age_seconds": 15 * 60},
    "odds_over_2_5_decimal": {"max_age_seconds": 15 * 60},
}
FORBIDDEN_FEATURE_NAMES = {
    "home_score", "away_score", "half_time_score", "full_time_score",
    "result", "match_result", "winner", "btts_result", "over_2_5_result",
    "settled_odds", "closing_odds_after_cutoff", "post_match_xg",
    "post_match_shots", "post_match_events", "points_awarded",
}
HEX = set("0123456789abcdef")


class PointInTimeFeatureError(ValueError):
    pass


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise PointInTimeFeatureError(f"{field}_missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PointInTimeFeatureError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PointInTimeFeatureError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_point_in_time_feature_snapshot(*, fixture_id: str,
                                         prediction_as_of: str,
                                         features: list[dict]) -> dict:
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise PointInTimeFeatureError("fixture_id_required")
    if not isinstance(features, list):
        raise PointInTimeFeatureError("features_must_be_array")
    cutoff = _parse_time(prediction_as_of, "prediction_as_of")
    normalized = []
    seen = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise PointInTimeFeatureError(f"feature_not_object:{index}")
        name = feature.get("name")
        if not isinstance(name, str) or not name:
            raise PointInTimeFeatureError(f"feature_name_invalid:{index}")
        if name in FORBIDDEN_FEATURE_NAMES:
            raise PointInTimeFeatureError(f"target_leakage_feature_forbidden:{name}")
        if name not in FEATURE_CATALOGUE:
            raise PointInTimeFeatureError(f"feature_not_in_pre_match_catalogue:{name}")
        if name in seen:
            raise PointInTimeFeatureError(f"duplicate_feature:{name}")
        seen.add(name)
        value = feature.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise PointInTimeFeatureError(f"feature_value_invalid:{name}")
        source = feature.get("source")
        source_id = feature.get("source_id")
        payload_hash = feature.get("payload_sha256")
        if not isinstance(source, str) or not source.strip():
            raise PointInTimeFeatureError(f"feature_source_missing:{name}")
        if not isinstance(source_id, str) or not source_id.strip():
            raise PointInTimeFeatureError(f"feature_source_id_missing:{name}")
        if (not isinstance(payload_hash, str) or len(payload_hash) != 64
                or any(char not in HEX for char in payload_hash)):
            raise PointInTimeFeatureError(f"feature_payload_hash_invalid:{name}")
        observed = _parse_time(feature.get("observed_at"), f"{name}_observed_at")
        available = _parse_time(feature.get("available_at"), f"{name}_available_at")
        retrieved = _parse_time(feature.get("retrieved_at"), f"{name}_retrieved_at")
        if observed > cutoff:
            raise PointInTimeFeatureError(f"future_observation:{name}")
        if available > cutoff:
            raise PointInTimeFeatureError(f"future_availability:{name}")
        if retrieved > cutoff:
            raise PointInTimeFeatureError(f"future_retrieval:{name}")
        if available < observed:
            raise PointInTimeFeatureError(f"availability_precedes_observation:{name}")
        if retrieved < available:
            raise PointInTimeFeatureError(f"retrieval_precedes_availability:{name}")
        age = (cutoff - observed).total_seconds()
        if age > FEATURE_CATALOGUE[name]["max_age_seconds"]:
            raise PointInTimeFeatureError(f"stale_feature:{name}")
        normalized.append({
            "name": name,
            "value": float(value),
            "source": source.strip(),
            "source_id": source_id.strip(),
            "observed_at": observed.isoformat().replace("+00:00", "Z"),
            "available_at": available.isoformat().replace("+00:00", "Z"),
            "retrieved_at": retrieved.isoformat().replace("+00:00", "Z"),
            "payload_sha256": payload_hash,
        })
    normalized.sort(key=lambda item: item["name"])
    snapshot = {
        "schema_version": 1,
        "snapshot_type": "veltrix_point_in_time_pre_match_features",
        "fixture_id": fixture_id.strip(),
        "prediction_as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "feature_count": len(normalized),
        "features": normalized,
        "target_label_separate": True,
        "model_training_certified": False,
    }
    snapshot["snapshot_sha256"] = _hash(snapshot)
    return snapshot


def validate_point_in_time_feature_snapshot(snapshot: Any) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1:
        raise PointInTimeFeatureError("snapshot_schema_invalid")
    expected_snapshot_keys = {
        "schema_version", "snapshot_type", "fixture_id", "prediction_as_of",
        "feature_count", "features", "target_label_separate",
        "model_training_certified", "snapshot_sha256",
    }
    if set(snapshot) != expected_snapshot_keys:
        raise PointInTimeFeatureError("snapshot_shape_invalid")
    if not isinstance(snapshot.get("fixture_id"), str) or not snapshot["fixture_id"].strip():
        raise PointInTimeFeatureError("snapshot_fixture_id_invalid")
    if snapshot.get("snapshot_type") != "veltrix_point_in_time_pre_match_features":
        raise PointInTimeFeatureError("snapshot_type_invalid")
    supplied = snapshot.get("snapshot_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64 or any(c not in HEX for c in supplied):
        raise PointInTimeFeatureError("snapshot_hash_invalid")
    unhashed = dict(snapshot)
    unhashed.pop("snapshot_sha256", None)
    if _hash(unhashed) != supplied:
        raise PointInTimeFeatureError("snapshot_hash_mismatch")
    cutoff = _parse_time(snapshot.get("prediction_as_of"), "prediction_as_of")
    features = snapshot.get("features")
    if (not isinstance(features, list) or isinstance(snapshot.get("feature_count"), bool)
            or not isinstance(snapshot.get("feature_count"), int)
            or snapshot.get("feature_count") != len(features)):
        raise PointInTimeFeatureError("snapshot_feature_count_mismatch")
    if snapshot.get("target_label_separate") is not True or snapshot.get("model_training_certified") is not False:
        raise PointInTimeFeatureError("snapshot_certification_boundary_invalid")
    names = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise PointInTimeFeatureError(f"snapshot_feature_invalid:{index}")
        expected_feature_keys = {
            "name", "value", "source", "source_id", "observed_at",
            "available_at", "retrieved_at", "payload_sha256",
        }
        if set(feature) != expected_feature_keys:
            raise PointInTimeFeatureError(f"snapshot_feature_shape_invalid:{index}")
        name = feature.get("name")
        if not isinstance(name, str) or name not in FEATURE_CATALOGUE or name in FORBIDDEN_FEATURE_NAMES:
            raise PointInTimeFeatureError(f"snapshot_feature_not_allowed:{index}")
        value = feature.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise PointInTimeFeatureError(f"snapshot_feature_value_invalid:{index}")
        if not isinstance(feature.get("source"), str) or not feature["source"].strip():
            raise PointInTimeFeatureError(f"snapshot_feature_source_invalid:{index}")
        if not isinstance(feature.get("source_id"), str) or not feature["source_id"].strip():
            raise PointInTimeFeatureError(f"snapshot_feature_source_id_invalid:{index}")
        payload_hash = feature.get("payload_sha256")
        if (not isinstance(payload_hash, str) or len(payload_hash) != 64
                or any(char not in HEX for char in payload_hash)):
            raise PointInTimeFeatureError(f"snapshot_feature_payload_hash_invalid:{index}")
        observed = _parse_time(feature.get("observed_at"), f"feature_{name}_observed_at")
        available = _parse_time(feature.get("available_at"), f"feature_{name}_available_at")
        retrieved = _parse_time(feature.get("retrieved_at"), f"feature_{name}_retrieved_at")
        if observed > cutoff or available > cutoff or retrieved > cutoff:
            raise PointInTimeFeatureError(f"snapshot_future_timestamp:{index}")
        if available < observed or retrieved < available:
            raise PointInTimeFeatureError(f"snapshot_provenance_time_order_invalid:{index}")
        if (cutoff - observed).total_seconds() > FEATURE_CATALOGUE[name]["max_age_seconds"]:
            raise PointInTimeFeatureError(f"snapshot_feature_stale:{index}")
        names.append(name)
    if names != sorted(names) or len(names) != len(set(names)):
        raise PointInTimeFeatureError("snapshot_feature_order_or_uniqueness_invalid")
    return {
        "valid": True,
        "snapshot_sha256": supplied,
        "feature_count": len(features),
        "prediction_as_of": cutoff.isoformat().replace("+00:00", "Z"),
        "model_training_certified": False,
    }
