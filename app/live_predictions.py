"""Experimental fixture-to-prediction pipeline using completed historical scores.

This is a research baseline, not a validated betting model. It never labels
outputs as value bets and refuses teams with too little historical data.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from difflib import get_close_matches
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from typing import Any, Iterable

from app.prediction import match_probabilities
from app.advanced_models import dixon_coles_1x2, recency_weighted_mean, rest_congestion_context

MIN_TEAM_MATCHES = 5
TEAM_WINDOW = 10
HOME_ELO_ADVANTAGE = 55.0
ELO_K = 20.0

# API-Football league IDs mapped to division codes in the open historical CSV.
LEAGUE_DIVISION_BY_CODE = {
    "PL": "E0", "ELC": "E1", "EL1": "E2", "EL2": "E3",
    "PD": "SP1", "SD": "SP2", "SA": "I1", "SB": "I2",
    "BL1": "D1", "BL2": "D2", "FL1": "F1", "FL2": "F2",
    "DED": "N1", "PPL": "P1", "SPL": "SC0", "BSA": "B1",
}
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
    """Normalize common provider naming wrappers and explicit club aliases.

    Only generic legal/club markers at the edges are stripped. Ambiguous
    fuzzy matches remain suggestions only; a wrong team merge is worse than
    withholding a forecast.
    """
    normalized = unicodedata.normalize("NFKD", str(name or "").casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    # Preserve a small set of letters that NFKD does not decompose consistently.
    normalized = normalized.replace("ø", "o").replace("ł", "l").replace("đ", "d").replace("ð", "d").replace("þ", "th")
    tokens = re.findall(r"[a-z0-9]+", normalized)
    edge_markers = {"fc", "afc", "cf", "sc", "ac", "as", "ec", "sbv", "acf", "cd", "ud", "bc"}
    while tokens and tokens[0] in edge_markers:
        tokens.pop(0)
    while tokens and tokens[-1] in edge_markers:
        tokens.pop()
    key = "".join(tokens)
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
        "bayern": "bayernmunich",
        "bayernmunchen": "bayernmunich",
        "juve": "juventus",
        "atleticomadrid": "atleticodemadrid",
        "athleticomadrid": "atleticodemadrid",
        "athmadrid": "atleticodemadrid",
        "newcastleutd": "newcastleunited",
        "westham": "westhamunited",
        "westhamutd": "westhamunited",
        "athleticclub": "athleticbilbao",
        "athbilbao": "athleticbilbao",
        "internazionale": "intermilan",
        "internazionalemilano": "intermilan",
        "inter": "intermilan",
        "psveindhoven": "psv",
        "feyenoordrotterdam": "feyenoord",
        "nec": "necnijmegen",
        # Exact provider abbreviations observed in API-Sports/fixture feeds.
        "argentinosjrs": "argentinosjuniors",
        "independrivadavia": "independienterivadavia",
    }
    return aliases.get(key, key)


def _team_variant_signature(key: str) -> tuple[str, ...]:
    """Identify squad/category markers that must never be erased by fuzzy matching."""
    markers: list[str] = []
    # Several fixture feeds abbreviate squad type as a single trailing letter:
    # "(W)" for women's sides and "(R)" for reserve sides. Those markers must
    # survive normalization so fuzzy matching cannot merge them with senior men.
    for label, pattern in (
        ("women", r"(?:women|womens|ladies|feminin|femenino|feminino|w)$"),
        ("youth", r"(?:youth|academy|junior|juniors)$"),
        ("age_group", r"u(?:1[0-9]|2[0-3])$"),
        ("reserve", r"(?:reserves|reserve|bteam|ii|iii|iv|b|2|3|r)$"),
    ):
        if re.search(pattern, key):
            markers.append(label)
    # Distinguish different age groups and reserve levels, not just their category.
    age = re.search(r"u(1[0-9]|2[0-3])$", key)
    if age:
        markers.append("u" + age.group(1))
    reserve = re.search(r"(?:reserves|reserve|bteam|ii|iii|iv|b|2|3|r)$", key)
    if reserve:
        markers.append(reserve.group(0))
    return tuple(markers)


def _one_edit_apart(left: str, right: str) -> bool:
    """Allow one obvious spelling typo, not broad similarity between different clubs."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = sum(a != b for a, b in zip(left, right))
        if differences == 1:
            return True
        # Accept one adjacent transposition, a common typing/provider variant.
        for index in range(len(left) - 1):
            if (
                left[index] == right[index + 1]
                and left[index + 1] == right[index]
                and left[:index] == right[:index]
                and left[index + 2:] == right[index + 2:]
            ):
                return True
        return False
    shorter, longer = (left, right) if len(left) < len(right) else (right, left)
    # A dropped first character often represents a club initial or abbreviated
    # prefix (e.g. "R. Santander"), not a spelling typo. Do not merge it
    # automatically with the longer club name.
    if longer[1:] == shorter:
        return False
    i = j = edits = 0
    while i < len(shorter) and j < len(longer):
        if shorter[i] == longer[j]:
            i += 1
            j += 1
        else:
            edits += 1
            j += 1
            if edits > 1:
                return False
    return True


