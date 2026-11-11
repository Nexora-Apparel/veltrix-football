"""Read-only row-level reconciliation for pinned OpenFootball and 5Dollar snapshots.

The script intentionally compares date + ordered teams. OpenFootball kickoff times
are unzoned local times, so they are never converted to UTC or compared as instants.
A one-day date mismatch is reported as a conflict, not silently normalized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

TEAM_CROSSWALK = {
    "AFC Bournemouth": "Bournemouth",
    "Arsenal FC": "Arsenal",
    "Aston Villa FC": "Aston Villa",
    "Brentford FC": "Brentford",
    "Brighton & Hove Albion FC": "Brighton",
    "Chelsea FC": "Chelsea",
    "Coventry City FC": "Coventry",
    "Crystal Palace FC": "Crystal Palace",
    "Everton FC": "Everton",
    "Fulham FC": "Fulham",
    "Hull City AFC": "Hull",
    "Ipswich Town FC": "Ipswich",
    "Leeds United FC": "Leeds",
    "Liverpool FC": "Liverpool",
    "Manchester City FC": "Man City",
    "Manchester United FC": "Man Utd",
    "Newcastle United FC": "Newcastle",
    "Nottingham Forest FC": "Nottm Forest",
    "Sunderland AFC": "Sunderland",
    "Tottenham Hotspur FC": "Tottenham",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ft_score(row: dict) -> tuple[int, int] | None:
    score = row.get("score")
    if not isinstance(score, dict):
        return None
    value = score.get("ft")
    if not isinstance(value, list) or len(value) != 2:
        return None
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in value):
        return None
    return value[0], value[1]


def _fd_score(row: dict) -> tuple[int, int] | None:
    goals = row.get("goals")
    if not isinstance(goals, dict):
        return None
    home, away = goals.get("home"), goals.get("away")
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in (home, away)):
        return None
    return home, away


def _team_pair(row: dict) -> tuple[str, str] | None:
    home, away = row.get("teams", {}).get("home"), row.get("teams", {}).get("away")
    if not isinstance(home, dict) or not isinstance(away, dict):
        return None
    home_name, away_name = home.get("name"), away.get("name")
    if not isinstance(home_name, str) or not home_name.strip():
        return None
    if not isinstance(away_name, str) or not away_name.strip():
        return None
    return home_name.strip(), away_name.strip()


def reconcile(
    openfootball: dict,
    fivedollar: dict,
    start_date: str,
    end_date_exclusive: str,
    openfootball_sha256: str = "",
    fivedollar_sha256: str = "",
) -> dict:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date_exclusive)
    if end <= start:
        raise ValueError("end date must be after start date")

    source_rows = openfootball.get("matches")
    reference_rows = fivedollar.get("rows")
    if not isinstance(source_rows, list) or not isinstance(reference_rows, list):
        raise ValueError("snapshot schemas invalid")

    reverse = {provider_name: source_name for source_name, provider_name in TEAM_CROSSWALK.items()}
    source_index: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    source_pair_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    source_window_rows = []
    unknown_source_teams = []
    duplicate_source_keys = 0

    for row in source_rows:
        if not isinstance(row, dict):
            continue
        try:
            match_day = date.fromisoformat(str(row.get("date", "")))
        except ValueError:
            continue
        if not start <= match_day < end:
            continue
        source_window_rows.append(row)
        home_name, away_name = row.get("team1"), row.get("team2")
        if home_name not in TEAM_CROSSWALK or away_name not in TEAM_CROSSWALK:
            unknown_source_teams.append({"date": row.get("date"), "home": home_name, "away": away_name})
            continue
        home = TEAM_CROSSWALK[home_name]
        away = TEAM_CROSSWALK[away_name]
        key = (match_day.isoformat(), home, away)
        pair = (home, away)
        if source_index[key]:
            duplicate_source_keys += 1
        source_index[key].append(row)
        source_pair_index[pair].append(row)

    reference_index: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    reference_pair_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    duplicate_reference_ids = 0
    seen_ids: set[str] = set()
    invalid_reference_rows = 0
    for row in reference_rows:
        if not isinstance(row, dict) or row.get("status") != "finished":
            continue
        fixture_id = str(row.get("id", "")).strip()
        pair = _team_pair(row)
        kickoff = row.get("kickoff_utc")
        if not fixture_id or not pair or not isinstance(kickoff, str):
            invalid_reference_rows += 1
            continue
        if fixture_id in seen_ids:
            duplicate_reference_ids += 1
        seen_ids.add(fixture_id)
        try:
            match_day = date.fromisoformat(kickoff[:10])
        except ValueError:
            invalid_reference_rows += 1
            continue
        if not start <= match_day < end:
            continue
        home, away = pair
        key = (match_day.isoformat(), home, away)
        reference_index[key].append(row)
        reference_pair_index[(home, away)].append(row)

    exact_date_team_matches = 0
    score_agreements = 0
    score_conflicts = []
    missing_openfootball_scores = []
    date_conflicts = []
    unmatched_reference = []
    matched_source_keys: set[tuple[str, str, str]] = set()
    duplicate_reference_keys = sum(1 for rows in reference_index.values() if len(rows) > 1)
    for key, refs in reference_index.items():
        if len(refs) != 1:
            continue
        source_matches = source_index.get(key, [])
        ref = refs[0]
        if len(source_matches) == 1:
            matched_source_keys.add(key)
            exact_date_team_matches += 1
            source_score = _ft_score(source_matches[0])
            reference_score = _fd_score(ref)
            if source_score is None:
                missing_openfootball_scores.append({
                    "date": key[0], "home": key[1], "away": key[2],
                    "reference_score": list(reference_score) if reference_score else None,
                })
            elif reference_score is None:
                missing_openfootball_scores.append({
                    "date": key[0], "home": key[1], "away": key[2],
                    "reference_score": None,
                })
            elif source_score == reference_score:
                score_agreements += 1
            else:
                score_conflicts.append({
                    "date": key[0], "home": key[1], "away": key[2],
                    "openfootball_score": list(source_score),
                    "fivedollar_score": list(reference_score),
                })
        elif not source_matches:
            pair_matches = source_pair_index.get((key[1], key[2]), [])
            if len(pair_matches) == 1:
                source_row = pair_matches[0]
                source_match_day = date.fromisoformat(str(source_row.get("date")))
                matched_source_keys.add((source_match_day.isoformat(), key[1], key[2]))
                date_conflicts.append({
                    "home": key[1], "away": key[2],
                    "fivedollar_date": key[0],
                    "openfootball_date": source_row.get("date"),
                    "date_difference_days": (
                        date.fromisoformat(str(source_row.get("date"))) - date.fromisoformat(key[0])
                    ).days,
                    "fivedollar_score": list(_fd_score(ref)) if _fd_score(ref) else None,
                    "openfootball_score": list(_ft_score(source_row)) if _ft_score(source_row) else None,
                })
            else:
                unmatched_reference.append({
                    "date": key[0], "home": key[1], "away": key[2], "fixture_id": str(ref.get("id")),
                })

    exact_source_keys = set(source_index)
    reference_keys = set(reference_index)
    unmatched_openfootball = [
        {"date": key[0], "home": key[1], "away": key[2]}
        for key in sorted(exact_source_keys - reference_keys - matched_source_keys)
    ]

    reference_count = len(reference_index)
    score_coverage = (
        score_agreements + len(score_conflicts)
    ) / reference_count if reference_count else 0.0
    comparable_scores = score_agreements + len(score_conflicts)
    score_agreement_rate = score_agreements / comparable_scores if comparable_scores else None

    passed = (
        reference_count > 0
        and exact_date_team_matches == reference_count
        and not missing_openfootball_scores
        and not date_conflicts
        and not unmatched_reference
        and not unmatched_openfootball
        and not duplicate_source_keys
        and not duplicate_reference_ids
        and not duplicate_reference_keys
        and not unknown_source_teams
        and not invalid_reference_rows
        and not score_conflicts
    )
    return {
        "schema_version": "openfootball-5dollar-live-reconciliation-v1",
        "status": "PASS" if passed else "REVIEW_REQUIRED",
        "source_acceptance": passed,
        "read_only": True,
        "database_writes": 0,
        "prediction_code_access": False,
        "window": {"start_inclusive": start.isoformat(), "end_exclusive": end.isoformat()},
        "source_hashes": {
            "openfootball_sha256": openfootball_sha256,
            "fivedollar_sha256": fivedollar_sha256,
        },
        "team_crosswalk": {
            "source_team_count": len(TEAM_CROSSWALK),
            "explicit_mappings": TEAM_CROSSWALK,
            "unmapped_source_teams": unknown_source_teams,
        },
        "counts": {
            "openfootball_source_rows_in_window": len(source_window_rows),
            "fivedollar_finished_rows_in_window": reference_count,
            "exact_date_and_ordered_team_matches": exact_date_team_matches,
            "score_agreements": score_agreements,
            "score_conflicts": len(score_conflicts),
            "missing_openfootball_scores": len(missing_openfootball_scores),
            "date_conflicts": len(date_conflicts),
            "unmatched_reference_fixtures": len(unmatched_reference),
            "unmatched_openfootball_fixtures": len(unmatched_openfootball),
            "duplicate_openfootball_keys": duplicate_source_keys,
            "duplicate_fivedollar_fixture_ids": duplicate_reference_ids,
            "duplicate_fivedollar_match_keys": duplicate_reference_keys,
            "invalid_reference_rows": invalid_reference_rows,
        },
        "rates": {
            "score_coverage_against_reference": round(score_coverage, 6),
            "score_agreement_on_comparable_scores": (
                round(score_agreement_rate, 6) if score_agreement_rate is not None else None
            ),
        },
        "details": {
            "date_conflicts": date_conflicts,
            "missing_openfootball_scores": missing_openfootball_scores,
            "score_conflicts": score_conflicts,
            "unmatched_reference_fixtures": unmatched_reference,
            "unmatched_openfootball_fixtures": unmatched_openfootball,
        },
        "timestamp_policy": (
            "5Dollar kickoff_utc is UTC. OpenFootball date/time has no timezone; "
            "its date and local time are retained as supplied. No timezone conversion "
            "or assumed UTC offset is applied."
        ),
        "limitations": [
            "A passing EPL comparison would qualify only this source pair and this window, not other competitions or data domains.",
            "FPL fields are a separate undocumented EPL player-data source and are not reconciled by this report.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openfootball", required=True)
    parser.add_argument("--fivedollar", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date-exclusive", required=True)
    parser.add_argument("--output", default="readonly-snapshots/reconciliation_report.json")
    parser.add_argument("--openfootball-sha256", default="")
    parser.add_argument("--fivedollar-sha256", default="")
    args = parser.parse_args()
    openfootball = json.loads(Path(args.openfootball).read_text(encoding="utf-8"))
    fivedollar = json.loads(Path(args.fivedollar).read_text(encoding="utf-8"))
    report = reconcile(
        openfootball, fivedollar, args.start_date, args.end_date_exclusive,
        args.openfootball_sha256, args.fivedollar_sha256,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = report["counts"]
    print(
        f"RECONCILIATION: {report['status']}; "
        f"reference={counts['fivedollar_finished_rows_in_window']}; "
        f"exact={counts['exact_date_and_ordered_team_matches']}; "
        f"score_agreements={counts['score_agreements']}; "
        f"missing_scores={counts['missing_openfootball_scores']}; "
        f"date_conflicts={counts['date_conflicts']}; "
        f"score_conflicts={counts['score_conflicts']}"
    )
    print(f"SOURCE_ACCEPTANCE: {str(report['source_acceptance']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
