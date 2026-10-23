from __future__ import annotations

import argparse
import json
from datetime import date

from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError
from app.historical_data import add_leakage_safe_rolling_features, completed_fixture_rows, validate_date_range, write_csv

def print_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))

def main():
    parser = argparse.ArgumentParser(description="Veltrix Football API diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Verify API key/account status")
    fixture_parser = sub.add_parser("fixtures", help="Fetch fixtures for a date")
    fixture_parser.add_argument("--date", default=date.today().isoformat())
    fixture_parser.add_argument("--timezone", default="Africa/Lagos")
    history_parser = sub.add_parser("history", help="Export completed historical fixtures and pre-match form features")
    history_parser.add_argument("--from", dest="start_date", required=True, help="Start date YYYY-MM-DD")
    history_parser.add_argument("--to", dest="end_date", required=True, help="End date YYYY-MM-DD; max 366 calendar days")
    history_parser.add_argument("--output", default="data/historical_features.csv")
    history_parser.add_argument("--window", type=int, default=5, help="Prior matches per team for rolling features")
    history_parser.add_argument("--timezone", default="Africa/Lagos")
    league_parser = sub.add_parser("leagues", help="List competitions available to the account")
    league_parser.add_argument("--all-seasons", action="store_true")

    args = parser.parse_args()

    try:
        api = FootballAPI(get_settings())
        if args.command == "status":
            data = api.status()
            print("API status request succeeded. Review account/subscription fields below.")
            print_json(data)
        elif args.command == "fixtures":
            data = api.fixtures(args.date, args.timezone)
            fixtures = data.get("response", [])
            print(f"Valid API response. Fixtures returned: {len(fixtures)}")
            print_json({"results": data.get("results"), "meta": data.get("_veltrix_meta"), "response": fixtures})
        elif args.command == "history":
            start, end = validate_date_range(args.start_date, args.end_date)
            payload = api.fixtures_between(start, end, args.timezone)
            raw = payload.get("response", [])
            rows = completed_fixture_rows(raw)
            featured = add_leakage_safe_rolling_features(rows, args.window)
            count = write_csv(featured, args.output)
            print(f"Fixtures received: {len(raw)}; completed matches saved: {count}")
            print(f"CSV: {args.output}; rolling window: {args.window}; timezone: {args.timezone}")
            print_json({"results": payload.get("results"), "meta": payload.get("_veltrix_meta"), "saved_rows": count})
        elif args.command == "leagues":
            data = api.leagues(current=not args.all_seasons)
            leagues = data.get("response", [])
            print(f"Valid API response. Competitions returned: {len(leagues)}")
            print_json({"results": data.get("results"), "meta": data.get("_veltrix_meta"), "response": leagues})
    except (RuntimeError, FootballAPIError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
