"""Publish reproducible chronological model-validation evidence to command-data."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.publish_command_data import publish


def _require_object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object.")
    return value


def build_summary(backtest: dict, coverage: dict, generated_at: str | None = None) -> dict:
    """Create a compact, auditable verdict without promoting diagnostic passes to certification."""
    provenance = _require_object(backtest.get("dataset_provenance"), "dataset_provenance")
    if provenance.get("sha256") != coverage.get("sha256"):
        raise ValueError("Backtest and coverage audit dataset fingerprints do not match.")
    if int(provenance.get("rows_loaded") or 0) != int(coverage.get("valid_rows") or 0):
        raise ValueError("Backtest and coverage audit row counts do not match.")

    models = _require_object(backtest.get("models"), "models")
    odds = _require_object(backtest.get("historical_odds_subset"), "historical_odds_subset")
    compared = _require_object(odds.get("models_compared_on_same_matches"), "same_match_comparison")
    market = _require_object(compared.get("market"), "market benchmark")
    elo = _require_object(models.get("elo"), "Elo metrics")
    poisson = _require_object(models.get("poisson"), "Poisson metrics")
    same_elo = _require_object(compared.get("elo"), "same-fixture Elo metrics")
    same_poisson = _require_object(compared.get("poisson"), "same-fixture Poisson metrics")

    live = _require_object(backtest.get("live_pipeline"), "live_pipeline")
    one_x_two = _require_object(live.get("one_x_two_calibration"), "one_x_two_calibration")
    goal = _require_object(live.get("goal_markets"), "live goal_markets")
    rolling_goal = _require_object(goal.get("rolling_origin_calibration"), "goal rolling calibration")

    market_outperforms = all(
        market.get(metric) is not None
        and same_elo.get(metric) is not None
        and same_poisson.get(metric) is not None
        and market[metric] < same_elo[metric]
        and market[metric] < same_poisson[metric]
        for metric in ("brier_score", "log_loss")
    )

    goal_markets = {}
    for name, result in _require_object(rolling_goal.get("markets"), "goal market diagnostics").items():
        if not isinstance(result, dict):
            continue
        goal_markets[name] = {
            "status": result.get("status", "NOT_EVALUATED"),
            "folds_evaluated": result.get("folds_evaluated", 0),
            "folds_beating_raw_and_baseline": result.get("folds_beating_raw_and_baseline", 0),
            "raw": result.get("raw"),
            "calibrated": result.get("calibrated"),
            "expanding_baseline": result.get("expanding_baseline"),
            "diagnostic_only": True,
            "applied_to_production": False,
            "betting_certification": False,
        }

    def compact_metrics(value: Any) -> dict | None:
        if not isinstance(value, dict):
            return None
        return {k: value.get(k) for k in (
            "matches", "result_accuracy", "accuracy", "brier_score", "log_loss",
            "precision", "recall", "predicted_class_counts", "actual_class_counts",
            "class_precision_recall",
        ) if k in value}

    outcome_balance = {}
    for name, audit in _require_object(live.get("outcome_balance_audit", {}), "outcome_balance_audit").items():
        if not isinstance(audit, dict):
            continue
        outcome_balance[name] = {
            "status": audit.get("status"),
            "matches": audit.get("matches"),
            "home_bias_flag": audit.get("home_bias_flag"),
            "probability_mass_status": audit.get("probability_mass_status"),
            "maximum_probability_mass_gap_percentage_points": audit.get("maximum_probability_mass_gap_percentage_points"),
            "note": audit.get("note"),
            "classes": {
                cls: {k: stats.get(k) for k in (
                    "actual_matches", "predicted_matches", "actual_share", "predicted_share",
                    "prediction_share_gap_percentage_points", "precision", "recall",
                    "mean_predicted_probability", "observed_frequency",
                    "probability_minus_observed_percentage_points",
                )}
                for cls, stats in (audit.get("classes") or {}).items()
                if isinstance(stats, dict)
            },
        }

    confidence_selection = {}
    for name, audit in _require_object(live.get("confidence_selection_audit", {}), "confidence_selection_audit").items():
        if not isinstance(audit, dict):
            continue
        confidence_selection[name] = {
            "status": audit.get("status"),
            "total_matches": audit.get("total_matches"),
            "thresholds": [{
                k: row.get(k) for k in (
                    "minimum_top_probability", "selected_matches", "coverage", "accuracy",
                    "mean_top_probability", "predicted_class_counts",
                )
            } for row in audit.get("thresholds", []) if isinstance(row, dict)],
            "note": audit.get("note"),
        }

    favourite_underdog = {}
    for name, audit in _require_object(live.get("favourite_underdog_audit", {}), "favourite_underdog_audit").items():
        if not isinstance(audit, dict) or name == "note":
            continue
        favourite_underdog[name] = {
            "status": audit.get("status"),
            "overall": compact_metrics(audit.get("overall")),
            "favourite_wins": compact_metrics(audit.get("favourite_wins")),
            "underdog_wins": compact_metrics(audit.get("underdog_wins")),
            "matches_with_market_classification": audit.get("matches_with_market_classification"),
            "mean_model_probability_assigned_to_market_favourite": audit.get("mean_model_probability_assigned_to_market_favourite"),
            "mean_model_probability_assigned_to_market_underdog": audit.get("mean_model_probability_assigned_to_market_underdog"),
            "important_note": audit.get("important_note"),
        }

    draw_margin = {}
    for name, experiment in _require_object(live.get("draw_margin_experiment", {}), "draw_margin_experiment").items():
        if not isinstance(experiment, dict) or name == "note":
            continue
        draw_margin[name] = {
            "status": experiment.get("status"),
            "calibration_cutoff_date": experiment.get("calibration_cutoff_date"),
            "calibration_matches": experiment.get("calibration_matches"),
            "holdout_matches": experiment.get("holdout_matches"),
            "selected_draw_margin": experiment.get("selected_draw_margin"),
            "raw_argmax_holdout": {
                **(compact_metrics(experiment.get("raw_argmax_holdout")) or {}),
                "predicted_class_counts": (experiment.get("raw_argmax_holdout") or {}).get("predicted_class_counts"),
            },
            "draw_margin_holdout": {
                **(compact_metrics(experiment.get("draw_margin_holdout")) or {}),
                "predicted_class_counts": (experiment.get("draw_margin_holdout") or {}).get("predicted_class_counts"),
            },
            "holdout_accuracy_delta": experiment.get("holdout_accuracy_delta"),
            "improved_unseen_holdout_accuracy": experiment.get("improved_unseen_holdout_accuracy"),
            "note": experiment.get("note"),
        }

    metrics_by_competition = {}
    for competition, stats in _require_object(live.get("metrics_by_competition", {}), "metrics_by_competition").items():
        if not isinstance(stats, dict):
            continue
        metrics_by_competition[competition] = {
            "live_eligible_matches": stats.get("live_eligible_matches"),
            "poisson": compact_metrics(stats.get("poisson")),
            "elo": compact_metrics(stats.get("elo")),
            "historical_odds_matches": stats.get("historical_odds_matches"),
            "poisson_market_comparison": {
                "model": compact_metrics((stats.get("same_match_market_comparison") or {}).get("poisson")),
                "market": compact_metrics((stats.get("same_match_market_comparison") or {}).get("market")),
            },
            "elo_market_comparison": {
                "model": compact_metrics((stats.get("elo_same_match_market_comparison") or {}).get("elo")),
                "market": compact_metrics((stats.get("elo_same_match_market_comparison") or {}).get("market")),
            },
        }

    recent_holdout = _require_object(live.get("recent_holdout", {}), "recent_holdout")
    recent_holdout_summary = {
        "method": recent_holdout.get("method"),
        "start_date": recent_holdout.get("start_date"),
        "end_date": recent_holdout.get("end_date"),
        "matches": recent_holdout.get("matches"),
        "metrics": compact_metrics(recent_holdout.get("metrics")),
        "dixon_coles_alternative": compact_metrics((recent_holdout.get("dixon_coles_alternative") or {}).get("metrics")),
        "elo_alternative": compact_metrics((recent_holdout.get("elo_alternative") or {}).get("metrics")),
    }
    dixon = _require_object(live.get("dixon_coles_alternative", {}), "dixon_coles_alternative")
    elo_alternative = _require_object(live.get("elo_alternative", {}), "elo_alternative")

    one_x_two_models = {}
    for name, result in one_x_two.items():
        if name == "note" or not isinstance(result, dict):
            continue
        one_x_two_models[name] = {
            "status": result.get("status"),
            "folds_requested": result.get("folds_requested"),
            "folds_evaluated": result.get("folds_evaluated"),
            "raw": result.get("raw"),
            "calibrated": result.get("calibrated"),
            "market_on_same_odds_covered_fixtures": result.get("market_on_same_odds_covered_fixtures"),
            "beats_market_on_same_fixtures": result.get("beats_market_on_same_fixtures"),
            "market_anchor_blend_beats_market": result.get("market_anchor_blend_beats_market"),
            "calibration_diagnostic_pass": result.get("calibration_diagnostic_pass"),
            "diagnostic_only": True,
            "applied_to_production": False,
        }

    return {
        "schema_version": 1,
        "product": "VELTRIX FOOTBALL AI",
        "generated_at_utc": generated_at or datetime.now(timezone.utc).isoformat(),
        "status": "RESEARCH_DIAGNOSTIC_ONLY",
        "dataset": {
            **provenance,
            "audit_rows": coverage.get("rows"),
            "valid_rows": coverage.get("valid_rows"),
            "invalid_rows": coverage.get("invalid_rows"),
            "duplicate_match_keys": coverage.get("duplicate_match_keys"),
            "competition_count": coverage.get("competition_count"),
            "integrity_status": "PASS" if coverage.get("invalid_rows") == 0 and coverage.get("duplicate_match_keys") == 0 else "REVIEW_REQUIRED",
            "missingness": coverage.get("missing_values"),
        },
        "historical_1x2": {
            "test_matches": backtest.get("test_matches"),
            "first_test_date": backtest.get("first_test_date"),
            "last_test_date": backtest.get("last_test_date"),
            "full_sample_models": {
                "poisson": {k: poisson.get(k) for k in ("matches", "result_accuracy", "brier_score", "log_loss")},
                "elo": {k: elo.get(k) for k in ("matches", "result_accuracy", "brier_score", "log_loss")},
            },
            "market_comparison_same_fixtures": {
                "poisson": {k: same_poisson.get(k) for k in ("matches", "result_accuracy", "brier_score", "log_loss")},
                "elo": {k: same_elo.get(k) for k in ("matches", "result_accuracy", "brier_score", "log_loss")},
                "market": {k: market.get(k) for k in ("matches", "result_accuracy", "brier_score", "log_loss")},
            },
            "market_outperforms_both_on_brier_and_log_loss": market_outperforms,
            "release_status": "NOT_CERTIFIED_MARKET_OUTPERFORMED_MODELS" if market_outperforms else "NOT_CERTIFIED",
        },
        "rolling_origin_1x2_calibration": one_x_two_models,
        "recent_holdout": recent_holdout_summary,
        "alternative_models": {
            "dixon_coles": {
                "model": dixon.get("model"),
                "rho": dixon.get("rho"),
                "metrics": compact_metrics(dixon.get("metrics")),
                "model_validated": dixon.get("model_validated"),
                "production_applied": False,
            },
            "elo_alternative": {
                "model": elo_alternative.get("model"),
                "matches": elo_alternative.get("matches"),
                "metrics": compact_metrics(elo_alternative.get("metrics")),
                "production_applied": False,
            },
        },
        "class_balance_audit": outcome_balance,
        "confidence_selection_audit": confidence_selection,
        "favourite_underdog_audit": favourite_underdog,
        "draw_margin_experiment": {
            "models": draw_margin,
            "note": "Decision-only experiment; no draw-margin adjustment is applied to production probabilities.",
        },
        "metrics_by_competition": metrics_by_competition,
        "rolling_origin_goal_market_calibration": {
            "folds_requested": rolling_goal.get("folds_requested"),
            "folds_evaluated": rolling_goal.get("folds_evaluated"),
            "markets": goal_markets,
            "all_goal_markets_calibration_pass": rolling_goal.get("all_goal_markets_calibration_pass"),
            "diagnostic_only": True,
            "applied_to_production": False,
            "betting_certification": False,
        },
        "release_controls": {
            "value_betting": "LOCKED_INSUFFICIENT_EVIDENCE",
            "alerts_enabled": False,
            "calibration_changes_applied_to_live": False,
            "reason": "Chronological calibration diagnostics are not proof of market-beating skill, positive ROI, or prospective validation.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backtest", required=True)
    parser.add_argument("--coverage", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    backtest = json.loads(Path(args.backtest).read_text(encoding="utf-8"))
    coverage = json.loads(Path(args.coverage).read_text(encoding="utf-8"))
    summary = build_summary(backtest, coverage)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if not repo or not token:
        raise RuntimeError("GitHub publication context is missing.")
    publish("public-data/model_validation_report.json", output, repo, token)
    publish("public-data/historical_coverage_audit.json", Path(args.coverage), repo, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
