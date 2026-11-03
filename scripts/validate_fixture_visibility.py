"""Fail-closed validation that every eligible same-day fixture remains visible."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FORECAST_STATUSES = {"EXPERIMENTAL_ONLY", "EXPERIMENTAL_LOW_DATA"}
NON_FORECAST_STATUSES = {
    "INSUFFICIENT_HISTORY", "UNSUPPORTED_COMPETITION", "KICKOFF_UNVERIFIED",
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

    # A cold or stale history cache must not silently publish a mostly empty
    # predictions page when enough provider-attributed results exist for a
    # conservative global prior. Women's/youth/reserve fixtures remain excluded
    # until category-matched history is available.
    coverage = report.get("historical_data_coverage") or {}
    source_counts = coverage.get("recent_cache_source_counts") or {}
    try:
        licensed_global_rows = int(source_counts.get("5DollarFootballAPI", 0))
    except (TypeError, ValueError):
        licensed_global_rows = 0
    non_senior_reason = (
        "women's, youth and reserve competitions require category-matched historical results"
    )
    senior_candidates = [
        row for row in rows
        if str(row.get("status") or "").upper() not in {
            "KICKOFF_UNVERIFIED", "KICKOFF_PASSED", "FIXTURE_NOT_PREMATCH"
        }
        and non_senior_reason not in str(row.get("reason") or "").casefold()
    ]
    forecast_rows = sum(
        str(row.get("status") or "").upper() in FORECAST_STATUSES
        and isinstance(row.get("probabilities"), dict)
        for row in rows
    )
    low_data_forecasts = counts.get("EXPERIMENTAL_LOW_DATA", 0)
    forecast_coverage = (
        forecast_rows / len(senior_candidates) if senior_candidates else 1.0
    )
    if licensed_global_rows >= 30 and senior_candidates and forecast_coverage < 0.90:
        raise ValueError(
            "Forecast coverage gate failed: "
            f"{forecast_rows}/{len(senior_candidates)} senior fixtures have forecasts "
            f"({forecast_coverage:.1%}) despite {licensed_global_rows} licensed provider results; "
            "repair the model fallback before publication."
        )

    result = {
        "status": "PASSED",
        "fixture_rows": len(rows),
        "expected_fixture_rows": expected if expected is not None else len(rows),
        "fixture_status_counts": counts,
        "kickoff_unverified_rows": counts.get("KICKOFF_UNVERIFIED", 0),
        "forecast_rows": forecast_rows,
        "low_data_forecast_rows": low_data_forecasts,
        "senior_forecast_coverage": round(forecast_coverage, 4),
        "licensed_global_history_rows": licensed_global_rows,
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
