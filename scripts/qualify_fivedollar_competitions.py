#!/usr/bin/env python3
"""Run bounded, read-only 5Dollar results qualification and emit one report."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.fivedollar_qualification_report import (
    build_fivedollar_qualification_report,
    validate_fivedollar_qualification_report,
)

BASE = "https://api.5dollarfootballapi.com/v1"


class Budget:
    def __init__(self, maximum: int):
        self.maximum = maximum
        self.actual = 0
        self.by_endpoint: dict[str, int] = {}

    def get(self, endpoint: str, params: dict, key: str) -> dict:
        if self.actual >= self.maximum:
            raise RuntimeError("request_budget_exhausted")
        self.actual += 1
        self.by_endpoint[endpoint] = self.by_endpoint.get(endpoint, 0) + 1
        query = urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{BASE}/{endpoint.lstrip('/')}" + (f"?{query}" if query else "")
        request = Request(url, headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "VeltrixFootball-Qualification/1.0",
        })
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"provider_http_{exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise RuntimeError("provider_network_error") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("provider_invalid_json") from None
        if not isinstance(payload, dict) or payload.get("success") != 1:
            raise RuntimeError("provider_response_unsuccessful")
        return payload

    def accounting(self) -> list[dict]:
        return [{"endpoint": key, "requests": value}
                for key, value in sorted(self.by_endpoint.items())]


def _has_more(payload: dict) -> bool:
    pagination = payload.get("pagination") or {}
    if not isinstance(pagination, dict):
        raise RuntimeError("provider_pagination_invalid")
    return pagination.get("has_more") is True


def _valid_score(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def collect(key: str, budget: Budget, days: int, max_pages: int, run_id: str) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(days=days)
    competitions, catalogue_pages, catalogue_complete = [], 0, False
    page = 1
    try:
        while catalogue_pages < 5:
            payload = budget.get("leagues", {"page": page, "per_page": 100}, key)
            rows = payload.get("data")
            if not isinstance(rows, list):
                raise RuntimeError("provider_catalogue_data_invalid")
            for item in rows:
                if isinstance(item, dict) and item.get("id") is not None and item.get("name"):
                    competitions.append({"competition_id": str(item["id"]),
                                         "competition_name": str(item["name"])})
            catalogue_pages += 1
            if not _has_more(payload):
                catalogue_complete = True
                break
            page += 1
    except RuntimeError as exc:
        if str(exc) not in {"request_budget_exhausted"}:
            raise

    # Only the authenticated account catalogue defines the scope. Never infer
    # inaccessible competitions from public documentation or other providers.
    summary = []
    for competition in competitions:
        counters = {
            "competition_id": competition["competition_id"],
            "competition_name": competition["competition_name"],
            "pages_fetched": 0, "source_rows": 0, "accepted_rows": 0,
            "invalid_rows": 0, "duplicate_ids": 0, "missing_team_ids": 0,
            "pagination_complete": False,
        }
        page = 1
        seen = set()
        try:
            while counters["pages_fetched"] < max_pages:
                endpoint = f"leagues/{competition['competition_id']}/fixtures"
                payload = budget.get(endpoint, {
                    "start_time": int(start.timestamp()),
                    "end_time": int(now.timestamp()),
                    "status": "finished", "page": page, "per_page": 100,
                }, key)
                rows = payload.get("data")
                if not isinstance(rows, list):
                    raise RuntimeError("provider_fixture_data_invalid")
                counters["pages_fetched"] += 1
                counters["source_rows"] += len(rows)
                for item in rows:
                    if not isinstance(item, dict):
                        counters["invalid_rows"] += 1
                        continue
                    fixture_id = item.get("id")
                    if fixture_id is None:
                        counters["invalid_rows"] += 1
                        continue
                    identity = str(fixture_id)
                    if identity in seen:
                        counters["duplicate_ids"] += 1
                        continue
                    seen.add(identity)
                    teams, goals = item.get("teams"), item.get("goals")
                    home = teams.get("home") if isinstance(teams, dict) else None
                    away = teams.get("away") if isinstance(teams, dict) else None
                    if (not isinstance(home, dict) or not isinstance(away, dict)
                            or home.get("id") is None or away.get("id") is None):
                        counters["missing_team_ids"] += 1
                        continue
                    if (item.get("status") != "finished" or not isinstance(goals, dict)
                            or not _valid_score(goals.get("home"))
                            or not _valid_score(goals.get("away"))):
                        counters["invalid_rows"] += 1
                        continue
                    counters["accepted_rows"] += 1
                if not _has_more(payload):
                    counters["pagination_complete"] = True
                    break
                page += 1
        except RuntimeError as exc:
            if str(exc) not in {"request_budget_exhausted"}:
                raise
        summary.append(counters)
        if budget.actual >= budget.maximum:
            # Remaining catalogue entries are retained as explicitly incomplete.
            for remaining in competitions[len(summary):]:
                summary.append({
                    "competition_id": remaining["competition_id"],
                    "competition_name": remaining["competition_name"],
                    "pages_fetched": 0, "source_rows": 0, "accepted_rows": 0,
                    "invalid_rows": 0, "duplicate_ids": 0, "missing_team_ids": 0,
                    "pagination_complete": False,
                })
            break

    if not summary:
        raise RuntimeError("provider_catalogue_empty_or_budget_exhausted")
    return build_fivedollar_qualification_report(
        run_id=run_id,
        retrieved_at=now.isoformat().replace("+00:00", "Z"),
        window_start_utc=start.isoformat().replace("+00:00", "Z"),
        window_end_utc=now.isoformat().replace("+00:00", "Z"),
        max_requests=budget.maximum,
        actual_requests=budget.actual,
        endpoint_requests=budget.accounting(),
        competitions=summary,
        catalogue_pages_fetched=catalogue_pages,
        catalogue_pagination_complete=catalogue_complete,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-requests", type=int, required=True)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--max-pages-per-competition", type=int, default=3)
    parser.add_argument("--output", default="fivedollar_competition_qualification.json")
    args = parser.parse_args()
    if not 1 <= args.max_requests <= 60:
        parser.error("--max-requests must be between 1 and 60")
    if not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")
    if not 1 <= args.max_pages_per_competition <= 5:
        parser.error("--max-pages-per-competition must be between 1 and 5")
    key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not key:
        print("QUALIFICATION: BLOCKED_MISSING_SECRET")
        return 2
    budget = Budget(args.max_requests)
    run_id = os.getenv("GITHUB_RUN_ID", "manual-local-run")
    try:
        report = collect(key, budget, args.days, args.max_pages_per_competition, run_id)
        result = validate_fivedollar_qualification_report(report)
    except (RuntimeError, ValueError) as exc:
        print(f"QUALIFICATION: FAILED ({str(exc)[:160]})")
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"QUALIFICATION: {'PASS' if result['acceptance_pass'] else 'REVIEW_REQUIRED'}; "
        f"competitions={result['competition_count']}; "
        f"requests={budget.actual}/{budget.maximum}; "
        f"accepted={result['aggregates']['accepted_rows']}; "
        f"invalid={result['aggregates']['invalid_rows']}; "
        f"duplicates={result['aggregates']['duplicate_ids']}; "
        f"missing_team_ids={result['aggregates']['missing_team_ids']}"
    )
    print(f"REPORT_SHA256: {result['report_sha256']}")
    print(f"REPORT_FILE: {output}")
    # A valid REVIEW_REQUIRED report is still an auditable artifact; the
    # offline reviewer decides whether it can qualify the provider scope.
    return 0


if __name__ == "__main__":
    sys.exit(main())
