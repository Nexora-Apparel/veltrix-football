"""Retry known historical result gaps and publish only verified recovered scores."""
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
from app.live_predictions import _name_key


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
    """Import independently published 2026/27 results for every mapped competition."""
    audit = {
        "provider": "open-matchday", "season": "2627",
        "status": "INCOMPLETE", "files_requested": len(OPEN_MATCHDAY_DIVISIONS),
        "files_verified": 0, "files_failed": [], "matches_added": 0,
        "resolved_dates": [], "attribution": "oladeeayo/open-matchday",
        "source_terms": "Informational, non-commercial use only; no commercial reuse or redistribution without permission.",
    }
    if not gaps:
        audit["status"] = "NOT_REQUIRED"
        return [], audit
    try:
        response = session.get(f"{OPEN_MATCHDAY_BASE}/build_summary.json", timeout=30)
        response.raise_for_status()
        summary = response.json()
        if summary.get("season") != "2627" or not isinstance(summary.get("leagues"), list):
            raise ValueError("Unexpected open-matchday summary schema or season.")
        audit["generated_utc"] = summary.get("generated_utc")
    except (requests.RequestException, ValueError, OSError, AttributeError) as exc:
        audit["files_failed"].append({"source": "build_summary.json", "error_type": type(exc).__name__})
        return [], audit
    metadata = {
        str(row.get("folder") or "").strip(): row
        for row in summary["leagues"] if isinstance(row, dict)
    }
    recovered = []
    all_verified = True
    for division, folder in OPEN_MATCHDAY_DIVISIONS.items():
        meta = metadata.get(f"data/{folder}")
        if (
            not isinstance(meta, dict)
            or int(meta.get("results") or 0) < 1
            or str(meta.get("latest") or "") < max(gaps)
            or meta.get("errors")
        ):
            all_verified = False
            audit["files_failed"].append({"division": division, "folder": folder, "reason": "MISSING_OR_STALE_MANIFEST"})
            continue
        try:
            response = session.get(f"{OPEN_MATCHDAY_BASE}/data/{folder}/results_2627.csv", timeout=30)
            response.raise_for_status()
            reader = csv.DictReader(io.StringIO(response.text))
            required = {"date", "home", "away", "ft_home", "ft_away"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ValueError("Unexpected results CSV schema.")
            for raw in reader:
                day = str(raw.get("date") or "").strip()[:10]
                if day not in gaps:
                    continue
                try:
                    hg, ag = int(raw["ft_home"]), int(raw["ft_away"])
                    home, away = str(raw.get("home") or "").strip(), str(raw.get("away") or "").strip()
                    if hg < 0 or ag < 0 or not home or not away or _name_key(home) == _name_key(away):
                        continue
                except (KeyError, TypeError, ValueError):
                    continue
                recovered.append({
                    "date": day, "division": division, "home": home, "away": away,
                    "home_goals": hg, "away_goals": ag, "fixture_id": None,
                    "fixture_status": "FT", "source_provider": "open-matchday",
                    "source_detail": str(raw.get("source") or "unknown"),
                })
            audit["files_verified"] += 1
        except (requests.RequestException, ValueError, OSError, csv.Error) as exc:
            all_verified = False
            audit["files_failed"].append({"division": division, "folder": folder, "error_type": type(exc).__name__})
    audit["matches_added"] = len(recovered)
    if all_verified and audit["files_verified"] == audit["files_requested"]:
        audit["resolved_dates"] = sorted(gaps)
        audit["status"] = "VERIFIED_MAPPED_COMPETITION_COVERAGE"
    else:
        audit["status"] = "PARTIAL_SOURCE_COVERAGE"
    return recovered, audit


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


def run(cache_path: Path, fallback_path: Path, output_path: Path, api: Any, session: Any = None) -> dict[str, Any]:
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
            provider_cooldown_active = (today_lagos - last_retry).days < 7
            retry_after_date = (last_retry + timedelta(days=7)).isoformat()
        except (TypeError, ValueError):
            provider_cooldown_active = False
    fallback = _fallback_rows(fallback_path, set(gaps))
    fallback_by_day: dict[str, int] = {}
    for row in fallback:
        fallback_by_day[row["date"]] = fallback_by_day.get(row["date"], 0) + 1

    own_session = session is None
    session = session or requests.Session()
    open_rows, open_audit = _open_matchday_backfill(session, gaps)
    recovered: list[dict[str, Any]] = list(open_rows)
    day_results = []
    resolved = set(open_audit.get("resolved_dates") or [])
    unresolved_gaps = [day for day in gaps if day not in resolved]
    league_scan = {"active_mapped_leagues": 0, "successful_league_queries": 0, "matches": 0, "failed_leagues": []}
    league_rows_by_day: dict[str, list[dict[str, Any]]] = {day: [] for day in unresolved_gaps}
    rate_limited = False
    if unresolved_gaps and not provider_cooldown_active:
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
                    time_module.sleep(1.5)
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
    # Secondary open-data results are useful additions but cannot prove global
    # date completeness, so they never clear a primary-provider date gap alone.
    recovered.extend(fallback)
    unique = {}
    for row in existing + recovered:
        key = (str(row.get("date") or "")[:10], str(row.get("division") or ""), _name_key(row.get("home")), _name_key(row.get("away")))
        if key[0] and key[2] and key[3] and key not in unique:
            unique[key] = row
    merged = sorted(unique.values(), key=lambda r: (str(r.get("date") or ""), str(r.get("division") or ""), _name_key(r.get("home")), _name_key(r.get("away"))))
    state["history_gaps"] = [day for day in gaps if day not in resolved]
    if not state["history_gaps"]:
        state.pop("history_gaps", None)
    if not rate_limited and not provider_cooldown_active:
        state["last_gap_retry_on"] = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
    state["gap_backfill_last_run"] = "2026-11-02"
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
        "status": "PROVIDER_RATE_LIMITED" if rate_limited else ("COMPLETE" if not state.get("history_gaps") else ("PARTIAL_PROVIDER_RETRY_COOLDOWN" if provider_cooldown_active else "PARTIAL_UNRESOLVED_SOURCE_GAPS")),
        "requested_gap_dates": len(gaps), "primary_resolved_dates": len(provider_resolved_dates),
        "open_matchday_resolved_dates": sorted(open_resolved_dates), "all_resolved_dates": sorted(resolved),
        "unresolved_dates": state.get("history_gaps", []),
        "open_matchday": open_audit,
        "provider_retry_cooldown_active": provider_cooldown_active,
        "provider_retry_after_date": retry_after_date,
        "league_endpoint_scan": league_scan,
        "league_endpoint_resolved_dates": sorted(day for day, rows in league_rows_by_day.items() if rows and day in resolved),
        "secondary_fallback_matches_added": len(fallback),
        "primary_matches_added": sum(1 for row in recovered if row.get("source_provider") == "5DollarFootballAPI"),
        "league_endpoint_matches_added": sum(1 for row in recovered if row.get("source_provider") == "5DollarFootballAPI_LEAGUE_FIXTURES"),
        "cache_rows_before": len(existing), "cache_rows_after": len(merged),
        "date_results": day_results,
        "integrity": "Secondary results are added with provenance; unresolved dates are never silently marked complete.",
        "alerts_enabled": False,
    }
    if own_session:
        session.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--fallback", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if not repo or not token:
        raise RuntimeError("GitHub publication context is missing.")
    api = FiveDollarFootballClient()
    report = run(Path(args.cache), Path(args.fallback), Path(args.output), api)
    Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if report["status"] not in {"PROVIDER_RATE_LIMITED", "RETRY_COOLDOWN"}:
        publish("public-data/recent_results_cache.json", Path(args.output), repo, token)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] in {"COMPLETE", "RETRY_COOLDOWN"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
