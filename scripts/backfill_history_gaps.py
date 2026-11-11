# Current-day delivery replay marker: 2026-11-02 verification attempt 2.
# Live report verification trigger marker: [run-live-verification]
"""Retry known historical result gaps and publish only verified recovered scores."""
# [run-openligadb-backfill] One-shot recovery pass after canonical shortcut mapping.
# ODbL provenance is recorded per row; partial OpenLigaDB coverage never clears global gaps.
# One-shot ODbL supplement after merging static and discovered competition shortcuts [run-openligadb-backfill].
# ODbL-only recovery trigger [run-openligadb-backfill]; preserve the 5Dollar cooldown.
# Controlled live refresh request after the 378-test regression pass [run-live-verification] [skip-telegram].
# Explicit recovery-run marker: [run-gap-backfill]
# 2026-11-02 forced one-shot historical gap recovery: [run-gap-backfill]
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
import time as time_module
import re
import unicodedata
import io
import requests
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

from app.provider_adapters import FiveDollarFootballClient, ProviderAPIError, LEAGUE_CODES
from app.recent_results import extract_completed_results
from scripts.publish_command_data import publish
from app.fixture_history_utils import _name_key


def _mapped_league_division(league: dict[str, Any]) -> str | None:
    """Resolve provider league names even when country/short-name labels vary."""
    nested = league.get("league") if isinstance(league.get("league"), dict) else {}
    candidates = [
        league.get("name"), league.get("league_name"), nested.get("name"),
        league.get("short_name"), league.get("code"),
    ]
    inverse = {str(code).casefold(): str(code) for code in LEAGUE_CODES.values()}
    aliases = {"epl": "PL", "ll": "PD", "sa": "SA", "bl1": "BL1", "fl1": "FL1"}
    for value in candidates:
        raw = str(value or "").strip()
        if not raw:
            continue
        normalized = unicodedata.normalize("NFKD", raw.casefold())
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
        if normalized in LEAGUE_CODES:
            return LEAGUE_CODES[normalized]
        compact = normalized.replace(" ", "")
        if compact in aliases:
            return aliases[compact]
        if compact in inverse:
            return inverse[compact]
        # Provider labels sometimes prefix the country or tier. Match only a
        # complete mapped competition phrase, not a loose substring.
        for name, division in sorted(LEAGUE_CODES.items(), key=lambda item: len(item[0]), reverse=True):
            if normalized == name or normalized.endswith(" " + name) or normalized.startswith(name + " "):
                return division
    return None



OPEN_MATCHDAY_BASE = "https://raw.githubusercontent.com/oladeeayo/open-matchday/master"
OPEN_MATCHDAY_DIVISIONS = {
    "E0": "ENG_1_premier-league", "E1": "ENG_2_championship",
    "E2": "ENG_3_league-one", "E3": "ENG_4_league-two",
    "EC": "ENG_5_national-league", "SC0": "SCO_1_premiership",
    "SC1": "SCO_2_championship", "SC2": "SCO_3_league-one",
    "SC3": "SCO_4_league-two", "D1": "GER_1_bundesliga",
    "D2": "GER_2_2-bundesliga", "I1": "ITA_1_serie-a",
    "I2": "ITA_2_serie-b", "SP1": "ESP_1_la-liga",
    "SP2": "ESP_2_segunda-division", "F1": "FRA_1_ligue-1",
    "F2": "FRA_2_ligue-2", "N1": "NED_1_eredivisie",
    "B1": "BEL_1_pro-league", "P1": "POR_1_primeira-liga",
    "T1": "TUR_1_super-lig", "G1": "GRE_1_super-league",
    "SWE": "SWE_1_allsvenskan", "BSA": "BRA_1_serie-a",
    "ARG": "ARG_1_liga-profesional",
}


