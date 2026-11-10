"""New Veltrix pre-match Dixon-Coles/Poisson inference engine.

Consumes only validated point-in-time feature snapshots and explicit fitted
parameter sets. Missing or unsupported inputs withhold the forecast; there is
no global prior or favourite-default fallback. Inference is not publication.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from app.point_in_time_feature_contract import (
    PointInTimeFeatureError,
    validate_point_in_time_feature_snapshot,
)


MODEL_VERSION = "veltrix-dixon-coles-poisson-v1"
REQUIRED_FEATURES = {
    "home_team_elo",
    "away_team_elo",
    "home_rolling_xg_for",
    "home_rolling_xg_against",
    "away_rolling_xg_for",
    "away_rolling_xg_against",
}


class ModelInferenceError(ValueError):
    pass


def _hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_model_parameter_set(*, training_dataset_sha256: str,
                              training_data_cutoff_at: str,
                              trained_until: str, trained_at: str,
                              home_advantage_multiplier: float,
                              elo_goal_coefficient: float,
                              rho: float, max_goals: int = 15,
                              calibration_id: str) -> dict:
    """Create a digest-bound fitted parameter set; values must come from training."""
    params = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "training_dataset_sha256": training_dataset_sha256,
        "training_data_cutoff_at": training_data_cutoff_at,
        "trained_until": trained_until,
        "trained_at": trained_at,
        "home_advantage_multiplier": home_advantage_multiplier,
        "elo_goal_coefficient": elo_goal_coefficient,
        "rho": rho,
        "max_goals": max_goals,
        "calibration_id": calibration_id,
    }
    params["parameter_sha256"] = _hash(params)
    return params


def _parse_time(value: Any, field: str):
    from datetime import datetime
    if not isinstance(value, str):
        raise ModelInferenceError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ModelInferenceError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ModelInferenceError(f"{field}_timezone_missing")
    return parsed


def validate_model_parameter_set(params: Any, prediction_as_of: str) -> dict:
    expected = {
        "schema_version", "model_version", "training_dataset_sha256",
        "training_data_cutoff_at", "trained_until", "trained_at",
        "home_advantage_multiplier", "elo_goal_coefficient", "rho",
        "max_goals", "calibration_id", "parameter_sha256",
    }
    if not isinstance(params, dict) or set(params) != expected:
        raise ModelInferenceError("model_parameter_shape_invalid")
    if params.get("schema_version") != 1 or params.get("model_version") != MODEL_VERSION:
        raise ModelInferenceError("model_parameter_version_invalid")
    supplied = params.get("parameter_sha256")
    unhashed = dict(params)
    unhashed.pop("parameter_sha256", None)
    if not isinstance(supplied, str) or len(supplied) != 64 or _hash(unhashed) != supplied:
        raise ModelInferenceError("model_parameter_hash_invalid")
    digest = params.get("training_dataset_sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)):
        raise ModelInferenceError("training_dataset_hash_invalid")
    if not isinstance(params.get("calibration_id"), str) or not params["calibration_id"].strip():
        raise ModelInferenceError("calibration_id_missing")

    cutoff = _parse_time(prediction_as_of, "prediction_as_of")
    data_cutoff = _parse_time(params["training_data_cutoff_at"], "training_data_cutoff_at")
    trained_until = _parse_time(params["trained_until"], "trained_until")
    trained_at = _parse_time(params["trained_at"], "trained_at")
    if data_cutoff > cutoff or trained_until > data_cutoff or trained_at > cutoff:
        raise ModelInferenceError("model_parameter_temporal_leakage")

    home_advantage = params.get("home_advantage_multiplier")
    elo_coefficient = params.get("elo_goal_coefficient")
    rho = params.get("rho")
    max_goals = params.get("max_goals")
    for name, value in (
        ("home_advantage_multiplier", home_advantage),
        ("elo_goal_coefficient", elo_coefficient),
        ("rho", rho),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ModelInferenceError(f"model_parameter_{name}_invalid")
    if not 0.8 <= home_advantage <= 1.3:
        raise ModelInferenceError("home_advantage_multiplier_out_of_range")
    if not 0 <= elo_coefficient <= 0.01:
        raise ModelInferenceError("elo_goal_coefficient_out_of_range")
    if not -0.2 <= rho <= 0.2:
        raise ModelInferenceError("dixon_coles_rho_out_of_range")
    if isinstance(max_goals, bool) or not isinstance(max_goals, int) or not 12 <= max_goals <= 15:
        raise ModelInferenceError("max_goals_out_of_range")
    return {
        "valid": True,
        "parameter_sha256": supplied,
        "training_data_cutoff_at": data_cutoff.isoformat(),
        "trained_until": trained_until.isoformat(),
        "trained_at": trained_at.isoformat(),
    }


def _poisson_probabilities(lam: float, max_goals: int) -> list[float]:
    values = [math.exp(-lam)]
    for goals in range(1, max_goals + 1):
        values.append(values[-1] * lam / goals)
    tail = max(0.0, 1.0 - sum(values))
    if tail > 1e-4:
        raise ModelInferenceError("poisson_tail_mass_exceeds_tolerance")
    return values


def _dixon_coles_tau(home_goals: int, away_goals: int,
                     lambda_home: float, lambda_away: float,
                     rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def infer_pre_match_forecast(*, snapshot: dict, model_parameters: dict) -> dict:
    try:
        snapshot_check = validate_point_in_time_feature_snapshot(snapshot)
    except (PointInTimeFeatureError, TypeError, KeyError) as exc:
        raise ModelInferenceError(f"feature_snapshot_invalid:{str(exc)[:120]}") from None
    parameter_check = validate_model_parameter_set(
        model_parameters, snapshot["prediction_as_of"]
    )
    features = {item["name"]: item["value"] for item in snapshot["features"]}
    missing = sorted(REQUIRED_FEATURES - set(features))
    base = {
        "schema_version": 1,
        "forecast_type": "veltrix_pre_match_dixon_coles_forecast",
        "model_version": MODEL_VERSION,
        "fixture_id": snapshot["fixture_id"],
        "prediction_as_of": snapshot["prediction_as_of"],
        "feature_snapshot_sha256": snapshot_check["snapshot_sha256"],
        "model_parameter_sha256": parameter_check["parameter_sha256"],
        "required_features": sorted(REQUIRED_FEATURES),
        "missing_features": missing,
        "publication_allowed": False,
        "value_betting_enabled": False,
    }
    if missing:
        result = {
            **base,
            "status": "withheld",
            "withheld_reasons": ["required_point_in_time_features_missing"],
            "expected_goals": None,
            "probabilities": None,
            "score_matrix": None,
        }
        result["forecast_sha256"] = _hash(result)
        return result

    numeric = {name: features[name] for name in REQUIRED_FEATURES}
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(value) for value in numeric.values()):
        raise ModelInferenceError("required_feature_value_invalid")
    elo_home, elo_away = numeric["home_team_elo"], numeric["away_team_elo"]
    xg_values = [
        numeric["home_rolling_xg_for"], numeric["home_rolling_xg_against"],
        numeric["away_rolling_xg_for"], numeric["away_rolling_xg_against"],
    ]
    if not 500 <= elo_home <= 3000 or not 500 <= elo_away <= 3000:
        return _withheld(base, "elo_feature_out_of_supported_range")
    if any(value <= 0 or value > 4.5 for value in xg_values):
        return _withheld(base, "rolling_xg_feature_out_of_supported_range")

    params = model_parameters
    base_home = math.sqrt(
        numeric["home_rolling_xg_for"] * numeric["away_rolling_xg_against"]
    )
    base_away = math.sqrt(
        numeric["away_rolling_xg_for"] * numeric["home_rolling_xg_against"]
    )
    elo_difference = elo_home - elo_away
    elo_adjustment = math.exp(params["elo_goal_coefficient"] * elo_difference / 2.0)
    lambda_home = base_home * params["home_advantage_multiplier"] * elo_adjustment
    lambda_away = base_away / elo_adjustment
    if not 0.05 <= lambda_home <= 4.5 or not 0.05 <= lambda_away <= 4.5:
        return _withheld(base, "expected_goal_rate_out_of_supported_range")

    max_goals = params["max_goals"]
    home_p = _poisson_probabilities(lambda_home, max_goals)
    away_p = _poisson_probabilities(lambda_away, max_goals)
    rho = params["rho"]
    matrix = []
    for home_goals in range(max_goals + 1):
        row = []
        for away_goals in range(max_goals + 1):
            tau = _dixon_coles_tau(
                home_goals, away_goals, lambda_home, lambda_away, rho
            )
            probability = home_p[home_goals] * away_p[away_goals] * tau
            if not math.isfinite(probability) or probability < 0:
                return _withheld(base, "dixon_coles_correction_invalid")
            row.append(probability)
        matrix.append(row)
    total = sum(sum(row) for row in matrix)
    if not math.isfinite(total) or total <= 0:
        return _withheld(base, "joint_score_distribution_invalid")
    matrix = [[value / total for value in row] for row in matrix]

    p_home = sum(matrix[h][a] for h in range(max_goals + 1) for a in range(max_goals + 1) if h > a)
    p_draw = sum(matrix[g][g] for g in range(max_goals + 1))
    p_away = sum(matrix[h][a] for h in range(max_goals + 1) for a in range(max_goals + 1) if h < a)
    p_btts_yes = sum(matrix[h][a] for h in range(1, max_goals + 1) for a in range(1, max_goals + 1))
    p_over_25 = sum(matrix[h][a] for h in range(max_goals + 1) for a in range(max_goals + 1) if h + a >= 3)
    probabilities = {
        "1x2": {"home": p_home, "draw": p_draw, "away": p_away},
        "btts": {"yes": p_btts_yes, "no": 1.0 - p_btts_yes},
        "over_2_5": {"yes": p_over_25, "no": 1.0 - p_over_25},
    }
    if (abs(sum(probabilities["1x2"].values()) - 1.0) > 1e-8
            or any(not 0 <= value <= 1 for market in probabilities.values() for value in market.values())):
        return _withheld(base, "derived_market_probabilities_invalid")

    result = {
        **base,
        "status": "inference_complete_validation_required",
        "withheld_reasons": [],
        "expected_goals": {
            "home": round(lambda_home, 6),
            "away": round(lambda_away, 6),
        },
        "elo_difference_home_minus_away": round(elo_difference, 4),
        "probabilities": {
            market: {key: round(value, 10) for key, value in values.items()}
            for market, values in probabilities.items()
        },
        "score_matrix": [[round(value, 12) for value in row] for row in matrix],
        "score_matrix_max_goals_inclusive": max_goals,
        "score_matrix_tail_mass_tolerance": 1e-4,
        "fallback_prior_used": False,
        "favourite_filter_used": False,
    }
    result["forecast_sha256"] = _hash(result)
    return result


def _withheld(base: dict, reason: str) -> dict:
    result = {
        **base,
        "status": "withheld",
        "withheld_reasons": [reason],
        "expected_goals": None,
        "probabilities": None,
        "score_matrix": None,
        "fallback_prior_used": False,
        "favourite_filter_used": False,
    }
    result["forecast_sha256"] = _hash(result)
    return result


def validate_pre_match_forecast(*, forecast: Any, snapshot: dict,
                                model_parameters: dict) -> dict:
    if not isinstance(forecast, dict) or forecast.get("schema_version") != 1:
        raise ModelInferenceError("forecast_schema_invalid")
    supplied = forecast.get("forecast_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64:
        raise ModelInferenceError("forecast_hash_invalid")
    unhashed = dict(forecast)
    unhashed.pop("forecast_sha256", None)
    if _hash(unhashed) != supplied:
        raise ModelInferenceError("forecast_hash_mismatch")
    recomputed = infer_pre_match_forecast(
        snapshot=snapshot, model_parameters=model_parameters
    )
    if recomputed["forecast_sha256"] != supplied:
        raise ModelInferenceError("forecast_recomputation_mismatch")
    if forecast.get("publication_allowed") is not False or forecast.get("value_betting_enabled") is not False:
        raise ModelInferenceError("forecast_publication_boundary_invalid")
    return {
        "valid": True,
        "forecast_sha256": supplied,
        "status": forecast.get("status"),
        "publication_allowed": False,
        "value_betting_enabled": False,
    }
