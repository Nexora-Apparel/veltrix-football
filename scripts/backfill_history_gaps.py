"""Retry known historical result gaps and publish only verified recovered scores."""
from __future__ import annotations
import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.provider_adapters import FiveDollarFootballClient, ProviderAPIError
from app.recent_results import extract_completed_results
from scripts.publish_command_data import publish
from app.live_predictions import _name_key


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
    for day in gaps:
        try:
            payload = api.fixtures(day, "Africa/Lagos")
            rows = extract_completed_results(payload)
            meta = payload.get("_veltrix_meta") or {}
            pages = int(meta.get("pages_fetched", 0) or 0)
            if rows and pages > 0:
                recovered.extend({
                    "date": row["date"].isoformat(), "division": row.get("division") or "",
                    "home": row["home"], "away": row["away"],
                    "home_goals": row["home_goals"], "away_goals": row["away_goals"],
                    "fixture_id": row.get("fixture_id"), "fixture_status": row.get("fixture_status") or "FT",
                    "source_provider": "5DollarFootballAPI",
                } for row in rows)
                resolved.add(day)
                day_results.append({"date": day, "status": "PRIMARY_RESULTS_RECOVERED", "matches": len(rows), "pages": pages, "secondary_matches": fallback_by_day.get(day, 0)})
            else:
                day_results.append({"date": day, "status": "PRIMARY_EMPTY_UNVERIFIED", "matches": 0, "pages": pages, "secondary_matches": fallback_by_day.get(day, 0)})
        except (ProviderAPIError, ValueError, OSError) as exc:
            day_results.append({"date": day, "status": "PRIMARY_REQUEST_FAILED", "matches": 0, "secondary_matches": fallback_by_day.get(day, 0), "error_type": type(exc).__name__})

    # Secondary open-data results are useful additions but cannot prove global
    # date completeness, so they never clear a primary-provider date gap alone.
    recovered.extend(fallback)
    unique = {}
    for row in existing + recovered:
        key = (str(row.get("date") or "")[:10], str(row.get("division") or ""), _name_key(row.get("home")), _name_key(row.get("away")))
        if all(key) and key not in unique:
            unique[key] = row
    merged = sorted(unique.values(), key=lambda r: (str(r.get("date") or ""), str(r.get("division") or ""), _name_key(r.get("home")), _name_key(r.get("away"))))
    state["history_gaps"] = [day for day in gaps if day not in resolved]
    if not state["history_gaps"]:
        state.pop("history_gaps", None)
    state["last_gap_retry_on"] = "2026-11-02"
    state["gap_backfill_last_run"] = "2026-11-02"
    state["gap_backfill_provider_resolved_dates"] = sorted(set(state.get("gap_backfill_provider_resolved_dates", [])) | resolved)
    cache["version"] = 2
    cache["state"] = state
    cache["matches"] = merged
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    report = {
        "status": "COMPLETE" if not state.get("history_gaps") else "PARTIAL_UNRESOLVED_SOURCE_GAPS",
        "requested_gap_dates": len(gaps), "primary_resolved_dates": len(resolved),
        "unresolved_dates": state.get("history_gaps", []),
        "secondary_fallback_matches_added": len(fallback),
        "primary_matches_added": len(recovered) - len(fallback),
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
    publish("public-data/recent_results_cache.json", Path(args.output), repo, token)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
