"""Experimental fixture-to-prediction pipeline using completed historical scores.

This is a research baseline, not a validated betting model. It never labels
outputs as value bets and refuses teams with too little historical data.
"""
from __future__ import annotations

import csv
import re
from difflib import get_close_matches
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from typing import Any, Iterable

from app.prediction import match_probabilities

MIN_TEAM_MATCHES = 5
TEAM_WINDOW = 10
HOME_ELO_ADVANTAGE = 55.0
ELO_K = 20.0

# API-Football league IDs mapped to division codes in the open historical CSV.
LEAGUE_DIVISION_BY_ID = {
    39: "E0", 40: "E1", 41: "E2", 42: "E3", 43: "EC",
    140: "SP1", 141: "SP2", 135: "I1", 136: "I2",
    78: "D1", 79: "D2", 61: "F1", 62: "F2", 88: "N1",
    94: "P1", 179: "SC0", 180: "SC1", 183: "SC2", 184: "SC3",
    144: "B1", 203: "T1", 197: "G1", 128: "ARG", 71: "BRA",
    169: "CHN", 98: "JAP", 253: "USA", 262: "MEX", 119: "DEN",
    103: "NOR", 113: "SWE", 218: "AUT", 244: "FIN", 357: "IRL",
    106: "POL", 283: "ROM", 235: "RUS", 207: "SUI",
}


def _name_key(name: Any) -> str:
    """Normalize punctuation and a small, explicit set of common team aliases.

    Deliberately avoid fuzzy matching: a wrong team merge is worse than
    withholding a forecast when historical identity is uncertain.
    """
    key = re.sub(r"[^a-z0-9]+", "", str(name or "").casefold())
    aliases = {
        "manutd": "manchesterunited",
        "manunited": "manchesterunited",
        "manchesterutd": "manchesterunited",
        "mancity": "manchestercity",
        "manchestercty": "manchestercity",
        "spurs": "tottenhamhotspur",
        "tottenham": "tottenhamhotspur",
        "wolves": "wolverhamptonwanderers",
        "wolverhampton": "wolverhamptonwanderers",
        "psg": "parissaintgermain",
        "parissg": "parissaintgermain",
        "barca": "barcelona",
        "fcbarcelona": "barcelona",
        "bayern": "bayernmunich",
        "bayernmunchen": "bayernmunich",
        "juve": "juventus",
        "atleticomadrid": "atleticodemadrid",
        "athleticomadrid": "atleticodemadrid",
        "athmadrid": "atleticodemadrid",
        "newcastleutd": "newcastleunited",
        "westham": "westhamunited",
        "westhamutd": "westhamunited",
    }
    return aliases.get(key, key)


def load_historical_matches(path: str | Path) -> list[dict[str, Any]]:
    """Load normalized importer CSV; malformed rows are ignored."""
    rows: list[dict[str, Any]] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            try:
                match_date = date.fromisoformat(raw["match_date"])
                hg, ag = int(raw["home_goals"]), int(raw["away_goals"])
                home, away = raw["home_team"].strip(), raw["away_team"].strip()
                if not home or not away or hg < 0 or ag < 0 or _name_key(home) == _name_key(away):
                    continue
                rows.append({
                    "date": match_date, "division": str(raw.get("division") or "").strip(),
                    "home": home, "away": away,
                    "home_key": _name_key(home), "away_key": _name_key(away),
                    "home_goals": hg, "away_goals": ag,
                })
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(rows, key=lambda row: row["date"])


