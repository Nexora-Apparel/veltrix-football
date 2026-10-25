"""Remove already-started fixtures from a saved same-day report before delivery."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.live_predictions import _name_key, _one_edit_apart, _team_variant_signature

def _has_unsafe_auto_team_match(row: dict) -> bool:
    """Reject legacy fuzzy matches that violate the current conservative identity rules."""
    matches = row.get("team_name_matches") or {}
    if not isinstance(matches, dict):
        return False
    for side in matches.values():
        if not isinstance(side, dict) or side.get("auto_matched") is not True:
            continue
        fixture_key = _name_key(side.get("fixture_name"))
        historical_key = str(side.get("historical_key") or "")
        if (
            not historical_key
            or _team_variant_signature(fixture_key) != _team_variant_signature(historical_key)
            or not _one_edit_apart(fixture_key, historical_key)
        ):
            return True
    return False


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
    unsafe_team_identity_rows_withheld = 0
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
            delivered_row = row
            if row.get("status") == "EXPERIMENTAL_ONLY" and _has_unsafe_auto_team_match(row):
                delivered_row = dict(row)
                delivered_row["status"] = "INSUFFICIENT_HISTORY"
                delivered_row["reason"] = (
                    "Forecast withheld because the saved report used an unsafe fuzzy team-name match."
                )
                delivered_row["team_identity_withheld"] = True
                unsafe_team_identity_rows_withheld += 1
            kept.append(delivered_row)

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
        bool(row.get("team_name_match_suggestions"))
        or any(
            bool(side.get("auto_matched"))
            for side in (row.get("team_name_matches") or {}).values()
            if isinstance(side, dict)
        )
        for row in kept
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
        "unsafe_team_identity_rows_withheld": unsafe_team_identity_rows_withheld,
    }
    # This script is used only by the quota-safe reuse path. Mark the snapshot so
    # consumers cannot mistake a filtered older report for a fresh live fetch.
    result["publication_status"] = "REUSED_SNAPSHOT_NOT_REFRESHED"
    result["publication_notice"] = (
        "A saved same-day snapshot was reused because a new live report was unavailable; "
        "this run did not fetch fresh fixtures."
    )
    if not isinstance(result.get("historical_data_coverage"), dict):
        sync = result.get("recent_results_sync") or {}
        requested_start = sync.get("requested_start") if isinstance(sync, dict) else None
        base_through = None
        if requested_start:
            try:
                base_through = (date.fromisoformat(str(requested_start)) - __import__("datetime").timedelta(days=1)).isoformat()
            except ValueError:
                base_through = None
        result["historical_data_coverage"] = {
            "status": "GAPPED_OR_STALE",
            "base_history_through": base_through,
            "contiguous_through": base_through,
            "latest_available_match_date": result.get("historical_data_through") or (sync.get("covered_through") if isinstance(sync, dict) else None),
            "refresh_status": str(sync.get("status") or "UNKNOWN") if isinstance(sync, dict) else "UNKNOWN",
            "requested_start": requested_start,
            "requested_end": sync.get("requested_end") if isinstance(sync, dict) else None,
            "covered_from": sync.get("covered_from") if isinstance(sync, dict) else None,
            "covered_through": sync.get("covered_through") if isinstance(sync, dict) else None,
            "ranges_succeeded": sync.get("ranges_succeeded") if isinstance(sync, dict) else None,
            "ranges_requested": sync.get("ranges_requested") if isinstance(sync, dict) else None,
            "backfill_complete": False,
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
