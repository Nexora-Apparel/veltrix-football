"""Fetch today's fixtures and write an experimental prediction JSON report."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError
from app.live_predictions import build_daily_report, load_historical_matches
from app.recent_results import fetch_recent_results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="Nigeria-local fixture date YYYY-MM-DD (defaults to today in selected timezone)")
    parser.add_argument("--history", default="data/open_historical_matches.csv")
    parser.add_argument("--output", default="reports/daily_predictions.json")
    parser.add_argument("--timezone", default="Africa/Lagos")
    args = parser.parse_args()
    try:
        target_date = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(args.timezone)).date()
        api = FootballAPI(get_settings())
        payload = api.fixtures(target_date.isoformat(), args.timezone)
        base_history = load_historical_matches(args.history)
        report = build_daily_report(
            payload,
            args.history,
            as_of=target_date,
            timezone_name=args.timezone,
            base_historical_matches=base_history,
        )
        if report["future_fixtures_considered"] > 0:
            recent_rows, recent_sync = fetch_recent_results(
                api, base_history, target_date - timedelta(days=1)
            )
            if recent_rows:
                report = build_daily_report(
                    payload,
                    args.history,
                    as_of=target_date,
                    timezone_name=args.timezone,
                    additional_historical_matches=recent_rows,
                    base_historical_matches=base_history,
                )
        else:
            recent_sync = {
                "status": "SKIPPED_NO_FUTURE_FIXTURES",
                "results_added": 0,
                "requested_start": None,
                "requested_end": (target_date - timedelta(days=1)).isoformat(),
                "covered_from": None,
                "covered_through": report.get("historical_data_through"),
                "ranges_succeeded": 0,
                "warning": None,
            }
        report["recent_results_sync"] = recent_sync
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "date": target_date.isoformat(),
            "fixtures_received": report["fixtures_received"],
            "same_day_pre_match_fixtures": report["same_day_pre_match_fixtures"],
            "future_fixtures_considered": report["future_fixtures_considered"],
            "past_kickoffs_excluded": report["past_kickoffs_excluded"],
            "fixtures_excluded_other_date_or_status": report["fixtures_excluded_other_date_or_status"],
            "predictions_created": report["predictions_created"],
            "insufficient_history": report["insufficient_history"],
            "unsupported_competitions": report.get("unsupported_competitions", 0),
            "unsupported_competition_breakdown": report.get("unsupported_competition_breakdown", {}),
            "possible_team_name_mismatches": report["possible_team_name_mismatches"],
            "historical_data_through": report.get("historical_data_through"),
            "historical_matches_available": report.get("historical_matches_available", 0),
            "recent_results_sync": recent_sync,
            "output": str(output),
            "model_status": report["model_status"],
        }, indent=2))
    except (RuntimeError, ValueError, FootballAPIError, OSError) as exc:
        print(f"DAILY PREDICTION RUN FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
