"""Fetch today's fixtures, refresh completed results, and write an experimental report."""
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
from app.live_odds import extract_market_probabilities


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="Fixture date YYYY-MM-DD in the selected timezone (defaults to today)")
    parser.add_argument("--history", default="data/open_historical_matches.csv")
    parser.add_argument("--output", default="reports/daily_predictions.json")
    parser.add_argument("--timezone", default="Africa/Lagos")
    args = parser.parse_args()
    try:
        target_date = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(args.timezone)).date()
        api = FootballAPI(get_settings())
        payload = api.fixtures(target_date.isoformat(), args.timezone)
        base_history = load_historical_matches(args.history)

        # Historical results must refresh even when the target day's matches have
        # already kicked off. Otherwise late-day runs can leave model history stale.
        recent_rows, recent_sync = fetch_recent_results(
            api, base_history, target_date - timedelta(days=1), timezone_name=args.timezone
        )

        market_odds_by_fixture = {}
        # Odds are only useful for fixtures that have not kicked off yet.
        if _has_future_fixtures(payload, target_date, args.timezone):
            try:
                odds_payload = api.odds_for_date(target_date.isoformat(), args.timezone)
                market_odds_by_fixture = extract_market_probabilities(odds_payload)
                odds_sync = {
                    "status": "AVAILABLE" if market_odds_by_fixture else "NO_VALID_1X2_ODDS",
                    "fixtures_with_odds": len(market_odds_by_fixture),
                    "snapshot_date": target_date.isoformat(),
                    "warning": None,
                }
            except (FootballAPIError, ValueError) as exc:
                odds_sync = {
                    "status": "UNAVAILABLE",
                    "fixtures_with_odds": 0,
                    "snapshot_date": target_date.isoformat(),
                    "warning": str(exc),
                }
        else:
            odds_sync = {
                "status": "SKIPPED_NO_FUTURE_FIXTURES",
                "fixtures_with_odds": 0,
                "snapshot_date": target_date.isoformat(),
                "warning": None,
            }

        report = build_daily_report(
            payload,
            args.history,
            as_of=target_date,
            timezone_name=args.timezone,
            additional_historical_matches=recent_rows,
            base_historical_matches=base_history,
            market_odds_by_fixture=market_odds_by_fixture,
        )
        report["recent_results_sync"] = recent_sync
        report["live_odds_sync"] = odds_sync
        report["fixtures_with_market_odds"] = sum(
            isinstance(item.get("market_probabilities"), dict)
            for item in report.get("predictions", [])
        )
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
            "live_odds_sync": odds_sync,
            "fixtures_with_market_odds": report["fixtures_with_market_odds"],
            "output": str(output),
            "model_status": report["model_status"],
        }, indent=2))
    except (RuntimeError, ValueError, FootballAPIError, OSError) as exc:
        print(f"DAILY PREDICTION RUN FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _has_future_fixtures(payload: dict, target_date: date, timezone_name: str) -> bool:
    """Return whether the payload contains a same-local-day fixture still to start."""
    from app.live_predictions import _fixture_parts
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(timezone_name))
    response = payload.get("response")
    if not isinstance(response, list):
        return False
    return any(
        (part := _fixture_parts(item, timezone_name))
        and part["kickoff_date"] == target_date
        and part["kickoff_datetime"] > now
        for item in response
    )


if __name__ == "__main__":
    main()
