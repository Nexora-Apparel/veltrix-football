"""Remove already-started fixtures from a saved same-day report before delivery."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

def filter_report_for_delivery(report: dict, now: datetime | None = None) -> dict:
    if not isinstance(report, dict) or report.get("same_day_only") is not True:
        raise ValueError("Refusing to deliver a report that does not enforce same-day fixture filtering.")
    timezone_name = str(report.get("timezone") or "Africa/Lagos")
    zone = ZoneInfo(timezone_name)
    target_day = date.fromisoformat(str(report.get("as_of_date", "")))
    current = now or datetime.now(zone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=zone)
    else:
        current = current.astimezone(zone)
    if current.date() != target_day:
        raise ValueError("Saved report date is not today in the report timezone; refusing stale delivery.")
    rows = report.get("predictions")
    if not isinstance(rows, list):
        raise ValueError("Saved report predictions must be a list.")
    kept = []
    past_rows_excluded = 0
    other_date_rows_excluded = 0
    missing_or_invalid_kickoff_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            missing_or_invalid_kickoff_rows += 1
            continue
        value = row.get("kickoff_local")
        if not value:
            missing_or_invalid_kickoff_rows += 1
            continue
        try:
            kickoff = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            missing_or_invalid_kickoff_rows += 1
            continue
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=zone)
        else:
            kickoff = kickoff.astimezone(zone)
        if kickoff.date() != target_day:
            other_date_rows_excluded += 1
        elif kickoff <= current:
            past_rows_excluded += 1
        else:
            kept.append(row)

    # Recompute every counter that describes the delivered prediction rows.
    # Otherwise the saved JSON can contain 594 rows but stale status counts
    # totaling 614, which makes the command centre appear internally inconsistent.
    experimental = [row for row in kept if row.get("status") == "EXPERIMENTAL_ONLY"]
    insufficient = [row for row in kept if row.get("status") == "INSUFFICIENT_HISTORY"]
    unsupported = [row for row in kept if row.get("status") == "UNSUPPORTED_COMPETITION"]
    result = dict(report)
    result["predictions"] = kept
    result["same_day_pre_match_fixtures"] = len(kept)
    result["future_fixtures_considered"] = len(kept)
    result["predictions_created"] = len(experimental)
    result["insufficient_history"] = len(insufficient)
    result["unsupported_competitions"] = len(unsupported)
    result["unsupported_competition_breakdown"] = {
        str(league_name): sum(row.get("league") == league_name for row in unsupported)
        for league_name in sorted({row.get("league") for row in unsupported if row.get("league")})
    }
    result["possible_team_name_mismatches"] = sum(
        bool(row.get("team_name_match_suggestions")) for row in kept
    )
    result["primary_model_counts"] = {
        str(model_name): sum(row.get("model") == model_name for row in experimental)
        for model_name in sorted({str(row.get("model")) for row in experimental if row.get("model")})
    }
    result["poisson_alternative_available"] = sum(
        isinstance(row.get("poisson_probabilities"), dict) for row in experimental
    )
    result["elo_alternative_available"] = sum(
        isinstance(row.get("elo_probabilities"), dict) for row in experimental
    )
    result["fixtures_with_market_odds"] = sum(
        isinstance(row.get("market_probabilities"), dict) for row in kept
    )
    result["past_kickoffs_excluded"] = int(report.get("past_kickoffs_excluded", 0)) + past_rows_excluded
    result["delivery_filter"] = {
        "applied": True,
        "filtered_at": current.isoformat(),
        "saved_fixture_rows": len(rows),
        "future_same_day_fixture_rows": len(kept),
        "past_kickoffs_excluded": past_rows_excluded,
        "other_date_rows_excluded": other_date_rows_excluded,
        "missing_or_invalid_kickoff_rows_excluded": missing_or_invalid_kickoff_rows,
    }
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        report = json.loads(Path(args.input).read_text(encoding="utf-8"))
        filtered = filter_report_for_delivery(report)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(filtered, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "as_of_date": filtered["as_of_date"],
            "saved_fixture_rows": filtered["delivery_filter"]["saved_fixture_rows"],
            "future_same_day_fixture_rows": filtered["delivery_filter"]["future_same_day_fixture_rows"],
            "usable_forecasts": filtered["predictions_created"],
            "delivery_filter": "APPLIED",
        }, indent=2))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"REPORT FILTER FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

if __name__ == "__main__":
    main()