def _fixture_parts(item: dict[str, Any], timezone_name: str = "Africa/Lagos") -> dict[str, Any] | None:
    fixture = item.get("fixture") or {}
    teams = item.get("teams") or {}
    league = item.get("league") or {}
    home = (teams.get("home") or {}).get("name")
    away = (teams.get("away") or {}).get("name")
    kickoff = fixture.get("date")
    status = (fixture.get("status") or {}).get("short")
    # Never issue a pre-match forecast for live, finished, cancelled, or postponed games.
    if not home or not away or not kickoff or status not in {"NS", "TBD"}:
        return None
    try:
        parsed = datetime.fromisoformat(str(kickoff).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        local_kickoff = parsed.astimezone(ZoneInfo(timezone_name))
    except (ValueError, ZoneInfoNotFoundError):
        return None
    return {
        "fixture_id": fixture.get("id"),
        "kickoff": parsed.isoformat(),
        "kickoff_local": local_kickoff.isoformat(),
        "kickoff_date": local_kickoff.date(),
        "kickoff_datetime": local_kickoff,
        "home_team": home,
        "away_team": away,
        "league": league.get("name"),
        "league_id": league.get("id"),
        "division_code": LEAGUE_DIVISION_BY_ID.get(league.get("id")),
        "fixture_status": status,
    }


def _elo_probabilities(
    historical_matches: list[dict[str, Any]],
    home_name: str,
    away_name: str,
    division_code: str | None,
    *,
    min_team_matches: int = MIN_TEAM_MATCHES,
    cache: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, float] | None, dict[str, Any]]:
    """Calculate an Elo estimate from prior matches only, caching each history scope."""
    scope = "COMPETITION" if division_code else "GLOBAL_FALLBACK"
    cache_key = division_code or "__GLOBAL__"
    state = cache.get(cache_key) if cache is not None else None
    if state is None:
        scoped = (
            [row for row in historical_matches if row.get("division") == division_code]
            if division_code else historical_matches
        )
        ratings: dict[str, float] = defaultdict(lambda: 1500.0)
        match_counts: dict[str, int] = defaultdict(int)
        total_matches = 0
        draws = 0
        for match in sorted(scoped, key=lambda row: row["date"]):
            h_key, a_key = match["home_key"], match["away_key"]
            hg, ag = match["home_goals"], match["away_goals"]
            home_rating, away_rating = ratings[h_key], ratings[a_key]
            expected_home = 1.0 / (
                1.0 + 10.0 ** (-(home_rating + HOME_ELO_ADVANTAGE - away_rating) / 400.0)
            )
            actual_score = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
            goal_weight = min(2.0, 1.0 + abs(hg - ag) * 0.1)
            delta = ELO_K * goal_weight * (actual_score - expected_home)
            ratings[h_key] = home_rating + delta
            ratings[a_key] = away_rating - delta
            match_counts[h_key] += 1
            match_counts[a_key] += 1
            total_matches += 1
            draws += int(hg == ag)
        state = {
            "ratings": ratings,
            "match_counts": match_counts,
            "total_matches": total_matches,
            "draws": draws,
        }
        if cache is not None:
            cache[cache_key] = state

    ratings = state["ratings"]
    match_counts = state["match_counts"]
    total_matches = state["total_matches"]
    home_key, away_key = _name_key(home_name), _name_key(away_name)
    metadata = {
        "scope": scope,
        "division_code": division_code,
        "home_prior_matches": match_counts[home_key],
        "away_prior_matches": match_counts[away_key],
    }
    if (
        total_matches < 10
        or match_counts[home_key] < min_team_matches
        or match_counts[away_key] < min_team_matches
    ):
        return None, metadata

    draw_rate = (state["draws"] + 3.0) / (total_matches + 10.0)
    expected_home = 1.0 / (
        1.0 + 10.0 ** (-(ratings[home_key] + HOME_ELO_ADVANTAGE - ratings[away_key]) / 400.0)
    )
    non_draw = 1.0 - draw_rate
    return {
        "home_win": non_draw * expected_home,
        "draw": draw_rate,
        "away_win": non_draw * (1.0 - expected_home),
    }, metadata


