"""Fail-closed validation that every eligible same-day fixture remains visible."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


FORECAST_STATUSES = {"EXPERIMENTAL_ONLY"}
NON_FORECAST_STATUSES = {
    "INSUFFICIENT_HISTORY", "UNSUPPORTED_COMPETITION", "KICKOFF_UNVERIFIED",
}


def validate_fixture_visibility(report: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(report, dict) or report.get("same_day_only") is not True:
        raise ValueError("Fixture visibility validation requires a same-day-only report.")
    rows = report.get("predictions")
    if not isinstance(rows, list):
        raise ValueError("Report predictions must be a list.")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("A fixture row is malformed; refusing silent fixture loss.")
    expected = report.get("future_fixtures_considered")
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
    result = {
        "status": "PASSED",
        "fixture_rows": len(rows),
        "expected_fixture_rows": expected if expected is not None else len(rows),
        "fixture_status_counts": counts,
        "kickoff_unverified_rows": counts.get("KICKOFF_UNVERIFIED", 0),
        "forecast_rows": counts.get("EXPERIMENTAL_ONLY", 0),
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
