"""Fail-closed inference boundary for the independent VELTRIX model portfolio.

This service accepts only a provenance-validated pre-match feature snapshot and
sealed independent model artifacts. It never imports the legacy predictor,
blends models, publishes a pick, or enables value betting.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.independent_market_models import (
    FEATURES,
    ResultsModelError,
    predict_independent_markets,
)
from app.point_in_time_feature_contract import (
    PointInTimeFeatureError,
    validate_point_in_time_feature_snapshot,
)
from app.poisson_dixon_coles_model import (
    PoissonModelError,
    predict_poisson_dixon_coles,
)


class IndependentInferenceError(ValueError):
    pass


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise IndependentInferenceError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise IndependentInferenceError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise IndependentInferenceError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def infer_independent_fixture(*, fixture: dict, feature_snapshot: dict,
                              results_model: dict,
                              poisson_artifact: dict | None = None) -> dict:
    """Produce separate shadow candidates; no blending or release authorization."""
    required_fixture = {
        "fixture_id", "competition_key", "home_team_id", "away_team_id",
        "kickoff_at", "feature_as_of",
    }
    if not isinstance(fixture, dict) or not required_fixture.issubset(fixture):
        raise IndependentInferenceError("fixture_contract_incomplete")
    if not all(isinstance(fixture[key], str) and fixture[key].strip()
               for key in required_fixture):
        raise IndependentInferenceError("fixture_identity_or_time_invalid")
    if fixture["home_team_id"] == fixture["away_team_id"]:
        raise IndependentInferenceError("fixture_teams_must_differ")

    try:
        integrity = validate_point_in_time_feature_snapshot(feature_snapshot)
    except (PointInTimeFeatureError, TypeError, KeyError) as exc:
        raise IndependentInferenceError(
            f"feature_snapshot_rejected:{str(exc)[:120]}"
        ) from None

    if feature_snapshot["fixture_id"] != fixture["fixture_id"]:
        raise IndependentInferenceError("feature_snapshot_fixture_mismatch")
    kickoff = _time(fixture["kickoff_at"], "fixture_kickoff")
    as_of = _time(fixture["feature_as_of"], "fixture_feature_as_of")
    snapshot_as_of = _time(integrity["prediction_as_of"], "snapshot_prediction_as_of")
    if as_of != snapshot_as_of or as_of >= kickoff:
        raise IndependentInferenceError("fixture_feature_cutoff_mismatch")

    feature_values = {item["name"]: item["value"]
                      for item in feature_snapshot["features"]}
    missing = sorted(set(FEATURES) - set(feature_values))
    if missing:
        raise IndependentInferenceError(
            "required_model_features_missing:" + ",".join(missing)
        )
    model_features = {name: feature_values[name] for name in FEATURES}

    candidates = {}
    try:
        candidates["results_history_logistic"] = predict_independent_markets(
            model=results_model,
            features=model_features,
            prediction_as_of=as_of.isoformat().replace("+00:00", "Z"),
        )
    except ResultsModelError as exc:
        raise IndependentInferenceError(
            f"results_history_model_rejected:{str(exc)[:120]}"
        ) from None

    if poisson_artifact is not None:
        try:
            candidates["poisson_dixon_coles"] = predict_poisson_dixon_coles(
                artifact=poisson_artifact,
                fixture=fixture,
            )
        except PoissonModelError as exc:
            raise IndependentInferenceError(
                f"poisson_model_rejected:{str(exc)[:120]}"
            ) from None

    return {
        "schema_version": 1,
        "fixture_id": fixture["fixture_id"],
        "competition_key": fixture["competition_key"],
        "kickoff_at": kickoff.isoformat().replace("+00:00", "Z"),
        "prediction_as_of": as_of.isoformat().replace("+00:00", "Z"),
        "feature_snapshot_sha256": integrity["snapshot_sha256"],
        "candidates": candidates,
        "ensemble_status": "not_fitted_no_out_of_fold_weights",
        "publication_allowed": False,
        "value_betting_enabled": False,
        "legacy_model_dependency": False,
        "fallback_prior_used": False,
        "abstention_required_if_any_candidate_rejects": True,
    }
