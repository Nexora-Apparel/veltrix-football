"""Fetch today's fixtures and write an experimental prediction JSON report."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError
from app.live_predictions import build_daily_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="Nigeria-local fixture date YYYY-MM-DD (defaults to today in selected timezone)")
    parser.add_argument("--history", default="data/open_historical_matches.csv")
    parser.add_argument("--output", default="reports/daily_predictions.json")
    parser.add_argument("--timezone", default="Africa/Lagos")
    args = parser.parse_args()
    try:
        target_date = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(args.timezone)).date()
        payload = FootballAPI(get_settings()).fixtures(target_date.isoformat(), args.timezone)
        report = build_daily_report(payload, args.history, as_of=target_date, timezone_name=args.timezone)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "date": target_date.isoformat(),
            "fixtures_received": report["fixtures_received"],
            "predictions_created": report["predictions_created"],
            "insufficient_history": report["insufficient_history"],
            "output": str(output),
            "model_status": report["model_status"],
        }, indent=2))
    except (RuntimeError, ValueError, FootballAPIError, OSError) as exc:
        print(f"DAILY PREDICTION RUN FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
