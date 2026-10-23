from __future__ import annotations

import json
from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError

# A small, quota-conscious audit: three major leagues, three seasons.
# This verifies the actual subscription response, not the marketing page.
SAMPLES = {
    39: ("England", "Premier League"),
    140: ("Spain", "La Liga"),
    135: ("Italy", "Serie A"),
}
SEASONS = (2023, 2024, 2025)
COMPLETED = {"FT", "AET", "PEN"}


def main() -> int:
    api = FootballAPI(get_settings())
    report = {"plan_status": None, "samples": [], "errors": []}

    status = api.status()
    response = status.get("response", {})
    report["plan_status"] = {
        "plan": response.get("subscription", {}).get("plan"),
        "active": response.get("subscription", {}).get("active"),
        "requests_used": response.get("requests", {}).get("current"),
        "daily_limit": response.get("requests", {}).get("limit_day"),
    }

    for league_id, (country, league_name) in SAMPLES.items():
        try:
            meta = api.get("leagues", {"id": league_id})
            league_items = meta.get("response", [])
            seasons_available = set()
            coverage_by_season = {}
            for item in league_items:
                for season in item.get("seasons", []):
                    year = season.get("year")
                    if year is not None:
                        seasons_available.add(int(year))
                        coverage_by_season[str(year)] = season.get("coverage", {})
            for year in SEASONS:
                row = {
                    "league_id": league_id,
                    "league": league_name,
                    "country": country,
                    "season": year,
                    "listed_in_league_metadata": year in seasons_available,
                    "coverage": coverage_by_season.get(str(year)),
                }
                try:
                    payload = api.get("fixtures", {"league": league_id, "season": year})
                    fixtures = payload.get("response", [])
                    completed = [
                        f for f in fixtures
                        if f.get("fixture", {}).get("status", {}).get("short") in COMPLETED
                        and f.get("goals", {}).get("home") is not None
                        and f.get("goals", {}).get("away") is not None
                    ]
                    row.update({
                        "request_ok": True,
                        "fixtures_returned": len(fixtures),
                        "completed_with_scores": len(completed),
                    })
                except FootballAPIError as exc:
                    row.update({"request_ok": False, "error": str(exc)})
                    report["errors"].append(f"{league_name} {year}: {exc}")
                report["samples"].append(row)
        except FootballAPIError as exc:
            report["errors"].append(f"{league_name} metadata: {exc}")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    successful = sum(1 for row in report["samples"] if row.get("request_ok"))
    with_data = sum(1 for row in report["samples"] if row.get("completed_with_scores", 0) > 0)
    print(f"AUDIT_SUMMARY: successful season requests={successful}/{len(report['samples'])}; seasons with completed scored fixtures={with_data}; errors={len(report['errors'])}")
    # A zero-data response is a finding, not a workflow failure. Actual API errors are failures.
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
