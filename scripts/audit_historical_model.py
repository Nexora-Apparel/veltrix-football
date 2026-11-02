"""Reconstruct and compare archived daily 1X2 forecasts against saved completed results.

This audit makes no provider requests. It uses an archived prediction report and the
published resumable results cache, matches by exact local date/team identity, and
scores primary, Poisson, Elo and Dixon-Coles probabilities on identical fixtures.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.live_predictions import _name_key
from app.market_evidence import probability_distribution_audit


def _probabilities(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    aliases = {
        "H": ("H", "home_win", "home"),
        "D": ("D", "draw"),
        "A": ("A", "away_win", "away"),
    }
    result: dict[str, float] = {}
    for outcome, keys in aliases.items():
        raw = next((value[key] for key in keys if key in value), None)
        if isinstance(raw, bool):
            return None
        try:
            number = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number < 0 or number > 1:
            return None
        result[outcome] = number
    total = sum(result.values())
    if not 0.98 <= total <= 1.02:
        return None
    return {key: value / total for key, value in result.items()}


def _result(home_goals: Any, away_goals: Any) -> str | None:
    try:
        home, away = int(home_goals), int(away_goals)
    except (TypeError, ValueError, OverflowError):
        return None
    if home < 0 or away < 0:
        return None
    return "H" if home > away else "A" if away > home else "D"


def _date_key(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def _metric(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"matches": 0, "accuracy": None, "brier_score": None, "log_loss": None}
    accuracy = 0
    brier = 0.0
    log_loss = 0.0
    for row in rows:
        probs, actual = row["probabilities"], row["actual"]
        accuracy += int(max(probs, key=probs.get) == actual)
        brier += sum((probs[key] - float(key == actual)) ** 2 for key in ("H", "D", "A"))
        log_loss -= math.log(max(1e-15, probs[actual]))
    count = len(rows)
    return {
        "matches": count,
        "accuracy": accuracy / count,
        "brier_score": brier / count,
        "log_loss": log_loss / count,
    }


def audit_report(report: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report.get("predictions"), list) or not report.get("same_day_only"):
        raise ValueError("Archived report must contain predictions and enforce same-day filtering.")
    if not isinstance(cache.get("matches"), list):
        raise ValueError("Recent-results cache is missing its matches list.")

    report_date = _date_key(report.get("as_of_date"))
    generated_at = None
    try:
        generated_at = datetime.fromisoformat(str(report.get("generated_at_utc")).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        pass

    results: dict[tuple[str, str, str], dict[str, Any]] = {}
    duplicate_results = 0
    for item in cache["matches"]:
        if not isinstance(item, dict):
            continue
        day = _date_key(item.get("date"))
        home, away = _name_key(item.get("home")), _name_key(item.get("away"))
        actual = _result(item.get("home_goals"), item.get("away_goals"))
        if not day or not home or not away or not actual:
            continue
        key = (day, home, away)
        if key in results:
            duplicate_results += 1
            continue
        results[key] = {
            "actual": actual,
            "source_provider": item.get("source_provider") or "UNATTRIBUTED",
            "home_goals": int(item["home_goals"]),
            "away_goals": int(item["away_goals"]),
        }

    status_counts = Counter()
    primary_counts = Counter()
    competition_counts = Counter()
    matched_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmatched = []
    excluded_non_chronological = 0
    matched_by_provider = Counter()
    fixture_details: dict[tuple[str, str, str], dict[str, Any]] = {}

    for item in report["predictions"]:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "UNKNOWN")
        status_counts[status] += 1
        if status != "EXPERIMENTAL_ONLY":
            continue
        primary_model = str(item.get("model") or "UNKNOWN")
        primary_counts[primary_model] += 1
        competition_counts[str(item.get("division_code") or "UNMAPPED")] += 1
        kickoff = item.get("kickoff") or item.get("kickoff_local")
        try:
            kickoff_dt = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            kickoff_dt = None
        if generated_at is not None and kickoff_dt is not None:
            if kickoff_dt.tzinfo is None:
                kickoff_dt = kickoff_dt.replace(tzinfo=generated_at.tzinfo)
            if generated_at >= kickoff_dt:
                excluded_non_chronological += 1
                continue

        day = _date_key(item.get("kickoff_local") or item.get("kickoff"))
        key = (day or "", _name_key(item.get("home_team")), _name_key(item.get("away_team")))
        result = results.get(key)
        if result is None:
            unmatched.append({
                "fixture_id": item.get("fixture_id"),
                "date": day,
                "home_team": item.get("home_team"),
                "away_team": item.get("away_team"),
                "reason": "NO_EXACT_DATE_AND_TEAM_RESULT_MATCH",
            })
            continue
        matched_by_provider[str(result["source_provider"])] += 1
        detail = fixture_details.setdefault(key, {
            "date": key[0],
            "home_team": item.get("home_team"),
            "away_team": item.get("away_team"),
            "actual_result": result["actual"],
            "home_goals": result["home_goals"],
            "away_goals": result["away_goals"],
            "result_source_provider": result["source_provider"],
            "fixture_ids": [],
            "models": {},
        })
        if item.get("fixture_id") is not None and item.get("fixture_id") not in detail["fixture_ids"]:
            detail["fixture_ids"].append(item.get("fixture_id"))

        model_probabilities: dict[str, dict[str, float]] = {}
        primary = _probabilities(item.get("probabilities"))
        if primary:
            model_probabilities[primary_model] = primary
        if primary_model == "experimental_recent_goals_poisson":
            poisson = primary
        else:
            poisson = _probabilities(item.get("poisson_probabilities"))
        if poisson:
            model_probabilities["experimental_recent_goals_poisson"] = poisson
        if primary_model == "experimental_elo_by_competition":
            elo = primary
        else:
            elo = _probabilities(item.get("elo_probabilities"))
        if elo:
            model_probabilities["experimental_elo_by_competition"] = elo
        advanced = item.get("advanced_model_alternative")
        dixon = _probabilities(advanced.get("probabilities")) if isinstance(advanced, dict) else None
        if dixon:
            model_probabilities["experimental_recency_weighted_dixon_coles"] = dixon

        for model, probabilities in model_probabilities.items():
            detail["models"][model] = {
                "probabilities": probabilities,
                "predicted_result": max(probabilities, key=probabilities.get),
                "correct": max(probabilities, key=probabilities.get) == result["actual"],
            }
            matched_rows[model].append({
                "fixture_key": key,
                "fixture_id": item.get("fixture_id"),
                "home_team": item.get("home_team"),
                "away_team": item.get("away_team"),
                "actual": result["actual"],
                "probabilities": probabilities,
                "source_provider": result["source_provider"],
            })

    model_metrics = {model: _metric(rows) for model, rows in sorted(matched_rows.items())}\n    class_distribution_by_model = {\n        model: probability_distribution_audit(rows)\n        for model, rows in sorted(matched_rows.items())\n    }
    model_sets = {
        model: {row["fixture_key"] for row in rows}
        for model, rows in matched_rows.items()
    }
    common = set.intersection(*model_sets.values()) if len(model_sets) >= 2 else set()
    common_metrics = {}
    for model, rows in matched_rows.items():
        common_metrics[model] = _metric([row for row in rows if row["fixture_key"] in common])

    eligible = status_counts.get("EXPERIMENTAL_ONLY", 0)
    total = sum(status_counts.values())
    return {
        "audit_version": 1,
        "report_date": report_date,
        "generated_at_utc": report.get("generated_at_utc"),
        "historical_data_through": report.get("historical_data_through"),
        "fixtures_in_report": total,
        "forecast_eligible": eligible,
        "forecast_coverage": eligible / total if total else None,
        "status_counts": dict(status_counts),
        "primary_model_counts": dict(primary_counts),
        "eligible_competition_mapping": dict(competition_counts),
        "completed_results_cache_rows": len(cache["matches"]),
        "unique_valid_result_identities": len(results),
        "duplicate_result_identities_ignored": duplicate_results,
        "matched_forecast_fixtures": len({row["fixture_key"] for rows in matched_rows.values() for row in rows}),
        "unmatched_forecast_fixtures": len(unmatched),
        "excluded_non_chronological": excluded_non_chronological,
        "matched_result_sources": dict(matched_by_provider),
        "result_provenance_verified": bool(matched_by_provider) and all(source != "LEGACY_UNATTRIBUTED" for source in matched_by_provider),
        "result_provenance_warning": (
            "Matched results include legacy rows with no recorded source provider; treat all retrospective scores as provisional."
            if any(source == "LEGACY_UNATTRIBUTED" for source in matched_by_provider)
            else None
        ),
        "metrics_by_model_all_available_matches": model_metrics,\n        "class_distribution_diagnostics_by_model": class_distribution_by_model,
        "common_fixture_count_for_model_comparison": len(common),
        "metrics_by_model_on_common_fixtures": common_metrics,
        "match_basis": "exact_Africa_Lagos_date_and_normalized_home_away_team_identity",
        "matched_fixture_details": [fixture_details[key] for key in sorted(fixture_details)],
        "unmatched_examples": unmatched[:50],
        "interpretation": (
            "Descriptive retrospective audit only. It does not validate betting profitability. "
            "Compare model metrics only on the common-fixture set; small samples and incomplete "
            "result-cache coverage must not be treated as proof of model quality."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Archived daily_predictions.json")
    parser.add_argument("--cache", required=True, help="Published recent_results_cache.json")
    parser.add_argument("--output", default="reports/historical_model_audit.json")
    args = parser.parse_args()
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    cache = json.loads(Path(args.cache).read_text(encoding="utf-8"))
    result = audit_report(report, cache)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "unmatched_examples"}, indent=2))
    print(f"Audit saved: {output}")


if __name__ == "__main__":
    main()
