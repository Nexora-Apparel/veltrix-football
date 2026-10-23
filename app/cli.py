from __future__ import annotations

import argparse
import json
from datetime import date

from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError

def print_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))

def main():
    parser = argparse.ArgumentParser(description="Veltrix Football API diagnostics")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Verify API key/account status")
    fixture_parser = sub.add_parser("fixtures", help="Fetch fixtures for a date")
    fixture_parser.add_argument("--date", default=date.today().isoformat())
    fixture_parser.add_argument("--timezone", default="Africa/Lagos")
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