def _open_matchday_backfill(session: Any, gaps: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Do not ingest a source whose published terms prohibit commercial use."""
    return [], {
        "provider": "open-matchday",
        "season": "2627",
        "status": "SKIPPED_NONCOMMERCIAL_LICENSE",
        "files_requested": 0,
        "files_verified": 0,
        "files_failed": [],
        "matches_added": 0,
        "resolved_dates": [],
        "attribution": "oladeeayo/open-matchday",
        "source_terms": "Non-commercial restriction; excluded from the VELTRIX production/training dataset.",
    }

def _fallback_rows(path: Path, gaps: set[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for raw in csv.DictReader(handle):
            day = str(raw.get("match_date") or "")[:10]
            if day not in gaps:
                continue
            try:
                hg, ag = int(raw["home_goals"]), int(raw["away_goals"])
                home, away = str(raw["home_team"]).strip(), str(raw["away_team"]).strip()
                if not home or not away or hg < 0 or ag < 0 or _name_key(home) == _name_key(away):
                    continue
            except (KeyError, TypeError, ValueError):
                continue
            rows.append({
                "date": day, "division": str(raw.get("division") or ""),
                "home": home, "away": away, "home_goals": hg, "away_goals": ag,
                "fixture_id": None, "fixture_status": "FT",
                "source_provider": "football-data.co.uk",
            })
    return rows


OPENLIGADB_LEAGUES = (
    {"shortcut": "pl", "division": "E0", "name": "Premier League"},
    {"shortcut": "la1", "division": "SP1", "name": "La Liga"},
    {"shortcut": "bl1", "division": "D1", "name": "Bundesliga"},
    {"shortcut": "ucl", "division": "UCL", "name": "UEFA Champions League"},
    {"shortcut": "bl2", "division": "D2", "name": "2. Bundesliga"},
    {"shortcut": "bl3", "division": "D3", "name": "3. Liga"},
    {"shortcut": "dfb", "division": "DFB", "name": "DFB-Pokal"},
    {"shortcut": "uel2026", "division": "UEL", "name": "UEFA Europa League"},
    {"shortcut": "uecl2026", "division": "UECL", "name": "UEFA Conference League"},
    {"shortcut": "unl", "division": "UNL", "name": "UEFA Nations League"},
    {"shortcut": "BLÖ", "division": "AUT1", "name": "Austrian Bundesliga"},
)
OPENLIGADB_CANONICAL_SHORTCUT_BY_DIVISION = {
    row["division"]: str(row["shortcut"]).casefold() for row in OPENLIGADB_LEAGUES
}
OPENLIGADB_DIVISION_BY_SHORTCUT = {
    str(row["shortcut"]).casefold(): row["division"] for row in OPENLIGADB_LEAGUES
}
OPENLIGADB_DIVISION_BY_NAME = {
    "premier league": "E0", "english premier league": "E0", "england premier league": "E0",
    "la liga": "SP1", "laliga": "SP1", "spain la liga": "SP1",
    "bundesliga": "D1", "1 bundesliga": "D1", "germany bundesliga": "D1", "2 bundesliga": "D2",
    "serie a": "I1", "italy serie a": "I1", "serie b": "I2", "italy serie b": "I2",
    "ligue 1": "F1", "france ligue 1": "F1", "ligue 2": "F2", "france ligue 2": "F2",
    "eredivisie": "N1", "netherlands eredivisie": "N1",
    "primeira liga": "P1", "liga portugal": "P1", "portugal primeira liga": "P1",
    "scottish premiership": "SC0", "scotland premiership": "SC0",
    "brasileirao": "BSA", "brazilian serie a": "BSA", "brazil brasileirao": "BSA",
    "allsvenskan": "SWE", "sweden allsvenskan": "SWE",
    "belgian pro league": "B1", "jupiler pro league": "B1", "belgium pro league": "B1",
    "super lig": "T1", "turkish super lig": "T1", "turkey super lig": "T1",
    "uefa champions league": "UCL", "champions league": "UCL",
    "uefa europa league": "UEL", "europa league": "UEL",
    "championship": "E1", "english championship": "E1",
    "league one": "E2", "english league one": "E2",
    "league two": "E3", "english league two": "E3",
    "scottish championship": "SC1", "scottish league one": "SC2",
    "scottish league two": "SC3",
    "segunda division": "SP2", "la liga 2": "SP2",
    "greek super league": "G1",
}


def _openligadb_division(league: dict[str, Any]) -> str | None:
    raw = str(league.get("leagueName") or league.get("name") or "").strip()
    normalized = unicodedata.normalize("NFKD", raw.casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    shortcut = str(league.get("leagueShortcut") or "").strip().casefold()
    return OPENLIGADB_DIVISION_BY_SHORTCUT.get(shortcut) or OPENLIGADB_DIVISION_BY_NAME.get(normalized)


def _openligadb_available_leagues(session: Any, season: int = 2026) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url = f"https://api.openligadb.de/getavailableleagues/{season}"
    audit = {"url": url, "status": "NOT_REQUESTED", "available_count": 0, "mapped_count": 0, "unmapped_count": 0}
    try:
        response = session.get(url, timeout=30, headers={"User-Agent": "VELTRIX-FOOTBALL/1.0"})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("OpenLigaDB available-leagues response was not a JSON list.")
        audit["available_count"] = len(payload)
        mapped_candidates = []
        unmapped = []
        audit["sample_leagues"] = [
            {
                "shortcut": str(item.get("leagueShortcut") or ""),
                "name": str(item.get("leagueName") or item.get("name") or ""),
                "season": str(item.get("leagueSeason") or ""),
            }
            for item in payload[:100] if isinstance(item, dict)
        ]
        for item in payload:
            if not isinstance(item, dict):
                continue
            league_season = str(item.get("leagueSeason") or season).strip()
            if league_season and not (
                league_season == str(season)
                or league_season.startswith(f"{season}/")
                or league_season.startswith(f"{season}-")
            ):
                continue
            shortcut = str(item.get("leagueShortcut") or "").strip()
            division = _openligadb_division(item)
            name = str(item.get("leagueName") or item.get("name") or "").strip()
            if not shortcut or not division:
                unmapped.append({"shortcut": shortcut or None, "name": name or None})
                continue
            canonical = OPENLIGADB_CANONICAL_SHORTCUT_BY_DIVISION.get(division)
            if canonical and shortcut.casefold() != canonical:
                continue
            mapped_candidates.append({"shortcut": shortcut, "division": division, "name": name})
        mapped_candidates.sort(key=lambda row: (row["division"], row["shortcut"]))
        mapped, seen_divisions = [], set()
        for row in mapped_candidates:
            if row["division"] in seen_divisions:
                continue
            seen_divisions.add(row["division"])
            mapped.append(row)
        discovered_mapped_count = len(mapped)
        # The API discovery endpoint has incomplete season metadata. Preserve
        # known canonical IDs even when its list omits them.
        for fallback in OPENLIGADB_LEAGUES:
            if fallback["division"] not in seen_divisions:
                mapped.append(dict(fallback))
                seen_divisions.add(fallback["division"])
        mapped.sort(key=lambda row: (row["division"], row["shortcut"]))
        audit["mapped_count"] = len(mapped)
        audit["discovered_mapped_count"] = discovered_mapped_count
        audit["unmapped_count"] = max(0, audit["available_count"] - discovered_mapped_count)
        audit["unmapped_name_sample"] = unmapped[:40]
        audit["status"] = "MAPPED_LEAGUES_FOUND" if mapped else "NO_MAPPED_LEAGUES"
        return mapped, audit
    except requests.HTTPError as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        audit.update({"status": "HTTP_ERROR", "status_code": status_code, "error_type": "HTTPError"})
        return [], audit
    except (requests.RequestException, ValueError, TypeError) as exc:
        audit.update({"status": "DISCOVERY_ERROR", "error_type": type(exc).__name__})
        return [], audit
OPENLIGADB_LICENSE = "ODbL-1.0"
OPENLIGADB_LICENSE_URL = "https://opendatacommons.org/licenses/odbl/1-0/"
OPENLIGADB_ATTRIBUTION = "OpenLigaDB community-maintained football data, licensed under ODbL 1.0"


def _openligadb_gap_backfill(session: Any, gaps: list[str], delay_seconds: float = 10.0) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch finished scores from OpenLigaDB with explicit ODbL provenance.

    This is a partial source only: it never clears a global date gap because
    its competition coverage is narrower than VELTRIX's complete target set.
    """
    audit: dict[str, Any] = {
        "provider": "OpenLigaDB", "season": 2026, "license": OPENLIGADB_LICENSE,
        "license_url": OPENLIGADB_LICENSE_URL, "attribution": OPENLIGADB_ATTRIBUTION,
        "source_home": "https://www.openligadb.de/", "status": "NOT_REQUESTED",
        "competitions": [], "matches_found": 0, "matches_added": 0,
        "dates_covered": [], "date_coverage": [], "resolved_dates": [],
        "request_delay_seconds": delay_seconds, "global_gap_resolution": False,
    }
    gap_set = set(gaps)
    if not gap_set:
        return [], audit
    own_session = session is None
    client = session or requests.Session()
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    rate_limited = False
    try:
        leagues = list(OPENLIGADB_LEAGUES)
        if own_session:
            discovered, discovery_audit = _openligadb_available_leagues(client, 2026)
            audit["available_leagues_discovery"] = discovery_audit
            if discovered:
                # Keep the known cross-competition shortcuts and merge API
                # discoveries; the season catalogue can be incomplete or use
                # alternate/test shortcuts for a given season.
                by_shortcut = {item["shortcut"]: item for item in OPENLIGADB_LEAGUES}
                by_shortcut.update({item["shortcut"]: item for item in discovered})
                leagues = sorted(by_shortcut.values(), key=lambda row: (row["division"], row["shortcut"]))
            elif discovery_audit.get("status") == "HTTP_ERROR" and discovery_audit.get("status_code") == 429:
                rate_limited = True
                leagues = []
        else:
            audit["available_leagues_discovery"] = {
                "status": "SKIPPED_INJECTED_TEST_SESSION",
                "available_count": 0, "mapped_count": len(leagues),
            }
        audit["mapped_competitions"] = [
            {"shortcut": item["shortcut"], "division": item["division"], "name": item["name"]}
            for item in leagues
        ]
        for index, league in enumerate(leagues):
            if own_session and index and delay_seconds > 0:
                time_module.sleep(delay_seconds)
            url = f"https://api.openligadb.de/getmatchdata/{league['shortcut']}/2026"
            competition = {
                "shortcut": league["shortcut"], "division": league["division"],
                "name": league["name"], "url": url, "status": "NOT_CHECKED",
                "total_matches": 0, "finished_matches": 0,
                "gap_date_matches": 0, "full_time_candidates": 0,
                "matches_found": 0, "date_range": None,
            }
            try:
                response = client.get(
                    url, timeout=30,
                    headers={"User-Agent": "VELTRIX-FOOTBALL/1.0 (https://github.com/Nexora-Apparel/veltrix-football)"},
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ValueError("OpenLigaDB season response was not a JSON list.")
                competition["total_matches"] = len(payload)
                season_dates = [
                    str(match.get("matchDateTimeUTC") or match.get("matchDateTime") or "")[:10]
                    for match in payload if isinstance(match, dict)
                ]
                season_dates = [day for day in season_dates if len(day) == 10]
                if season_dates:
                    competition["date_range"] = [min(season_dates), max(season_dates)]

                for match in payload:
                    if not isinstance(match, dict):
                        continue
                    if match.get("matchIsFinished") is True:
                        competition["finished_matches"] += 1
                    kickoff = str(match.get("matchDateTimeUTC") or match.get("matchDateTime") or "")
                    day = kickoff[:10]
                    if day not in gap_set:
                        continue
                    competition["gap_date_matches"] += 1
                    if match.get("matchIsFinished") is not True:
                        continue

                    results = match.get("matchResults") if isinstance(match.get("matchResults"), list) else []
                    has_semantic_kind = any(
                        isinstance(result, dict) and result.get("resultTypeKind")
                        for result in results
                    )
                    full_time = next((
                        result for result in results
                        if isinstance(result, dict) and result.get("resultTypeKind") == "After90Minutes"
                    ), None)
                    # Legacy league records predate resultTypeKind. Only in
                    # those records is resultTypeID==2 a safe 90-minute proxy.
                    if not full_time and not has_semantic_kind:
                        full_time = next((
                            result for result in results
                            if isinstance(result, dict) and str(result.get("resultTypeID")) == "2"
                        ), None)
                    if not full_time:
                        continue
                    competition["full_time_candidates"] += 1
                    home_obj = match.get("team1") if isinstance(match.get("team1"), dict) else {}
                    away_obj = match.get("team2") if isinstance(match.get("team2"), dict) else {}
                    home = str(home_obj.get("teamName") or "").strip()
                    away = str(away_obj.get("teamName") or "").strip()
                    try:
                        home_goals = int(full_time["pointsTeam1"])
                        away_goals = int(full_time["pointsTeam2"])
                        date.fromisoformat(day)
                    except (KeyError, TypeError, ValueError):
                        continue
                    if not home or not away or _name_key(home) == _name_key(away):
                        continue
                    key = (day, league["division"], _name_key(home), _name_key(away))
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "date": day, "division": league["division"],
                        "home": home, "away": away,
                        "home_goals": home_goals, "away_goals": away_goals,
                        "fixture_id": match.get("matchID"), "fixture_status": "FT",
                        "source_provider": "OpenLigaDB",
                        "source_license": OPENLIGADB_LICENSE,
                        "source_license_url": OPENLIGADB_LICENSE_URL,
                        "source_attribution": OPENLIGADB_ATTRIBUTION,
                        "source_url": url, "source_timezone": "UTC",
                        "source_updated_at": match.get("lastUpdateDateTime"),
                        "league_name": match.get("leagueName") or league["name"],
                        "league_code": league["shortcut"],
                        "matchday": (match.get("group") or {}).get("groupOrderID") if isinstance(match.get("group"), dict) else None,
                    })

                competition["matches_found"] = sum(
                    1 for row in rows if row["league_code"] == league["shortcut"]
                )
                if competition["matches_found"]:
                    competition["status"] = "RESULTS_FOUND"
                elif competition["total_matches"] == 0:
                    competition["status"] = "EMPTY_SEASON_RESPONSE"
                elif competition["gap_date_matches"] == 0:
                    competition["status"] = "NO_GAP_FIXTURES_IN_SEASON"
                else:
                    competition["status"] = "NO_90_MINUTE_RESULT_FOR_GAP_FIXTURES"
            except requests.HTTPError as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                competition.update({"status": "HTTP_ERROR", "error_type": "HTTPError", "status_code": status_code})
                if status_code == 429:
                    rate_limited = True
                    audit["request_errors"] = audit.get("request_errors", []) + [{
                        "competition": league["shortcut"], "error_type": "HTTP_429",
                    }]
                    audit["competitions"].append(competition)
                    break
            except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                competition.update({"status": "REQUEST_ERROR", "error_type": type(exc).__name__})
            audit["competitions"].append(competition)
    finally:
        if own_session:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    date_counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = date_counts.setdefault(row["date"], {"date": row["date"], "matches": 0, "divisions": []})
        entry["matches"] += 1
        if row["division"] not in entry["divisions"]:
            entry["divisions"].append(row["division"])
    audit["matches_found"] = len(rows)
    audit["dates_covered"] = sorted(date_counts)
    audit["date_coverage"] = [date_counts[day] for day in sorted(date_counts)]
    any_season_data = any(item.get("total_matches", 0) for item in audit["competitions"])
    audit["status"] = (
        "PARTIAL_RATE_LIMITED" if rate_limited
        else "PARTIAL_RECOVERY" if rows
        else "NO_GAP_RESULTS" if any_season_data
        else "NO_DATA_AVAILABLE"
    )
    return rows, audit


