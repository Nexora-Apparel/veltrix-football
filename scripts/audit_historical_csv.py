"""Audit historical CSV integrity, date/competition coverage and feature missingness."""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

REQUIRED = ("match_date", "division", "home_team", "away_team", "home_goals", "away_goals", "full_time_result")
OUTCOMES = {"H", "D", "A"}

def audit_csv(input_path: str | Path) -> dict[str, Any]:
    path = Path(input_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing_required = sorted(set(REQUIRED) - set(columns))
        if missing_required:
            raise ValueError("Historical CSV missing required columns: " + ", ".join(missing_required))
        total = invalid_rows = duplicates = 0
        missing_values: Counter[str] = Counter()
        division_counts: Counter[str] = Counter()
        division_dates: dict[str, list[str]] = defaultdict(list)
        division_years: dict[str, Counter[str]] = defaultdict(Counter)
        seen: set[tuple[str, str, str, str]] = set()
        min_date: str | None = None
        max_date: str | None = None
        for row in reader:
            total += 1
            for column in columns:
                if not str(row.get(column) or "").strip():
                    missing_values[column] += 1
            try:
                match_day = date.fromisoformat(str(row.get("match_date") or "").strip()).isoformat()
                home_goals, away_goals = int(str(row.get("home_goals") or "").strip()), int(str(row.get("away_goals") or "").strip())
                division, home, away = (str(row.get(k) or "").strip() for k in ("division", "home_team", "away_team"))
                result = str(row.get("full_time_result") or "").strip().upper()
                if (not division or not home or not away or home.casefold() == away.casefold()
                    or home_goals < 0 or away_goals < 0 or result not in OUTCOMES
                    or result != ("H" if home_goals > away_goals else "A" if home_goals < away_goals else "D")):
                    raise ValueError("invalid match row")
            except (TypeError, ValueError):
                invalid_rows += 1
                continue
            key = (division.casefold(), match_day, home.casefold(), away.casefold())
            if key in seen:
                duplicates += 1
            seen.add(key)
            division_counts[division] += 1
            division_dates[division].append(match_day)
            division_years[division][match_day[:4]] += 1
            min_date = match_day if min_date is None else min(min_date, match_day)
            max_date = match_day if max_date is None else max(max_date, match_day)
    competitions: dict[str, Any] = {}
    for division in sorted(division_counts):
        dates, years = division_dates[division], division_years[division]
        competitions[division] = {
            "matches": division_counts[division],
            "first_match_date": min(dates), "last_match_date": max(dates),
            "matches_by_calendar_year": dict(sorted(years.items())),
            "unobserved_calendar_years_between_first_and_last": [
                str(year) for year in range(int(min(years)), int(max(years)) + 1) if str(year) not in years
            ],
        }
    return {
        "audit_version": 1, "input_file": path.name, "sha256": digest,
        "rows": total, "valid_rows": total - invalid_rows, "invalid_rows": invalid_rows,
        "duplicate_match_keys": duplicates, "competition_count": len(competitions),
        "first_match_date": min_date, "last_match_date": max_date, "columns": columns,
        "missing_values": {column: {"count": missing_values[column], "rate": missing_values[column] / total if total else 0.0} for column in columns},
        "competitions": competitions,
        "coverage_note": ("An unobserved competition/calendar year is a coverage warning, not a confirmed missing-fixture gap; "
                          "a complete expected-fixture inventory is required to prove missing matches."),
        "integrity_status": "PASS" if total > 0 and invalid_rows == 0 and duplicates == 0 else "FAIL",
    }

def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Historical CSV Coverage Audit", "",
        f"- **Integrity:** {report['integrity_status']}",
        f"- **Rows:** {report['rows']:,} ({report['valid_rows']:,} valid)",
        f"- **Competitions/divisions:** {report['competition_count']}",
        f"- **Date range:** {report['first_match_date'] or 'unknown'} to {report['last_match_date'] or 'unknown'}",
        f"- **Duplicate match keys:** {report['duplicate_match_keys']:,}",
        f"- **Invalid rows:** {report['invalid_rows']:,}",
        f"- **SHA-256:** {report['sha256']}", "",
        "> A year with no rows is a coverage warning, not proof of missing fixtures. Confirming gaps requires an expected-fixture inventory.", "",
        "## Coverage by competition", "",
        "| Division | Matches | First date | Last date | Years observed | Unobserved years inside span |",
        "|---|---:|---|---|---|---|",
    ]
    for division, item in report["competitions"].items():
        years = ", ".join(item["matches_by_calendar_year"])
        absent = ", ".join(item["unobserved_calendar_years_between_first_and_last"]) or "—"
        lines.append(f"| {division} | {item['matches']:,} | {item['first_match_date']} | {item['last_match_date']} | {years} | {absent} |")
    lines.extend(["", "## Missingness by column", "", "| Column | Missing values | Missing rate |", "|---|---:|---:|"])
    for column, item in report["missing_values"].items():
        lines.append(f"| {column} | {item['count']:,} | {item['rate']:.1%} |")
    lines.extend(["", "## Interpretation", "", report["coverage_note"], ""])
    return "\n".join(lines)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="data/open_historical_matches.csv")
    parser.add_argument("--json-output", default="reports/historical_coverage_audit.json")
    parser.add_argument("--markdown-output", default="reports/historical_coverage_audit.md")
    args = parser.parse_args()
    report = audit_csv(args.input)
    json_path, markdown_path = Path(args.json_output), Path(args.markdown_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("integrity_status", "rows", "valid_rows", "invalid_rows", "duplicate_match_keys", "competition_count", "first_match_date", "last_match_date", "sha256")}, indent=2))
    if report["integrity_status"] != "PASS":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