def predict_fixtures(
    fixtures: Iterable[dict[str, Any]],
    historical_matches: list[dict[str, Any]],
    *,
    as_of: date | None = None,
    min_team_matches: int = MIN_TEAM_MATCHES,
    team_window: int = TEAM_WINDOW,
    timezone_name: str = "Africa/Lagos",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Estimate experimental 1X2 probabilities from prior venue-aware team goal averages.

    Historical matches on or after the fixture's kickoff date are excluded.
    Team rates are shrunk toward historical home/away scoring baselines.
    No odds or value-bet claim is generated by this module.
    """
    if min_team_matches < 1 or team_window < min_team_matches:
        raise ValueError("team_window must be >= min_team_matches >= 1")
    try:
        local_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc
    current_time = now or datetime.now(local_zone)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=local_zone)
    current_time = current_time.astimezone(local_zone)
    today = as_of or current_time.date()
    usable = sorted((m for m in historical_matches if m["date"] < today), key=lambda row: row["date"])
    if not usable:
        # Never silently drop eligible fixtures when the history file is empty
        # or contains no records before the requested date. Emit explicit
        # withheld records so reports distinguish missing data from no fixtures.
        candidates = [
            p for item in fixtures
            if (p := _fixture_parts(item, timezone_name))
            and p["kickoff_date"] == today
            and p["kickoff_datetime"] > current_time
        ]
        return [
            {
                **{k: v for k, v in fixture.items() if k not in {"kickoff_date", "kickoff_datetime"}},
                "model": "experimental_recent_goals_poisson",
                "model_validated": False,
                "betting_recommendation": False,
                "historical_matches": {"home": 0, "away": 0},
                "status": "INSUFFICIENT_HISTORY",
                "reason": "No historical matches dated before the fixture date are available.",
                "team_name_match_suggestions": {},
            }
            for fixture in candidates
        ]

    known_team_names: dict[str, set[str]] = defaultdict(set)
    for match in usable:
        known_team_names[match["home_key"]].add(match["home"])
        known_team_names[match["away_key"]].add(match["away"])
    # Keep priors strictly positive so sparse or pathological data cannot cause
    # division by zero in the rate ratios.
    home_baseline = max(0.05, sum(m["home_goals"] for m in usable) / len(usable))
    away_baseline = max(0.05, sum(m["away_goals"] for m in usable) / len(usable))

    # Rebuild histories per target date so earlier dates are never duplicated.
    output: list[dict[str, Any]] = []
    parsed_fixtures = [
        p for item in fixtures
        if (p := _fixture_parts(item, timezone_name))
        and p["kickoff_date"] == today
        and p["kickoff_datetime"] > current_time
    ]
    # Strict same-local-calendar-day rule: never include tomorrow or later dates.
    for target_date in ([today] if parsed_fixtures else []):
        team_history: dict[str, deque[tuple[int, int, str]]] = defaultdict(
            lambda: deque(maxlen=team_window)
        )
        for match in usable:
            if match["date"] >= target_date:
                continue
            team_history[match["home_key"]].append(
                (match["home_goals"], match["away_goals"], "home")
            )
            team_history[match["away_key"]].append(
                (match["away_goals"], match["home_goals"], "away")
            )

        for fixture in (p for p in parsed_fixtures if p["kickoff_date"] == target_date):
            home_key, away_key = _name_key(fixture["home_team"]), _name_key(fixture["away_team"])
            home_hist, away_hist = list(team_history[home_key]), list(team_history[away_key])
            record: dict[str, Any] = {
                **{k: v for k, v in fixture.items() if k not in {"kickoff_date", "kickoff_datetime"}},
                "model": "experimental_recent_goals_poisson",
                "model_validated": False,
                "betting_recommendation": False,
                "historical_matches": {"home": len(home_hist), "away": len(away_hist)},
            }
            if len(home_hist) < min_team_matches or len(away_hist) < min_team_matches:
                suggestions: dict[str, list[str]] = {}
                for side, team_name, team_key, history in (
                    ("home", fixture["home_team"], home_key, home_hist),
                    ("away", fixture["away_team"], away_key, away_hist),
                ):
                    # Suggestions are diagnostics only; never silently merge fuzzy names.
                    if not history:
                        close_keys = get_close_matches(
                            team_key, list(known_team_names), n=3, cutoff=0.72
                        )
                        display_names = sorted({
                            label for candidate in close_keys
                            for label in known_team_names[candidate]
                        })
                        if display_names:
                            suggestions[side] = display_names[:3]
                record.update({
                    "status": "INSUFFICIENT_HISTORY",
                    "reason": f"Each team needs at least {min_team_matches} prior matches in the historical dataset.",
                    "team_name_match_suggestions": suggestions,
                })
                output.append(record)
                continue

            def shrunk_venue_rates(
                history: list[tuple[int, int, str]],
                venue: str,
                scored_prior: float,
                conceded_prior: float,
            ) -> tuple[float, float]:
                # Prefer the team's relevant venue split; fall back to all recent
                # matches only when no venue-specific sample exists.
                relevant = [row for row in history if row[2] == venue] or history
                weight = len(relevant) / (len(relevant) + 4.0)
                scored = sum(row[0] for row in relevant) / len(relevant)
                conceded = sum(row[1] for row in relevant) / len(relevant)
                return (
                    weight * scored + (1 - weight) * scored_prior,
                    weight * conceded + (1 - weight) * conceded_prior,
                )

            # Home-team home performance and away-team away performance are
            # estimated separately, with venue-appropriate league priors.
            home_scored, home_conceded = shrunk_venue_rates(
                home_hist, "home", home_baseline, away_baseline
            )
            away_scored, away_conceded = shrunk_venue_rates(
                away_hist, "away", away_baseline, home_baseline
            )
            home_xg = home_baseline * (home_scored / home_baseline) * (away_conceded / home_baseline)
            away_xg = away_baseline * (away_scored / away_baseline) * (home_conceded / away_baseline)
            home_xg = min(5.0, max(0.05, home_xg))
            away_xg = min(5.0, max(0.05, away_xg))
            probabilities = match_probabilities(home_xg, away_xg)
            elo_probabilities, elo_metadata = _elo_probabilities(
                usable,
                fixture["home_team"],
                fixture["away_team"],
                fixture.get("division_code"),
                min_team_matches=min_team_matches,
                cache=elo_cache,
            )
            record.update({
                "status": "EXPERIMENTAL_ONLY",
                "elo_model": (
                    "experimental_elo_by_competition"
                    if elo_metadata["scope"] == "COMPETITION"
                    else "experimental_elo_global_fallback"
                ),
                "elo_history": elo_metadata,
                **({"elo_probabilities": {
                    key: round(value, 4) for key, value in elo_probabilities.items()
                }} if elo_probabilities is not None else {}),
                "expected_goals": {"home": round(home_xg, 3), "away": round(away_xg, 3)},
                "probabilities": {
                    key: round(value, 4)
                    for key, value in probabilities["one_x_two"].items()
                },
                "btts_yes": round(probabilities["btts_yes"], 4),
                "over_2_5": round(probabilities["totals"]["over_2_5"], 4),
                "most_likely_scorelines": probabilities["most_likely_scorelines"][:3],
                "limitations": [
                    "Not validated for betting.",
                    "Historical dataset coverage and team-name matching may be incomplete.",
                    "Primary Poisson model uses global scoring priors and no current odds.",
                    "The primary Poisson model underperforms the historical market benchmark.",
                    "The Elo alternative is experimental and is tracked separately; its live paper performance is not yet established.",
                ],
            })
            output.append(record)
    return output


def build_daily_report(
    fixtures_payload: dict[str, Any],
    history_path: str | Path,
    *,
    as_of: date | None = None,
    timezone_name: str = "Africa/Lagos",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a daily report with explicit fixture-filter diagnostics."""
    fixtures = fixtures_payload.get("response")
    if not isinstance(fixtures, list):
        raise ValueError("Fixture API payload is missing a response list.")
    try:
        local_zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {timezone_name}") from exc
    current_time = now or datetime.now(local_zone)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=local_zone)
    current_time = current_time.astimezone(local_zone)
    target_date = as_of or current_time.date()

    parsed_for_date = [
        part for item in fixtures
        if (part := _fixture_parts(item, timezone_name))
        and part["kickoff_date"] == target_date
    ]
    past_kickoffs = sum(
        part["kickoff_datetime"] <= current_time for part in parsed_for_date
    )
    future_kickoffs = sum(
        part["kickoff_datetime"] > current_time for part in parsed_for_date
    )
    historical = load_historical_matches(history_path)
    predictions = predict_fixtures(
        fixtures,
        historical,
        as_of=target_date,
        timezone_name=timezone_name,
        now=current_time,
    )
    return {
        "product": "Veltrix Football",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": target_date.isoformat(),
        "timezone": timezone_name,
        "same_day_only": True,
        "model_status": "EXPERIMENTAL_NOT_VALIDATED",
        "fixtures_received": len(fixtures),
        "same_day_pre_match_fixtures": len(parsed_for_date),
        "past_kickoffs_excluded": past_kickoffs,
        "future_fixtures_considered": future_kickoffs,
        "fixtures_excluded_other_date_or_status": len(fixtures) - len(parsed_for_date),
        "predictions_created": sum(p["status"] == "EXPERIMENTAL_ONLY" for p in predictions),
        "insufficient_history": sum(p["status"] == "INSUFFICIENT_HISTORY" for p in predictions),
        "possible_team_name_mismatches": sum(bool(p.get("team_name_match_suggestions")) for p in predictions),
        "normal_bets": {"target_combined_decimal_odds": 10.0, "status": "NOT_GENERATED_MODEL_NOT_VALIDATED"},
        "value_bets": {"target_combined_decimal_odds": [50.0, 100.0], "status": "NOT_GENERATED_MODEL_NOT_VALIDATED"},
        "predictions": predictions,
        "notice": "Experimental research output only. The primary Poisson pipeline underperforms the market benchmark and is unvalidated for betting. The Elo alternative is experimental and is being tracked separately. No betting recommendations or value bets are approved.",
    }
