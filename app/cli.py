from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.historical_data import add_leakage_safe_rolling_features, completed_fixture_rows, validate_date_range, write_csv
from app.provider_adapters import FiveDollarFootballClient, ProviderAPIError


def print_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def main():
    parser = argparse.ArgumentParser(description="Veltrix Football multi-source diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Verify primary 5DollarFootballAPI account status")
    sub.add_parser("api-football-status", help="Disabled legacy command; API-Football/API-Sports is suspended")
    odds_parser = sub.add_parser("odds", help="Inspect real BTTS and Over/Under prices from 5DollarFootballAPI")
    odds_parser.add_argument("--date", required=True, help="Fixture date YYYY-MM-DD")
    odds_parser.add_argument("--timezone", default="Africa/Lagos")
    odds_parser.add_argument("--limit", type=int, default=15)
    fixture_parser = sub.add_parser("fixtures", help="Fetch fixtures from 5DollarFootballAPI")
    fixture_parser.add_argument("--date", default=None)
    fixture_parser.add_argument("--timezone", default="Africa/Lagos")
    history_parser = sub.add_parser("history", help="Export completed fixtures and leakage-safe rolling features")
    history_parser.add_argument("--from", dest="start_date", required=True, help="Start date YYYY-MM-DD")
    history_parser.add_argument("--to", dest="end_date", required=True, help="End date YYYY-MM-DD; max seven calendar days")
    history_parser.add_argument("--output", default="data/historical_features.csv")
    history_parser.add_argument("--window", type=int, default=5)
    history_parser.add_argument("--timezone", default="Africa/Lagos")
    league_parser = sub.add_parser("leagues", help="List a page of competitions from 5DollarFootballAPI")
    league_parser.add_argument("--page", type=int, default=1)
    league_parser.add_argument("--per-page", type=int, default=100)

    args = parser.parse_args()
    if args.command == "api-football-status":
        print_json({
            "provider": "API-Football / API-Sports",
            "status": "DISABLED_SUSPENDED",
            "message": "This legacy command makes no network request. Veltrix production uses 5DollarFootballAPI.",
        })
        return

    try:
        client = FiveDollarFootballClient()
        if not client.api_key:
            raise ProviderAPIError("FIVEDOLLARFOOTBALL_API_KEY is missing. Add it to the environment or GitHub Actions secrets; never paste it into source code.")
        if args.command == "status":
            print_json(client.status())
        elif args.command == "fixtures":
            target = args.date or datetime.now(ZoneInfo(args.timezone)).date().isoformat()
            data = client.fixtures(target, args.timezone)
            print_json({
                "provider": data.get("provider"),
                "results": data.get("results"),
                "meta": data.get("_veltrix_meta"),
                "response": data.get("response", []),
            })
        elif args.command == "history":
            start, end = validate_date_range(args.start_date, args.end_date)
            payload = client.fixtures_between(start, end, args.timezone)
            rows = completed_fixture_rows(payload.get("response", []))
            featured = add_leakage_safe_rolling_features(rows, args.window)
            count = write_csv(featured, args.output)
            print(f"Fixtures received: {payload.get('results', 0)}; completed matches saved: {count}")
            print(f"CSV: {args.output}; rolling window: {args.window}; timezone: {args.timezone}")
            print_json({"provider": payload.get("provider"), "meta": payload.get("_veltrix_meta"), "saved_rows": count})
        elif args.command == "leagues":
            data = client.leagues(args.page, args.per_page)
            print_json(data)
        elif args.command == "odds":
            target = date.fromisoformat(args.date)
            payload = client.fixtures(target.isoformat(), args.timezone)
            upcoming = [
                row for row in payload.get("response", [])
                if isinstance(row, dict)
                and ((row.get("fixture") or {}).get("status") or {}).get("short") == "NS"
            ]
            results = []
            for fixture in upcoming[:max(0, min(args.limit, 15))]:
                fixture_id = (fixture.get("fixture") or {}).get("id")
                if fixture_id is None:
                    continue
                try:
                    odds = client.fixture_odds(fixture_id)
                    results.append({
                        "fixture_id": fixture_id,
                        "home_team": (fixture.get("teams") or {}).get("home", {}).get("name"),
                        "away_team": (fixture.get("teams") or {}).get("away", {}).get("name"),
                        "kickoff": (fixture.get("fixture") or {}).get("date"),
                        "odds": odds.get("data"),
                    })
                except ProviderAPIError as exc:
                    results.append({"fixture_id": fixture_id, "status": "ODDS_UNAVAILABLE", "reason": str(exc)})
            print_json({
                "provider": "5DollarFootballAPI",
                "date": target.isoformat(),
                "fixtures_considered": len(upcoming[:max(0, min(args.limit, 15))]),
                "fixtures_with_odds_response": sum(1 for row in results if isinstance(row.get("odds"), dict)),
                "results": results,
                "note": "Prices are reference data only. Model probabilities remain experimental and no bets are placed.",
            })
    except (RuntimeError, ValueError, OSError, ProviderAPIError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
