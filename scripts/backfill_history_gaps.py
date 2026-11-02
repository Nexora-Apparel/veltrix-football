"""Retry known historical result gaps and publish only verified recovered scores."""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
import time
import re
import unicodedata
from datetime import date, datetime, timezone
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


def run(cache_path: Path, fallback_path: Path, output_path: Path, api: Any) -> dict[str, Any]:
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    if cache.get("version") not in (1, 2) or not isinstance(cache.get("matches"), list):
        raise ValueError("Unsupported or malformed recent-results cache.")
    state = cache.get("state") if isinstance(cache.get("state"), dict) else {}
    gaps = sorted({str(x) for x in state.get("history_gaps", []) if isinstance(x, str)})
    existing = list(cache["matches"])
    fallback = _fallback_rows(fallback_path, set(gaps))
    fallback_by_day: dict[str, int] = {}
    for row in fallback:
        fallback_by_day[row["date"]] = fallback_by_day.get(row["date"], 0) + 1

    recovered: list[dict[str, Any]] = []
    day_results = []
    resolved = set()
    league_scan = {"active_mapped_leagues": 0, "successful_league_queries": 0, "matches": 0, "failed_leagues": []}
    league_rows_by_day: dict[str, list[dict[str, Any]]] = {day: [] for day in gaps}
    rate_limited = False
    if gaps:
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
                    payload = api.league_fixtures(league_id, gaps[0], gaps[-1], "Africa/Lagos")
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
                    time.sleep(1.5)
                except (ProviderAPIError, ValueError, OSError) as exc:
                    league_scan["failed_leagues"].append({"league_id": str(league_id), "error_type": type(exc).__name__, "error": str(exc)[:240]})
                    if "HTTP 429" in str(exc):
                        rate_limited = True
                        break
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
    if not rate_limited:
        state["last_gap_retry_on"] = "2026-11-02"
    state["gap_backfill_last_run"] = "2026-11-02"
    state["gap_backfill_provider_resolved_dates"] = sorted(set(state.get("gap_backfill_provider_resolved_dates", [])) | resolved)
    cache["version"] = 2
    cache["state"] = state
    cache["matches"] = merged
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    report = {
        "status": "PROVIDER_RATE_LIMITED" if rate_limited else ("COMPLETE" if not state.get("history_gaps") else "PARTIAL_UNRESOLVED_SOURCE_GAPS"),
        "requested_gap_dates": len(gaps), "primary_resolved_dates": len(resolved),
        "unresolved_dates": state.get("history_gaps", []),
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
    if report["status"] != "PROVIDER_RATE_LIMITED":
        publish("public-data/recent_results_cache.json", Path(args.output), repo, token)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
