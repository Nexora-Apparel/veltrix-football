"""Import category-isolated historical results from the English Women's Football database.

Source: https://github.com/probjects/ewf-database
License: CC BY-SA 4.0; attribution and ShareAlike obligations apply.
This output is deliberately separate from the senior historical dataset.
"""
from __future__ import annotations

import argparse
import csv
import io
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import requests

SOURCE = "probjects/ewf-database"
SOURCE_URL = "https://raw.githubusercontent.com/probjects/ewf-database/main/data/ewf_matches.csv"
USER_AGENT = "VeltrixFootball/0.1"
OUTPUT_COLUMNS = [
    "source", "source_match_id", "category", "season", "division",
    "match_date", "home_team_id", "home_team", "away_team_id", "away_team",
    "home_goals", "away_goals", "full_time_result",
]


def normalize_match(row: dict[str, Any], start: date, end: date) -> dict[str, Any] | None:
    """Validate and normalize one completed match without losing source identity."""
    try:
        match_day = date.fromisoformat(str(row.get("date") or "").strip())
        home_goals = int(str(row.get("home_team_score") or "").strip())
        away_goals = int(str(row.get("away_team_score") or "").strip())
        tier = int(str(row.get("tier") or "").strip())
    except (TypeError, ValueError):
        return None
    if not start <= match_day <= end or home_goals < 0 or away_goals < 0 or tier not in (1, 2):
        return None
    home = str(row.get("home_team_name") or "").strip()
    away = str(row.get("away_team_name") or "").strip()
    home_id = str(row.get("home_team_id") or "").strip()
    away_id = str(row.get("away_team_id") or "").strip()
    match_id = str(row.get("match_id") or "").strip()
    season = str(row.get("season") or "").strip()
    division = str(row.get("division") or "").strip()
    if not all((home, away, home_id, away_id, match_id, season, division)) or home_id == away_id:
        return None
    result = "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"
    return {
        "source": SOURCE,
        "source_match_id": match_id,
        "category": "WOMENS_CLUB",
        "season": season,
        "division": f"ENG_WOMENS_TIER_{tier}",
        "match_date": match_day.isoformat(),
        "home_team_id": home_id,
        "home_team": home,
        "away_team_id": away_id,
        "away_team": away,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "full_time_result": result,
    }


def import_dataset(start_date: str, end_date: str, output: str, timeout: int = 45) -> dict[str, Any]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end date must be on or after start date")
    response = requests.get(
        SOURCE_URL, timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv"},
    )
    try:
        response.raise_for_status()
        stream = io.StringIO(response.content.decode("utf-8-sig"))
        reader = csv.DictReader(stream)
        required = {"date", "tier", "division", "match_id", "season", "home_team_id",
                    "home_team_name", "away_team_id", "away_team_name",
                    "home_team_score", "away_team_score"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise RuntimeError(f"Unexpected EWF CSV schema: {reader.fieldnames}")
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        seen: set[str] = set()
        by_division: Counter[str] = Counter()
        by_season: Counter[str] = Counter()
        saved = invalid = duplicates = 0
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            for raw in reader:
                normalized = normalize_match(raw, start, end)
                if normalized is None:
                    # Rows outside the requested date range are normal and not malformed.
                    try:
                        row_date = date.fromisoformat(str(raw.get("date") or "").strip())
                    except ValueError:
                        invalid += 1
                        continue
                    if start <= row_date <= end:
                        invalid += 1
                    continue
                source_id = normalized["source_match_id"]
                if source_id in seen:
                    duplicates += 1
                    continue
                seen.add(source_id)
                writer.writerow(normalized)
                saved += 1
                by_division[normalized["division"]] += 1
                by_season[normalized["season"]] += 1
        return {
            "source": SOURCE, "source_url": SOURCE_URL, "license": "CC BY-SA 4.0",
            "category": "WOMENS_CLUB", "from": start.isoformat(), "to": end.isoformat(),
            "matches_added": saved, "invalid_rows_in_requested_range": invalid,
            "duplicate_source_match_ids": duplicates,
            "matches_by_division": dict(sorted(by_division.items())),
            "matches_by_season": dict(sorted(by_season.items())),
            "output": str(path),
        }
    finally:
        response.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--output", default="data/womens_club_historical_matches.csv")
    args = parser.parse_args()
    print(import_dataset(args.start, args.end, args.output))


if __name__ == "__main__":
    main()
