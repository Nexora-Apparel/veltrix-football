"""Fail-closed validation that every eligible same-day fixture remains visible."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FORECAST_STATUSES = {"EXPERIMENTAL_ONLY", "LOW_HISTORY_FORECAST"}
NON_FORECAST_STATUSES = {
    "INSUFFICIENT_HISTORY", "EXPERIMENTAL_LOW_DATA", "UNSUPPORTED_COMPETITION", "KICKOFF_UNVERIFIED",
    "KICKOFF_PASSED", "FIXTURE_NOT_PREMATCH",
}


def validate_fixture_visibility(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("same_day_only") is not True:
        raise ValueError("Fixture visibility validation requires a same-day-only report.")
    rows = report.get("predictions")
    if not isinstance(rows, list):
        raise ValueError("Report predictions must be a list.")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("A fixture row is malformed; refusing silent fixture loss.")
    expected = report.get("same_day_fixtures_retained", report.get("future_fixtures_considered"))
    if expected is not None and int(expected) != len(rows):
        raise ValueError(
            f"Fixture visibility mismatch: report says {expected} eligible rows, but contains {len(rows)}."
        )
    for index, row in enumerate(rows):
        if not str(row.get("home_team") or "").strip() or not str(row.get("away_team") or "").strip():
            raise ValueError(f"Fixture row {index} is missing a home or away team identity.")
        status = str(row.get("status") or "").upper()
        if status in NON_FORECAST_STATUSES and isinstance(row.get("probabilities"), dict):
            raise ValueError(f"Non-forecast fixture row {index} unexpectedly contains probabilities.")
        if status in FORECAST_STATUSES and not isinstance(row.get("probabilities"), dict):
            raise ValueError(f"Forecast fixture row {index} has no probability distribution.")
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "UNKNOWN").upper()
        counts[status] = counts.get(status, 0) + 1

    # Adaptive low-history forecasts are explicitly counted and carry an evidence grade.
    # They remain separate from full-history forecasts in coverage reporting.
    coverage = report.get("historical_data_coverage") or {}
    source_counts = coverage.get("recent_cache_source_counts") or {}
    try:
        licensed_global_rows = int(source_counts.get("5DollarFootballAPI", 0))
    except (TypeError, ValueError):
        licensed_global_rows = 0
    senior_candidates = [
        row for row in rows
        if str(row.get("status") or "").upper() not in {
            "KICKOFF_UNVERIFIED", "KICKOFF_PASSED", "FIXTURE_NOT_PREMATCH"
        }
        and row.get("evidence_scope") != "CATEGORY_NEUTRAL_PRIOR"
        and "women's, youth and reserve competitions require category-matched historical results"
        not in str(row.get("reason") or "").casefold()
    ]
    is_forecast = lambda row: (
        str(row.get("status") or "").upper() in FORECAST_STATUSES
        and isinstance(row.get("probabilities"), dict)
    )
    forecast_rows = sum(is_forecast(row) for row in rows)
    # Senior coverage must use the same category-scoped population for both
    # numerator and denominator. Category-neutral forecasts remain visible and
    # count toward all-fixture coverage, but never inflate senior coverage.
    senior_forecast_rows = sum(is_forecast(row) for row in senior_candidates)
    low_data_forecasts = counts.get("LOW_HISTORY_FORECAST", 0)
    insufficient_history_rows = counts.get("INSUFFICIENT_HISTORY", 0)
    forecast_coverage = senior_forecast_rows / len(senior_candidates) if senior_candidates else 1.0
    result = {
        "status": "PASSED",
        "fixture_rows": len(rows),
        "expected_fixture_rows": expected if expected is not None else len(rows),
        "fixture_status_counts": counts,
        "kickoff_unverified_rows": counts.get("KICKOFF_UNVERIFIED", 0),
        "forecast_rows": forecast_rows,
        "senior_forecast_rows": senior_forecast_rows,
        "low_data_forecast_rows": low_data_forecasts,
        "insufficient_history_rows": insufficient_history_rows,
        "senior_forecast_coverage": round(forecast_coverage, 4),
        "licensed_global_history_rows_diagnostic_only": licensed_global_rows,
        "alerts_enabled": False,
    }
    report["fixture_visibility_validation"] = result
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    path = Path(args.report)
    report = json.loads(path.read_text(encoding="utf-8"))
    result = validate_fixture_visibility(report)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
