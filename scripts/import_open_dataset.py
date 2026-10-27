"""Import an open football results dataset without committing the raw data."""
from __future__ import annotations

import argparse
import csv
import io
from collections import Counter
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

DATASET_REPO = "xgabora/Club-Football-Match-Data"
RAW_BASE = f"https://raw.githubusercontent.com/{DATASET_REPO}/main/"
USER_AGENT = "VeltrixFootball/0.1"
FOOTBALL_DATA_DIVISIONS = (
    "E0", "E1", "E2", "E3", "EC", "SC0", "SC1", "SC2", "SC3",
    "D1", "D2", "I1", "I2", "SP1", "SP2", "F1", "F2", "N1",
    "B1", "P1", "T1", "G1",
)
FOOTBALL_DATA_BASE = "https://www.football-data.co.uk/mmz4281"
REQUIRED_COLUMNS = {"Division", "MatchDate", "HomeTeam", "AwayTeam", "FTHome", "FTAway"}
OUTPUT_COLUMNS = [
    "source", "division", "match_date", "home_team", "away_team",
    "home_goals", "away_goals", "full_time_result",
    "home_elo", "away_elo", "home_form3", "away_form3", "home_form5", "away_form5",
    "home_odds", "draw_odds", "away_odds", "over25_odds", "under25_odds",
    "half_time_home_goals", "half_time_away_goals",
    "home_shots", "away_shots", "home_shots_on_target", "away_shots_on_target",
]


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() in {"", "-", "NA", "N/A", "nan", "None"}:
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def normalize_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Map one source row into a stable schema; reject malformed score rows."""
    if not REQUIRED_COLUMNS.issubset(row.keys()):
        missing = sorted(REQUIRED_COLUMNS - set(row.keys()))
        raise ValueError(f"Dataset is missing required columns: {', '.join(missing)}")
    try:
        match_date = date.fromisoformat(str(row.get("MatchDate", "")).strip()).isoformat()
    except ValueError:
        return None
    home_goals, away_goals = _number(row.get("FTHome")), _number(row.get("FTAway"))
    if (home_goals is None or away_goals is None or not home_goals.is_integer()
            or not away_goals.is_integer() or home_goals < 0 or away_goals < 0):
        return None
    home_team, away_team = str(row.get("HomeTeam") or "").strip(), str(row.get("AwayTeam") or "").strip()
    division = str(row.get("Division") or "").strip()
    if not home_team or not away_team or not division or home_team.casefold() == away_team.casefold():
        return None
    hg, ag = int(home_goals), int(away_goals)
    result = "H" if hg > ag else "A" if hg < ag else "D"
    return {
        "source": DATASET_REPO,
        "division": division,
        "match_date": match_date,
        "home_team": home_team,
        "away_team": away_team,
        "home_goals": hg,
        "away_goals": ag,
        "full_time_result": result,
        "home_elo": _number(row.get("HomeElo")),
        "away_elo": _number(row.get("AwayElo")),
        "home_form3": _number(row.get("Form3Home")),
        "away_form3": _number(row.get("Form3Away")),
        "home_form5": _number(row.get("Form5Home")),
        "away_form5": _number(row.get("Form5Away")),
        "home_odds": _number(row.get("OddHome")),
        "draw_odds": _number(row.get("OddDraw")),
        "away_odds": _number(row.get("OddAway")),
        "over25_odds": _number(row.get("Over25")),
        "under25_odds": _number(row.get("Under25")),
        "half_time_home_goals": _number(row.get("HTHome")),
        "half_time_away_goals": _number(row.get("HTAway")),
        "home_shots": _number(row.get("HomeShots")),
        "away_shots": _number(row.get("AwayShots")),
        "home_shots_on_target": _number(row.get("HomeTarget")),
        "away_shots_on_target": _number(row.get("AwayTarget")),
    }


def _football_data_season_code(end_date: date) -> str:
    """Return the current football-data.co.uk season code for an end date."""
    start_year = end_date.year if end_date.month >= 7 else end_date.year - 1
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def _football_data_date(value: Any) -> date | None:
    """Parse football-data.co.uk's day-first dates and common ISO variants."""
    raw = str(value or "").strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _team_identity(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    key = re.sub(r"[^a-z0-9]", "", normalized)
    aliases = {
        "manutd": "manchesterunited", "manunited": "manchesterunited",
        "manchesterutd": "manchesterunited", "mancity": "manchestercity",
        "spurs": "tottenhamhotspur", "tottenham": "tottenhamhotspur",
        "wolves": "wolverhamptonwanderers", "psg": "parissaintgermain",
        "barca": "barcelona", "juve": "juventus", "inter": "intermilan",
        "internazionale": "intermilan", "athleticclub": "athleticbilbao",
    }
    return aliases.get(key, key)


def normalize_football_data_row(raw: dict[str, Any], division: str) -> dict[str, Any] | None:
    """Map a football-data.co.uk current-season result into Veltrix's CSV schema."""
    match_date = _football_data_date(raw.get("Date"))
    home = str(raw.get("HomeTeam") or "").strip()
    away = str(raw.get("AwayTeam") or "").strip()
    home_goals, away_goals = _number(raw.get("FTHG")), _number(raw.get("FTAG"))
    if (
        match_date is None or not home or not away
        or _team_identity(home) == _team_identity(away)
        or home_goals is None or away_goals is None
        or not home_goals.is_integer() or not away_goals.is_integer()
        or home_goals < 0 or away_goals < 0
    ):
        return None
    hg, ag = int(home_goals), int(away_goals)
    result = "H" if hg > ag else "A" if hg < ag else "D"
    return {
        "source": "football-data.co.uk",
        "division": division,
        "match_date": match_date.isoformat(),
        "home_team": home,
        "away_team": away,
        "home_goals": hg,
        "away_goals": ag,
        "full_time_result": result,
        "home_elo": None,
        "away_elo": None,
        "home_form3": None,
        "away_form3": None,
        "home_form5": None,
        "away_form5": None,
        "home_odds": _number(raw.get("B365H") or raw.get("AvgH")),
        "draw_odds": _number(raw.get("B365D") or raw.get("AvgD")),
        "away_odds": _number(raw.get("B365A") or raw.get("AvgA")),
        "over25_odds": _number(raw.get("B365>2.5") or raw.get("Avg>2.5")),
        "under25_odds": _number(raw.get("B365<2.5") or raw.get("Avg<2.5")),
        "half_time_home_goals": _number(raw.get("HTHG")),
        "half_time_away_goals": _number(raw.get("HTAG")),
        "home_shots": _number(raw.get("HS")),
        "away_shots": _number(raw.get("AS")),
        "home_shots_on_target": _number(raw.get("HST")),
        "away_shots_on_target": _number(raw.get("AST")),
    }


def _append_current_season_fallback(
    session: requests.Session,
    writer: csv.DictWriter,
    seen: set[tuple[str, str, str, str]],
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    """Supplement recent gaps from public current-season league CSVs when enabled.

    API-Football plan restrictions must not erase accessible open results. This
    source is used only as a historical-results fallback; it never supplies live
    fixtures or live bookmaker prices. Missing league files are normal and skipped.
    """
    season_code = _football_data_season_code(end_date)
    summary = {"files_checked": 0, "files_available": 0, "matches_added": 0}
    for division in FOOTBALL_DATA_DIVISIONS:
        url = f"{FOOTBALL_DATA_BASE}/{season_code}/{division}.csv"
        summary["files_checked"] += 1
        response = None
        try:
            response = session.get(url, timeout=20)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            decoded = response.content.decode("cp1252", errors="replace")
            reader = csv.DictReader(io.StringIO(decoded))
            if not reader.fieldnames or not {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}.issubset(reader.fieldnames):
                continue
            summary["files_available"] += 1
            for raw in reader:
                parsed_date = _football_data_date(raw.get("Date"))
                if parsed_date is None or not start_date <= parsed_date <= end_date:
                    continue
                row = normalize_football_data_row(raw, division)
                if row is None:
                    continue
                key = (
                    row["division"], row["match_date"],
                    _team_identity(row["home_team"]), _team_identity(row["away_team"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                writer.writerow(row)
                summary["matches_added"] += 1
        except (requests.RequestException, OSError, UnicodeError, csv.Error):
            # This is an optional secondary source. Preserve the primary import if
            # one league file is unavailable, rate-limited, or temporarily malformed.
            continue
        finally:
            if response is not None:
                response.close()
    return summary


def find_matches_csv(session: requests.Session) -> str:
    """Return the documented raw CSV path without spending a rate-limited tree API call.

    The upstream repository documents its match table at data/Matches.csv.
    Keeping this URL explicit avoids making the daily prediction workflow depend
    on GitHub's unauthenticated recursive-tree API quota.
    """
    del session  # retained in the signature for compatibility with callers/tests
    return RAW_BASE + "data/Matches.csv"


def import_dataset(start_date: str, end_date: str, output: str, timeout: int = 90) -> dict[str, Any]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start:
        raise ValueError("end date must be on or after start date")
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/csv,application/json"})
    csv_url = find_matches_csv(session)
    response = session.get(csv_url, timeout=timeout)
    response.raise_for_status()
    # Decode the completed response into a managed text stream. Wrapping the
    # requests raw socket in TextIOWrapper caused a close-order failure in CI.
    text_stream = io.StringIO(response.content.decode("utf-8-sig"))
    reader = csv.DictReader(text_stream)
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
        raise RuntimeError(f"Unexpected CSV schema. Found columns: {reader.fieldnames}")
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str, str, str]] = set()
    competition_counts: Counter[str] = Counter()
    season_counts: Counter[str] = Counter()
    scanned = saved = duplicates = invalid = 0
    try:
        with out_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            for raw in reader:
                scanned += 1
                raw_date = str(raw.get("MatchDate") or "").strip()
                try:
                    parsed_date = date.fromisoformat(raw_date)
                except ValueError:
                    invalid += 1
                    continue
                if not start <= parsed_date <= end:
                    continue
                row = normalize_row(raw)
                if row is None:
                    invalid += 1
                    continue
                key = (row["division"], row["match_date"], row["home_team"].casefold(), row["away_team"].casefold())
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                writer.writerow(row)
                saved += 1
                competition_counts[row["division"]] += 1
                season_counts[row["match_date"][:4]] += 1

            fallback_summary = {"files_checked": 0, "files_available": 0, "matches_added": 0}
            if os.getenv("VELTRIX_ENABLE_FOOTBALL_DATA_FALLBACK", "").strip().lower() in {"1", "true", "yes"}:
                fallback_summary = _append_current_season_fallback(
                    session, writer, seen, start, end
                )
                for division in FOOTBALL_DATA_DIVISIONS:
                    competition_counts.setdefault(division, 0)
                # Count fallback rows by season from the deduplicated output file
                # on the next load; the import summary reports the total additions.
    finally:
        text_stream.close()
        response.close()
        session.close()
    if saved == 0:
        out_path.unlink(missing_ok=True)
        raise RuntimeError("No valid completed matches found in the requested date range.")
    return {
        "source_repository": DATASET_REPO,
        "source_csv": csv_url,
        "date_range": {"from": start.isoformat(), "to": end.isoformat()},
        "source_rows_scanned": scanned,
        "matches_saved": saved + fallback_summary["matches_added"],
        "fallback_source": {
            "name": "football-data.co.uk",
            "season_code": _football_data_season_code(end),
            **fallback_summary,
        },
        "duplicates_skipped": duplicates,
        "invalid_rows_skipped": invalid,
        "matches_by_competition": dict(sorted(competition_counts.items())),
        "matches_by_season": dict(sorted(season_counts.items())),
        "output": str(out_path),
        "columns": OUTPUT_COLUMNS,
        "note": "Odds and match statistics may be missing by league/season. Validate per-field coverage before modeling.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import open historical football results for Veltrix Football")
    parser.add_argument("--from", dest="start_date", default="2024-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="end_date", default=date.today().isoformat(), help="End date YYYY-MM-DD")
    parser.add_argument("--output", default="data/open_historical_matches.csv")
    args = parser.parse_args()
    try:
        print(json.dumps(import_dataset(args.start_date, args.end_date, args.output), indent=2))
    except (ValueError, RuntimeError, requests.RequestException) as exc:
        print(f"IMPORT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
