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

    live = _require_object(backtest.get("live_pipeline"), "live_pipeline")
    one_x_two = _require_object(live.get("one_x_two_calibration"), "one_x_two_calibration")
    goal = _require_object(live.get("goal_markets"), "live goal_markets")
    rolling_goal = _require_object(goal.get("rolling_origin_calibration"), "goal rolling calibration")

    market_outperforms = all(
        market.get(metric) is not None
        and elo.get(metric) is not None
        and poisson.get(metric) is not None
        and market[metric] < elo[metric]
        and market[metric] < poisson[metric]
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
            "models": {
                "poisson": {k: poisson.get(k) for k in ("matches", "result_accuracy", "brier_score", "log_loss")},
                "elo": {k: elo.get(k) for k in ("matches", "result_accuracy", "brier_score", "log_loss")},
                "market_same_fixtures": {k: market.get(k) for k in ("matches", "result_accuracy", "brier_score", "log_loss")},
            },
            "market_outperforms_both_on_brier_and_log_loss": market_outperforms,
            "release_status": "NOT_CERTIFIED_MARKET_OUTPERFORMED_MODELS" if market_outperforms else "NOT_CERTIFIED",
        },
        "rolling_origin_1x2_calibration": one_x_two_models,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