def run(cache_path: Path, fallback_path: Path, output_path: Path, api: Any, session: Any = None, force: bool = False) -> dict[str, Any]:
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    if cache.get("version") not in (1, 2) or not isinstance(cache.get("matches"), list):
        raise ValueError("Unsupported or malformed recent-results cache.")
    state = cache.get("state") if isinstance(cache.get("state"), dict) else {}
    gaps = sorted({str(x) for x in state.get("history_gaps", []) if isinstance(x, str)})
    existing = list(cache["matches"])
    provider_cooldown_active = False
    retry_after_date = None
    if gaps and state.get("last_gap_retry_on"):
        try:
            last_retry = date.fromisoformat(str(state["last_gap_retry_on"]))
            today_lagos = datetime.now(ZoneInfo("Africa/Lagos")).date()
            provider_cooldown_active = (today_lagos - last_retry).days < 1
            retry_after_date = (last_retry + timedelta(days=1)).isoformat()
        except (TypeError, ValueError):
            provider_cooldown_active = False
    # Football-Data.co.uk explicitly limits its free CSV feed to private/academic
    # use and excludes commercial products and model training. Do not ingest it.
    fallback = []
    fallback_by_day: dict[str, int] = {}
    for row in fallback:
        fallback_by_day[row["date"]] = fallback_by_day.get(row["date"], 0) + 1

    # [run-gap-backfill] Controlled one-shot retry; do not ingest open-matchday: its published terms restrict use to
    # non-commercial informational purposes. Historical recovery stays on
    # the contracted primary provider until a commercially permitted source
    # is explicitly approved and audited.
    open_rows: list[dict[str, Any]] = []
    open_audit = {
        "provider": "open-matchday", "status": "SKIPPED_NONCOMMERCIAL_LICENSE",
        "files_requested": 0, "files_verified": 0, "matches_added": 0,
        "resolved_dates": [],
    }
    recovered: list[dict[str, Any]] = []
    day_results = []
    resolved = set()
    unresolved_gaps = [day for day in gaps if day not in resolved]
    league_scan = {"active_mapped_leagues": 0, "successful_league_queries": 0, "matches": 0, "failed_leagues": []}
    league_rows_by_day: dict[str, list[dict[str, Any]]] = {day: [] for day in unresolved_gaps}
    rate_limited = False
    delay_seconds = 0.0
    try:
        delay_seconds = max(0.0, min(30.0, float(os.getenv("VELTRIX_HISTORY_REQUEST_DELAY_SECONDS", "1.5"))))
    except (TypeError, ValueError):
        delay_seconds = 0.0
    if unresolved_gaps and (force or not provider_cooldown_active):
        leagues = []
        page = 1
        try:
            while page <= 20:
                payload = api.leagues(page=page, per_page=100)
                leagues.extend(payload.get("response") or [])
                pagination = payload.get("pagination") or {}
                if not pagination.get("has_more"):
                    break
                page += 1
        except ProviderAPIError as exc:
            rate_limited = "HTTP 429" in str(exc)
            league_scan["error_type"] = "HTTP_429" if rate_limited else type(exc).__name__
            league_scan["error"] = str(exc)[:240]

        mapped = [
            (league, _mapped_league_division(league))
            for league in leagues
            if isinstance(league, dict) and league.get("id") is not None
            and _mapped_league_division(league) is not None
        ]
        league_scan["provider_leagues_returned"] = len(leagues)
        league_scan["sample_league_names"] = [
            str(row.get("name") or row.get("league_name") or ((row.get("league") or {}).get("name") if isinstance(row.get("league"), dict) else "") or "")
            for row in leagues[:30] if isinstance(row, dict)
        ]
        league_scan["active_mapped_leagues"] = len(mapped)
        league_scan["mapped_league_names"] = [
            {"name": str(row.get("name") or row.get("league_name") or ((row.get("league") or {}).get("name") if isinstance(row.get("league"), dict) else "")), "division": division, "id": str(row.get("id"))}
            for row, division in mapped
        ]
        if not rate_limited:
            for league, division in mapped:
                league_id = league.get("id")
                try:
                    payload = api.league_fixtures(league_id, unresolved_gaps[0], unresolved_gaps[-1], "Africa/Lagos")
                    rows = extract_completed_results(payload)
                    league_scan["successful_league_queries"] += 1
                    for row in rows:
                        day = row["date"].isoformat()
                        if day in league_rows_by_day:
                            league_rows_by_day[day].append({
                                "date": day, "division": division or row.get("division") or "",
                                "home": row["home"], "away": row["away"],
                                "home_goals": row["home_goals"], "away_goals": row["away_goals"],
                                "fixture_id": row.get("fixture_id"), "fixture_status": row.get("fixture_status") or "FT",
                                "source_provider": "5DollarFootballAPI_LEAGUE_FIXTURES",
                            })
                    league_scan["matches"] += len(rows)
                    time_module.sleep(max(1.5, delay_seconds))
                except (ProviderAPIError, ValueError, OSError) as exc:
                    league_scan["failed_leagues"].append({"league_id": str(league_id), "error_type": type(exc).__name__, "error": str(exc)[:240]})
                    if "HTTP 429" in str(exc):
                        rate_limited = True
                        break
        for day in gaps:
            if day in resolved:
                day_results.append({"date": day, "status": "OPEN_MATCHDAY_VERIFIED", "matches": sum(1 for row in open_rows if row["date"] == day), "source": "open-matchday"})
        for day, rows in league_rows_by_day.items():
            if rows:
                recovered.extend(rows)
                if (
                    not rate_limited
                    and league_scan["active_mapped_leagues"] > 0
                    and league_scan["successful_league_queries"] == league_scan["active_mapped_leagues"]
                ):
                    resolved.add(day)
                day_results.append({
                    "date": day,
                    "status": "LEAGUE_RESULTS_RECOVERED" if day in resolved else "LEAGUE_RESULTS_PARTIAL",
                    "matches": len(rows),
                })
            else:
                day_results.append({
                    "date": day,
                    "status": "PROVIDER_RATE_LIMITED" if rate_limited else "LEAGUE_ENDPOINT_EMPTY_UNVERIFIED",
                    "matches": 0,
                })

    date_endpoint = {
        "status": "NOT_REQUIRED", "dates_checked": 0, "matches_added": 0,
        "resolved_dates": [], "timezone_retries": 0, "request_errors": [],
    }
    if unresolved_gaps and (force or not provider_cooldown_active):
        date_endpoint["status"] = "CHECKED"
        for day in unresolved_gaps:
            if day in resolved:
                continue
            try:
                date_fixtures = getattr(api, "fixtures", None)
                if not callable(date_fixtures):
                    date_endpoint["request_errors"].append({
                        "date": day, "error_type": "DATE_ENDPOINT_UNAVAILABLE",
                    })
                    continue
                # A 429 from the league catalogue must not suppress an
                # independent date endpoint probe; wait before probing it.
                date_pause = max(delay_seconds, 2.0 if rate_limited else 1.0)
                if session is None:
                    time_module.sleep(date_pause)
                payload = date_fixtures(day, "Africa/Lagos")
                # The date endpoint is independently usable even if the
                # league-catalogue endpoint was rate-limited.
                rate_limited = False
                rows = extract_completed_results(payload)
                timezone_used = "Africa/Lagos"
                meta = payload.get("_veltrix_meta") or {}
                pages = int(meta.get("pages_fetched", 0) or 0)
                if not rows:
                    if delay_seconds and session is None:
                        time_module.sleep(delay_seconds)
                    utc_payload = date_fixtures(day, "UTC")
                    utc_rows = extract_completed_results(utc_payload)
                    date_endpoint["timezone_retries"] += 1
                    if utc_rows:
                        payload, rows, timezone_used = utc_payload, utc_rows, "UTC"
                        meta = payload.get("_veltrix_meta") or {}
                        pages = int(meta.get("pages_fetched", 0) or 0)
                date_endpoint["dates_checked"] += 1
                if rows and pages > 0:
                    added = [{
                        "date": row["date"].isoformat(), "division": row.get("division") or "",
                        "home": row["home"], "away": row["away"],
                        "home_goals": row["home_goals"], "away_goals": row["away_goals"],
                        "fixture_id": row.get("fixture_id"),
                        "fixture_status": row.get("fixture_status") or "FT",
                        "source_provider": "5DollarFootballAPI_DATE_FIXTURES",
                    } for row in rows]
                    recovered.extend(added)
                    resolved.add(day)
                    date_endpoint["resolved_dates"].append(day)
                    date_endpoint["matches_added"] += len(added)
                    status = "DATE_RESULTS_RECOVERED"
                else:
                    status = "DATE_EMPTY_UNVERIFIED"
                existing_result = next((item for item in day_results if item.get("date") == day), None)
                if existing_result:
                    existing_result.update({"date_endpoint_status": status, "date_endpoint_matches": len(rows), "timezone": timezone_used})
                else:
                    day_results.append({"date": day, "status": status, "matches": len(rows), "timezone": timezone_used})
                time_module.sleep(max(delay_seconds, 1.0))
            except ProviderAPIError as exc:
                date_endpoint["request_errors"].append({"date": day, "error_type": type(exc).__name__, "error": str(exc)[:240]})
                if "HTTP 429" in str(exc):
                    rate_limited = True
                    date_endpoint["status"] = "RATE_LIMITED"
                    break
            except (ValueError, OSError) as exc:
                date_endpoint["request_errors"].append({"date": day, "error_type": type(exc).__name__})

    # OpenLigaDB is an independent, commercial-compatible ODbL source.
    # Keep its provenance on every row and never clear a global gap from this
    # narrower league subset alone.
    openligadb_rows, openligadb_audit = _openligadb_gap_backfill(session, gaps, delay_seconds)
    recovered.extend(openligadb_rows)
    recovered.extend(fallback)
    unique = {}
    for row in existing + recovered:
        key = (str(row.get("date") or "")[:10], str(row.get("division") or ""), _name_key(row.get("home")), _name_key(row.get("away")))
        if key[0] and key[2] and key[3] and key not in unique:
            unique[key] = row
    merged = sorted(unique.values(), key=lambda r: (str(r.get("date") or ""), str(r.get("division") or ""), _name_key(r.get("home")), _name_key(r.get("away"))))
    existing_keys = {
        (str(row.get("date") or "")[:10], str(row.get("division") or ""), _name_key(row.get("home")), _name_key(row.get("away")))
        for row in existing
    }
    openligadb_audit["matches_added"] = sum(
        1 for row in merged
        if row.get("source_provider") == "OpenLigaDB"
        and (str(row.get("date") or "")[:10], str(row.get("division") or ""), _name_key(row.get("home")), _name_key(row.get("away"))) not in existing_keys
    )
    openligadb_audit["matches_already_present"] = max(0, openligadb_audit.get("matches_found", 0) - openligadb_audit["matches_added"])
    state["openligadb_gap_backfill"] = {
        "status": openligadb_audit["status"],
        "last_checked_lagos": datetime.now(ZoneInfo("Africa/Lagos")).isoformat(),
        "matches_found": openligadb_audit["matches_found"],
        "matches_added": openligadb_audit["matches_added"],
        "dates_covered": openligadb_audit["dates_covered"],
        "competitions": [item["shortcut"] for item in openligadb_audit["competitions"] if item["matches_found"]],
        "license": OPENLIGADB_LICENSE,
        "attribution": OPENLIGADB_ATTRIBUTION,
    }
    source_licenses = state.get("source_licenses") if isinstance(state.get("source_licenses"), dict) else {}
    source_licenses["OpenLigaDB"] = {
        "license": OPENLIGADB_LICENSE,
        "license_url": OPENLIGADB_LICENSE_URL,
        "attribution": OPENLIGADB_ATTRIBUTION,
        "source_url": "https://www.openligadb.de/",
        "commercial_use": "Permitted subject to ODbL 1.0 attribution and share-alike obligations.",
    }
    state["source_licenses"] = source_licenses
    state["history_gaps"] = [day for day in gaps if day not in resolved]
    # Keep an explicit empty list when all dates are resolved. Consumers can
    # distinguish "checked and complete" from an older cache with no gap audit.
    if force or not provider_cooldown_active:
        # Record the attempt even when the provider rate-limits us. This
        # prevents repeated code-push or watchdog runs from hammering a
        # blocked endpoint; unresolved dates remain queued for the next day.
        state["last_gap_retry_on"] = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
    state["gap_backfill_last_run"] = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
    open_resolved_dates = set(open_audit.get("resolved_dates") or [])
    provider_resolved_dates = resolved - open_resolved_dates
    state["gap_backfill_provider_resolved_dates"] = sorted(set(state.get("gap_backfill_provider_resolved_dates", [])) | provider_resolved_dates)
    state["gap_backfill_open_matchday_resolved_dates"] = sorted(set(state.get("gap_backfill_open_matchday_resolved_dates", [])) | open_resolved_dates)
    cache["version"] = 2
    cache["state"] = state
    cache["matches"] = merged
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    report = {
        "status": (
            "COMPLETE" if not state.get("history_gaps")
            else "PARTIAL_OPENLIGADB_RECOVERY" if openligadb_audit.get("matches_found")
            else "PROVIDER_RATE_LIMITED" if rate_limited
            else "PARTIAL_PROVIDER_RETRY_COOLDOWN" if provider_cooldown_active and not force
            else "PARTIAL_UNRESOLVED_SOURCE_GAPS"
        ),
        "requested_gap_dates": len(gaps), "primary_resolved_dates": len(provider_resolved_dates),
        "open_matchday_resolved_dates": sorted(open_resolved_dates), "all_resolved_dates": sorted(resolved),
        "unresolved_dates": state.get("history_gaps", []),
        "open_matchday": open_audit,
        "openligadb": openligadb_audit,
        "openligadb_matches_added": openligadb_audit["matches_added"],
        "primary_provider_rate_limited": rate_limited,
        "date_endpoint": date_endpoint,
        "request_delay_seconds": delay_seconds,
        "provider_retry_cooldown_active": provider_cooldown_active,
        "provider_retry_after_date": retry_after_date,
        "league_endpoint_scan": league_scan,
        "league_endpoint_resolved_dates": sorted(day for day, rows in league_rows_by_day.items() if rows and day in resolved),
        "secondary_fallback_matches_added": 0,
        "secondary_fallback_status": "SKIPPED_NONCOMMERCIAL_LICENSE",
        "primary_matches_added": sum(1 for row in recovered if row.get("source_provider") in {"5DollarFootballAPI", "5DollarFootballAPI_DATE_FIXTURES"}),
        "league_endpoint_matches_added": sum(1 for row in recovered if row.get("source_provider") == "5DollarFootballAPI_LEAGUE_FIXTURES"),
        "cache_rows_before": len(existing), "cache_rows_after": len(merged),
        "date_results": day_results,
        "integrity": "OpenLigaDB rows retain ODbL provenance; this partial league subset never clears global date gaps. Unresolved dates are never silently marked complete.",
        "alerts_enabled": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--fallback", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--force", action="store_true", help="Bypass the daily retry cooldown for an explicitly requested run.")
    args = parser.parse_args()
    repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if not repo or not token:
        raise RuntimeError("GitHub publication context is missing.")
    api = FiveDollarFootballClient()
    report = run(Path(args.cache), Path(args.fallback), Path(args.output), api, force=args.force)
    Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    # Publish even a rate-limited result so the retry cursor and unresolved
    # dates persist. The report status distinguishes partial recovery from
    # complete recovery; a provider 429 is not a software/test failure.
    publish("public-data/recent_results_cache.json", Path(args.output), repo, token)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Independent 2026/27 result recovery is sourced from open-matchday with explicit provenance.

# [run-gap-backfill] one explicitly throttled recovery pass for unresolved dates.

# [run-gap-backfill] validate independent date endpoint after catalogue 429.

# One final bounded audit run after expanded 13-competition mapping: [run-openligadb-backfill]

# Controlled primary-provider retry after successful credential smoke check: [run-gap-backfill]

# Controlled forced retry after provider authentication recovered and quota reset was verified: [run-gap-backfill]
