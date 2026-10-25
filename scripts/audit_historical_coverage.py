"""Manual Highlightly season-coverage audit; keep requests bounded on the free tier."""
from __future__ import annotations

import json
from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError, normalize_match

SAMPLES = ("Premier League", "La Liga", "Serie A")
SEASONS = (2025, 2026)
COMPLETED = {"FT", "AET", "PEN"}


def main() -> int:
    api = FootballAPI(get_settings())
    report = {
        "purpose": "Sample Highlightly coverage for selected competitions and seasons.",
        "warning": "Each league/season sample makes API requests; monitor the daily quota.",
        "provider": "Highlightly",
        "samples": [],
        "errors": [],
    }

    for league_name in SAMPLES:
        for year in SEASONS:
            row = {"league": league_name, "season": year, "request_ok": False}
            try:
                league_payload = api.get("leagues", {
                    "season": year,
                    "leagueName": league_name,
                    "limit": 20,
                    "offset": 0,
                })
                leagues = league_payload.get("data")
                if not isinstance(leagues, list):
                    raise FootballAPIError("Highlightly leagues response is missing its data list.")
                if not leagues:
                    row.update({
                        "request_ok": True,
                        "league_found": False,
                        "fixtures_sampled": 0,
                        "note": "No matching league returned for this season/name filter.",
                    })
                    row["requests_remaining"] = (league_payload.get("_veltrix_meta") or {}).get("requests_remaining")
                    report["samples"].append(row)
                    continue

                league = leagues[0]
                match_payload = api.get("matches", {
                    "leagueId": league.get("id"),
                    "season": year,
                    "limit": 100,
                    "offset": 0,
                })
                raw_matches = match_payload.get("data")
                if not isinstance(raw_matches, list):
                    raise FootballAPIError("Highlightly matches response is missing its data list.")
                matches = [normalize_match(item) for item in raw_matches if isinstance(item, dict)]
                completed = [
                    item for item in matches
                    if item.get("fixture", {}).get("status", {}).get("short") in COMPLETED
                    and item.get("goals", {}).get("home") is not None
                    and item.get("goals", {}).get("away") is not None
                ]
                upcoming = [
                    item for item in matches
                    if item.get("fixture", {}).get("status", {}).get("short") in {"NS", "TBD"}
                ]
                row.update({
                    "request_ok": True,
                    "league_found": True,
                    "resolved_league_id": league.get("id"),
                    "fixtures_sampled": len(matches),
                    "provider_total_count": (match_payload.get("pagination") or {}).get("totalCount"),
                    "completed_with_scores_in_sample": len(completed),
                    "upcoming_unplayed_in_sample": len(upcoming),
                    "sample_upcoming_fixture_ids": [
                        item.get("fixture", {}).get("id") for item in upcoming[:3]
                    ],
                    "requests_remaining": (match_payload.get("_veltrix_meta") or {}).get("requests_remaining"),
                })
            except (FootballAPIError, ValueError) as exc:
                row["error"] = str(exc)
                report["errors"].append(f"{league_name} {year}: {exc}")
            report["samples"].append(row)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    successful = sum(bool(row.get("request_ok")) for row in report["samples"])
    with_data = sum(row.get("completed_with_scores_in_sample", 0) > 0 for row in report["samples"])
    upcoming = sum(row.get("upcoming_unplayed_in_sample", 0) > 0 for row in report["samples"])
    print(
        f"AUDIT_SUMMARY: successful samples={successful}/{len(report['samples'])}; "
        f"samples with completed scores={with_data}; samples with upcoming fixtures={upcoming}; "
        f"errors={len(report['errors'])}"
    )
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
