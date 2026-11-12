#!/usr/bin/env python3
"""Bounded, read-only 5DollarFootballAPI team-statistics capability probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.5dollarfootballapi.com/v1"
STAT_FIELDS = (
    "attacks", "dangerous_attacks", "shots_on_target",
    "shots_off_target", "possession", "first_half",
)


class Budget:
    def __init__(self, maximum: int):
        self.maximum = maximum
        self.actual = 0
        self.by_endpoint: dict[str, int] = {}

    def get(self, endpoint: str, params: dict, key: str) -> tuple[int | None, dict | None, str]:
        if self.actual >= self.maximum:
            return None, None, "REQUEST_BUDGET_EXHAUSTED"
        self.actual += 1
        self.by_endpoint[endpoint] = self.by_endpoint.get(endpoint, 0) + 1
        query = urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{BASE}/{endpoint.lstrip('/')}" + (f"?{query}" if query else "")
        request = Request(url, headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "VeltrixFootball-StatisticsQualification/1.0",
        })
        try:
            with urlopen(request, timeout=20) as response:
                status = response.status
                raw = response.read()
        except HTTPError as exc:
            return exc.code, None, f"HTTP_{exc.code}"
        except (URLError, TimeoutError, OSError):
            return None, None, "NETWORK_ERROR"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return status, None, "INVALID_JSON"
        if not isinstance(payload, dict) or payload.get("success") != 1:
            return status, payload if isinstance(payload, dict) else None, "UNSUCCESSFUL_RESPONSE"
        return status, payload, "OK"

    def accounting(self) -> list[dict]:
        return [{"endpoint": k, "requests": v} for k, v in sorted(self.by_endpoint.items())]


def valid_id(value) -> bool:
    return ((isinstance(value, int) and not isinstance(value, bool) and value > 0)
            or (isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0))


def _hash(report: dict) -> str:
    raw = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_report(report: dict) -> None:
    supplied = report.get("report_sha256")
    body = dict(report)
    body.pop("report_sha256", None)
    if not isinstance(supplied, str) or _hash(body) != supplied:
        raise ValueError("report_hash_invalid")
    if report.get("provider") != "5DollarFootballAPI" or report.get("mode") != "read_only_statistics_capability_probe":
        raise ValueError("report_scope_invalid")
    budget = report.get("request_budget", {})
    actual = budget.get("actual_requests")
    maximum = budget.get("maximum_requests")
    if (isinstance(actual, bool) or not isinstance(actual, int) or
            isinstance(maximum, bool) or not isinstance(maximum, int) or
            actual < 1 or actual > maximum or maximum > 20):
        raise ValueError("request_budget_invalid")
    entries = budget.get("endpoint_accounting")
    if not isinstance(entries, list) or sum(x["requests"] for x in entries) != actual:
        raise ValueError("request_accounting_invalid")
    if any(x.get("database_writes") != 0 for x in [report.get("side_effects", {})]):
        raise ValueError("side_effects_invalid")
    if report.get("side_effects") != {
        "database_writes": 0, "imports": 0, "prediction_publications": 0,
    }:
        raise ValueError("side_effects_invalid")
    samples = report.get("samples")
    if not isinstance(samples, list) or len(samples) != report.get("competition_count"):
        raise ValueError("sample_count_invalid")
    for row in samples:
        if not isinstance(row, dict) or row.get("statistics_status") not in {
            "OK_WITH_FIELDS", "OK_EMPTY", "HTTP_403", "HTTP_404",
            "HTTP_429", "HTTP_OTHER", "UNSUCCESSFUL_RESPONSE",
            "INVALID_JSON", "NETWORK_ERROR", "NO_FINISHED_FIXTURE",
            "FIXTURE_LOOKUP_FAILED", "REQUEST_BUDGET_EXHAUSTED",
        }:
            raise ValueError("sample_status_invalid")


def probe(key: str, maximum: int, days: int, run_id: str) -> dict:
    budget = Budget(maximum)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(days=days)
    status, catalogue, outcome = budget.get("leagues", {"page": 1, "per_page": 100}, key)
    if outcome != "OK" or not isinstance(catalogue.get("data"), list):
        raise RuntimeError(f"catalogue_{outcome.lower()}")
    competitions = []
    seen = set()
    for item in catalogue["data"]:
        if (not isinstance(item, dict) or not valid_id(item.get("id"))
                or not isinstance(item.get("name"), str) or not item["name"].strip()):
            raise RuntimeError("catalogue_row_invalid")
        identity = str(int(item["id"]))
        if identity in seen:
            raise RuntimeError("catalogue_duplicate_id")
        seen.add(identity)
        competitions.append({"id": identity, "name": item["name"].strip()})
    if not competitions:
        raise RuntimeError("catalogue_empty")
    if (catalogue.get("pagination") or {}).get("has_more") is True:
        raise RuntimeError("catalogue_truncated_requires_separate_pagination_probe")
    samples = []
    for comp in competitions:
        row = {
            "competition_id": comp["id"],
            "competition_name": comp["name"],
            "fixture_id": None,
            "fixture_lookup_status": "NOT_RUN",
            "statistics_http_status": None,
            "statistics_status": "NOT_RUN",
            "available_fields": [],
            "missing_fields": list(STAT_FIELDS),
            "first_half_fields": [],
        }
        endpoint = f"leagues/{comp['id']}/fixtures"
        http, payload, result = budget.get(endpoint, {
            "start_time": int(start.timestamp()),
            "end_time": int(now.timestamp()),
            "status": "finished", "page": 1, "per_page": 100,
        }, key)
        if result != "OK" or not isinstance(payload.get("data"), list):
            row["fixture_lookup_status"] = result
            row["statistics_status"] = "FIXTURE_LOOKUP_FAILED"
            samples.append(row)
            continue
        row["fixture_lookup_status"] = "OK"
        fixture = next((x for x in payload["data"] if isinstance(x, dict) and valid_id(x.get("id"))), None)
        if fixture is None:
            row["statistics_status"] = "NO_FINISHED_FIXTURE"
            samples.append(row)
            continue
        row["fixture_id"] = str(int(fixture["id"]))
        stats_http, stats_payload, stats_result = budget.get(
            f"fixtures/{row['fixture_id']}/statistics", {}, key
        )
        row["statistics_http_status"] = stats_http
        if stats_result == "OK":
            data = stats_payload.get("data")
            stats = data.get("statistics") if isinstance(data, dict) else None
            if isinstance(stats, dict):
                row["available_fields"] = sorted(k for k in STAT_FIELDS if k in stats and stats[k] is not None)
                row["missing_fields"] = sorted(set(STAT_FIELDS) - set(row["available_fields"]))
                first = stats.get("first_half")
                if isinstance(first, dict):
                    row["first_half_fields"] = sorted(k for k in STAT_FIELDS[:-1] if k in first and first[k] is not None)
                row["statistics_status"] = "OK_WITH_FIELDS" if row["available_fields"] else "OK_EMPTY"
            else:
                row["statistics_status"] = "OK_EMPTY"
        elif stats_result.startswith("HTTP_"):
            code = stats_http or 0
            row["statistics_status"] = "HTTP_403" if code == 403 else "HTTP_404" if code == 404 else "HTTP_429" if code == 429 else "HTTP_OTHER"
        else:
            row["statistics_status"] = stats_result
        samples.append(row)
        if budget.actual >= budget.maximum:
            break
    # Preserve one explicit row per catalogue competition, even if the budget
    # or a provider error prevented that competition from being tested.
    tested = {x["competition_id"] for x in samples}
    for comp in competitions:
        if comp["id"] not in tested:
            samples.append({
                "competition_id": comp["id"], "competition_name": comp["name"],
                "fixture_id": None, "fixture_lookup_status": "NOT_RUN",
                "statistics_http_status": None,
                "statistics_status": "REQUEST_BUDGET_EXHAUSTED",
                "available_fields": [], "missing_fields": list(STAT_FIELDS),
                "first_half_fields": [],
            })
    report = {
        "schema_version": 1,
        "mode": "read_only_statistics_capability_probe",
        "provider": "5DollarFootballAPI",
        "run_id": str(run_id),
        "retrieved_at": now.isoformat().replace("+00:00", "Z"),
        "window_start_utc": start.isoformat().replace("+00:00", "Z"),
        "window_end_utc": now.isoformat().replace("+00:00", "Z"),
        "request_budget": {
            "maximum_requests": maximum,
            "actual_requests": budget.actual,
            "endpoint_accounting": budget.accounting(),
        },
        "competition_count": len(competitions),
        "samples": sorted(samples, key=lambda x: x["competition_id"]),
        "side_effects": {
            "database_writes": 0, "imports": 0, "prediction_publications": 0,
        },
    }
    report["report_sha256"] = _hash(report)
    validate_report(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-requests", type=int, default=20)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--output", default="fivedollar_statistics_probe.json")
    args = parser.parse_args()
    if not 1 <= args.max_requests <= 20:
        parser.error("--max-requests must be between 1 and 20")
    if not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")
    key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not key:
        print("STATISTICS_PROBE: BLOCKED_MISSING_SECRET")
        return 2
    try:
        report = probe(key, args.max_requests, args.days, os.getenv("GITHUB_RUN_ID", "manual-local-run"))
    except RuntimeError as exc:
        print(f"STATISTICS_PROBE: FAILED ({str(exc)[:120]})")
        return 1
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = {}
    for row in report["samples"]:
        counts[row["statistics_status"]] = counts.get(row["statistics_status"], 0) + 1
    print(f"STATISTICS_PROBE: COMPLETE; competitions={report['competition_count']}; requests={report['request_budget']['actual_requests']}/{args.max_requests}; statuses={json.dumps(counts, sort_keys=True)}")
    print(f"REPORT_SHA256: {report['report_sha256']}")
    print(f"REPORT_FILE: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