def _resolve_team_key(name: Any, known_keys: Iterable[str]) -> str:
    """Resolve only one-character spelling variants; never cross squad boundaries.

    Exact normalized keys and explicit aliases win. Fuzzy guesses that can merge
    different clubs are deliberately withheld, even if the names look similar.
    """
    key = _name_key(name)
    candidates = list(set(known_keys))
    if key in candidates or not candidates:
        return key
    signature = _team_variant_signature(key)
    compatible = [
        candidate for candidate in candidates
        if _team_variant_signature(candidate) == signature
        and _one_edit_apart(key, candidate)
    ]
    # If more than one historical team is one edit away, the identity is ambiguous.
    return compatible[0] if len(compatible) == 1 else key


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
        # League IDs are provider-local. The ID map above contains API-Football
        # IDs only; never apply it to 5Dollar/other-provider IDs, which can collide
        # with an unrelated senior division and falsely enable unsupported leagues.
        "division_code": (
            LEAGUE_DIVISION_BY_CODE.get(str(league.get("code") or "").upper())
            or (
                LEAGUE_DIVISION_BY_ID.get(league.get("id"))
                if not item.get("_veltrix_source")
                or str(item.get("_veltrix_source")).casefold() in {"api-football", "api-sports"}
                else None
            )
        ),
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
    known_keys = set(match_counts)
    home_key = _resolve_team_key(home_name, known_keys)
    away_key = _resolve_team_key(away_name, known_keys)
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

    # Cache Elo ratings once per competition for this report date; all fixtures
    # share the same strictly pre-date history, so recomputing it per fixture is wasteful.
    elo_cache: dict[str, dict[str, Any]] = {}
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
            known_keys = set(team_history)
            home_key = _resolve_team_key(fixture["home_team"], known_keys)
            away_key = _resolve_team_key(fixture["away_team"], known_keys)
            home_hist, away_hist = list(team_history[home_key]), list(team_history[away_key])
            record: dict[str, Any] = {
                **{k: v for k, v in fixture.items() if k not in {"kickoff_date", "kickoff_datetime"}},
                "model": "experimental_recent_goals_poisson",
                "model_validated": False,
                "betting_recommendation": False,
                "historical_matches": {"home": len(home_hist), "away": len(away_hist)},
                "team_name_matches": {
                    "home": {"fixture_name": fixture["home_team"], "historical_key": home_key,
                             "auto_matched": home_key != _name_key(fixture["home_team"])},
                    "away": {"fixture_name": fixture["away_team"], "historical_key": away_key,
                             "auto_matched": away_key != _name_key(fixture["away_team"])},
                },
            }
            if len(home_hist) < min_team_matches or len(away_hist) < min_team_matches:
                if not fixture.get("division_code"):
                    record.update({
                        "status": "UNSUPPORTED_COMPETITION",
                        "reason": "This competition is not mapped to the historical dataset and the teams do not have enough exact-match history for a safe global estimate.",
                        "team_name_match_suggestions": {},
                    })
                    output.append(record)
                    continue
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

            # Research-only alternative: exponentially weighted recent venue form
            # plus the Dixon-Coles low-score correction. Keep it separate from the
            # production primary until walk-forward metrics justify promotion.
            def weighted_venue_rates(
                history: list[tuple[int, int, str]],
                venue: str,
                scored_prior: float,
                conceded_prior: float,
            ) -> tuple[float, float]:
                relevant = [row for row in history if row[2] == venue] or history
                weight = len(relevant) / (len(relevant) + 4.0)
                scored = recency_weighted_mean([row[0] for row in relevant], decay=0.85)
                conceded = recency_weighted_mean([row[1] for row in relevant], decay=0.85)
                return (
                    weight * scored + (1 - weight) * scored_prior,
                    weight * conceded + (1 - weight) * conceded_prior,
                )

            weighted_home_scored, weighted_home_conceded = weighted_venue_rates(
                home_hist, "home", home_baseline, away_baseline
            )
            weighted_away_scored, weighted_away_conceded = weighted_venue_rates(
                away_hist, "away", away_baseline, home_baseline
            )
            weighted_home_xg = min(5.0, max(0.05,
                home_baseline * (weighted_home_scored / home_baseline)
                * (weighted_away_conceded / home_baseline)
            ))
            weighted_away_xg = min(5.0, max(0.05,
                away_baseline * (weighted_away_scored / away_baseline)
                * (weighted_home_conceded / away_baseline)
            ))
            dixon_coles_probabilities = {
                key: round(value, 4)
                for key, value in dixon_coles_1x2(
                    weighted_home_xg, weighted_away_xg, rho=-0.05
                ).items()
            }

            elo_probabilities, elo_metadata = _elo_probabilities(
                usable,
                fixture["home_team"],
                fixture["away_team"],
                fixture.get("division_code"),
                min_team_matches=min_team_matches,
                cache=elo_cache,
            )
            poisson_probabilities = {
                key: round(value, 4)
                for key, value in probabilities["one_x_two"].items()
            }
            elo_model = (
                "experimental_elo_by_competition"
                if elo_metadata["scope"] == "COMPETITION"
                else "experimental_elo_global_fallback"
            )
            use_competition_elo = (
                elo_probabilities is not None and elo_metadata["scope"] == "COMPETITION"
            )
            primary_model = elo_model if use_competition_elo else "experimental_recent_goals_poisson"
            primary_probabilities = (
                {key: round(value, 4) for key, value in elo_probabilities.items()}
                if use_competition_elo else poisson_probabilities
            )
            record.update({
                "status": "EXPERIMENTAL_ONLY",
                "model": primary_model,
                "probabilities": primary_probabilities,
                "elo_history": elo_metadata,
                "expected_goals": {"home": round(home_xg, 3), "away": round(away_xg, 3)},
                "rest_congestion_context": rest_congestion_context(
                    usable, home_key, away_key, target_date, window_days=14
                ),
                "advanced_model_alternative": {
                    "model": "experimental_recency_weighted_dixon_coles",
                    "model_validated": False,
                    "rho": -0.05,
                    "expected_goals": {
                        "home": round(weighted_home_xg, 3),
                        "away": round(weighted_away_xg, 3),
                    },
                    "probabilities": dixon_coles_probabilities,
                    "status": "RESEARCH_ONLY_NOT_PRIMARY",
                },
                "data_availability": {
                    "historical_goals_for_against": "AVAILABLE",
                    "competition_elo": "AVAILABLE" if elo_probabilities is not None else "INSUFFICIENT_HISTORY",
                    "true_expected_goals_xg": "UNAVAILABLE_FROM_CURRENT_HISTORICAL_FEED",
                    "confirmed_lineups_injuries_suspensions": "NOT_CONNECTED",
                    "rest_and_fixture_congestion": "CONTEXT_ONLY_NOT_USED_IN_PROBABILITIES",
                    "live_bookmaker_odds": "NOT_FETCHED_IN_THIS_RUN_API_FOOTBALL_ODDS_ENRICHMENT_NOT_CONFIRMED",
                },
                "goal_markets_model": "experimental_recent_goals_poisson",
                "scoreline_model": "experimental_recent_goals_poisson",
                "btts_yes": round(probabilities["btts_yes"], 4),
                "over_2_5": round(probabilities["totals"]["over_2_5"], 4),
                "most_likely_scorelines": probabilities["most_likely_scorelines"][:3],
                **({
                    "poisson_model": "experimental_recent_goals_poisson",
                    "poisson_probabilities": poisson_probabilities,
                } if use_competition_elo else {}),
                **({
                    "elo_model": elo_model,
                    "elo_probabilities": {
                        key: round(value, 4) for key, value in elo_probabilities.items()
                    },
                } if elo_probabilities is not None and not use_competition_elo else {}),
                "limitations": [
                    "Not validated for betting.",
                    "Historical dataset coverage and team-name matching may be incomplete.",
                    "The recent-goals Poisson model underperforms the historical market benchmark.",
                    "Competition-specific Elo is selected as primary only when the fixture maps to a supported historical division and has sufficient team history.",
                    "Expected goals and totals remain auxiliary Poisson estimates when Elo is primary.",
                    "Elo and Poisson paper results are tracked separately; neither is approved for betting.",
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
    additional_historical_matches: list[dict[str, Any]] | None = None,
    base_historical_matches: list[dict[str, Any]] | None = None,
    market_odds_by_fixture: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a daily report with explicit fixture-filter and history-freshness diagnostics."""
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
    historical = list(base_historical_matches) if base_historical_matches is not None else load_historical_matches(history_path)
    if additional_historical_matches:
        existing = {
            (row["date"].isoformat(), row.get("division", ""), row["home_key"], row["away_key"])
            for row in historical
        }
        for row in additional_historical_matches:
            if row.get("date") >= target_date:
                continue
            key = (
                row["date"].isoformat(), row.get("division", ""),
                row["home_key"], row["away_key"],
            )
            if key not in existing:
                historical.append(row)
                existing.add(key)
        historical.sort(key=lambda row: row["date"])
    predictions = predict_fixtures(
        fixtures,
        historical,
        as_of=target_date,
        timezone_name=timezone_name,
        now=current_time,
    )
    if market_odds_by_fixture:
        eligible_statuses = {"EXPERIMENTAL_ONLY", "INSUFFICIENT_HISTORY", "UNSUPPORTED_COMPETITION"}
        for prediction in predictions:
            if prediction.get("status") not in eligible_statuses:
                continue
            odds = market_odds_by_fixture.get(prediction.get("fixture_id"))
            if not odds:
                continue
            prediction["market_model"] = odds.get("model", "market_consensus")
            prediction["market_probabilities"] = odds.get("probabilities")
            prediction["market_bookmakers_count"] = odds.get("bookmakers_count", 0)
            prediction["market_updated_at"] = odds.get("updated_at")
            prediction["market_method"] = odds.get("method")
    return {
        "product": "Veltrix Football",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "as_of_date": target_date.isoformat(),
        "timezone": timezone_name,
        "same_day_only": True,
        "model_status": "EXPERIMENTAL_NOT_VALIDATED",
        "historical_matches_available": sum(row["date"] < target_date for row in historical),
        "historical_data_through": max(
            (row["date"].isoformat() for row in historical if row["date"] < target_date),
            default=None,
        ),
        "fixtures_received": len(fixtures),
        "same_day_pre_match_fixtures": len(parsed_for_date),
        "past_kickoffs_excluded": past_kickoffs,
        "future_fixtures_considered": future_kickoffs,
        "fixtures_excluded_other_date_or_status": len(fixtures) - len(parsed_for_date),
        "predictions_created": sum(p["status"] == "EXPERIMENTAL_ONLY" for p in predictions),
        "insufficient_history": sum(p["status"] == "INSUFFICIENT_HISTORY" for p in predictions),
        "unsupported_competitions": sum(p["status"] == "UNSUPPORTED_COMPETITION" for p in predictions),
        "fixtures_with_market_odds": sum(
            isinstance(p.get("market_probabilities"), dict) for p in predictions
        ),
        "unsupported_competition_breakdown": {
            str(league_name): sum(
                p.get("status") == "UNSUPPORTED_COMPETITION" and p.get("league") == league_name
                for p in predictions
            )
            for league_name in sorted({
                p.get("league") for p in predictions
                if p.get("status") == "UNSUPPORTED_COMPETITION" and p.get("league")
            })
        },
        "possible_team_name_mismatches": sum(
            bool(p.get("team_name_match_suggestions"))
            or any(
                bool(side.get("auto_matched"))
                for side in (p.get("team_name_matches") or {}).values()
                if isinstance(side, dict)
            )
            for p in predictions
        ),
        "primary_model_counts": {
            model_name: sum(
                p.get("status") == "EXPERIMENTAL_ONLY" and p.get("model") == model_name
                for p in predictions
            )
            for model_name in sorted({
                str(p.get("model")) for p in predictions
                if p.get("status") == "EXPERIMENTAL_ONLY" and p.get("model")
            })
        },
        "poisson_alternative_available": sum(
            p.get("status") == "EXPERIMENTAL_ONLY" and isinstance(p.get("poisson_probabilities"), dict)
            for p in predictions
        ),
        "elo_alternative_available": sum(
            p.get("status") == "EXPERIMENTAL_ONLY" and isinstance(p.get("elo_probabilities"), dict)
            for p in predictions
        ),
        "normal_bets": {"target_combined_decimal_odds": 10.0, "status": "NOT_GENERATED_MODEL_NOT_VALIDATED"},
        "value_bets": {"target_combined_decimal_odds": [50.0, 100.0], "status": "NOT_GENERATED_MODEL_NOT_VALIDATED"},
        "predictions": predictions,
        "notice": "Experimental research output only. Historical tests show the Poisson pipeline underperforms the market benchmark. Competition-scoped Elo is preferred when available but remains unvalidated for betting; Poisson remains primary when Elo history is unavailable. No betting recommendations or value bets are approved.",
    }
