#!/usr/bin/env python3
"""Read-only 5Dollar account-plan and competition catalogue check for Phase 1."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://api.5dollarfootballapi.com/v1"


class ProbeError(RuntimeError):
    pass


def _request(path: str, key: str):
    req = Request(
        BASE + path,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "VELTRIX-Phase1-Provider-Qualification/1.0",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = response.headers
            status = response.status
    except HTTPError as exc:
        raise ProbeError(f"HTTP_{exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("NETWORK_ERROR") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("INVALID_JSON") from None
    if status != 200 or not isinstance(payload, dict) or payload.get("success") not in (1, True):
        raise ProbeError("UNSUCCESSFUL_RESPONSE")
    return payload, headers


def _hash(report: dict) -> str:
    body = dict(report)
    body.pop("report_sha256", None)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def probe(key: str, request=_request) -> dict:
    if not key.strip():
        raise ProbeError("MISSING_SECRET")
    status_payload, status_headers = request("/status", key)
    leagues_payload, league_headers = request("/leagues", key)
    if not isinstance(status_payload, dict) or not isinstance(status_payload.get("data"), dict):
        raise ProbeError("STATUS_SCHEMA_INVALID")
    if not isinstance(leagues_payload, dict):
        raise ProbeError("LEAGUE_CATALOGUE_SCHEMA_INVALID")
    status_data = status_payload["data"]
    leagues_data = leagues_payload.get("data")
    if isinstance(leagues_data, dict) and isinstance(leagues_data.get("leagues"), list):
        leagues_data = leagues_data["leagues"]
    if not isinstance(leagues_data, list):
        raise ProbeError("LEAGUE_CATALOGUE_SCHEMA_INVALID")

    competitions = []
    for row in leagues_data:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        country = row.get("country")
        if isinstance(country, dict):
            country = country.get("name") or country.get("code")
        competitions.append({
            "id": str(row.get("id")),
            "name": str(row.get("name") or "unknown")[:100],
            "country": str(country or "not_reported")[:60],
        })

    limits = status_data.get("limits") if isinstance(status_data.get("limits"), dict) else {}
    usage = status_data.get("usage") if isinstance(status_data.get("usage"), dict) else {}
    report = {
        "schema_version": 1,
        "provider": "5DollarFootballAPI",
        "mode": "read_only_account_plan_and_catalogue_check",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "OK",
        "plan": str(status_data.get("plan") or "not_reported"),
        "limits": {
            "rate_limit": limits.get("rate_limit"),
            "rate_window_seconds": limits.get("rate_window_seconds"),
            "burst_per_minute": limits.get("burst_per_minute"),
        },
        "usage_today": usage.get("today"),
        "competition_count_page_1": len(competitions),
        "competitions": competitions,
        "pagination": {
            "has_more": (leagues_payload.get("pagination") or {}).get("has_more"),
        },
        "quota_headers": {
            "status_limit": status_headers.get("X-RateLimit-Limit"),
            "status_remaining": status_headers.get("X-RateLimit-Remaining"),
            "catalogue_limit": league_headers.get("X-RateLimit-Limit"),
            "catalogue_remaining": league_headers.get("X-RateLimit-Remaining"),
        },
        "request_count": 2,
        "side_effects": {
            "database_writes": 0,
            "imports": 0,
            "prediction_changes": 0,
            "telegram_messages": 0,
            "deployments": 0,
        },
    }
    report["report_sha256"] = _hash(report)
    return report


def validate_report(report: dict) -> None:
    if not isinstance(report, dict) or report.get("provider") != "5DollarFootballAPI":
        raise ValueError("provider_invalid")
    if report.get("mode") != "read_only_account_plan_and_catalogue_check":
        raise ValueError("mode_invalid")
    if report.get("request_count") != 2:
        raise ValueError("request_count_invalid")
    if report.get("side_effects", {}).get("database_writes") != 0:
        raise ValueError("side_effects_invalid")
    if report.get("report_sha256") != _hash(report):
        raise ValueError("report_hash_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/phase1_fivedollar_account.json")
    args = parser.parse_args()
    try:
        report = probe(os.getenv("FIVEDOLLARFOOTBALL_API_KEY", ""))
        validate_report(report)
    except ProbeError as exc:
        print(f"FIVEDOLLAR_ACCOUNT_PROBE: {exc}")
        return 2
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "FIVEDOLLAR_ACCOUNT_PROBE: "
        f"plan={report['plan']} "
        f"rate_limit={report['limits']['rate_limit']} "
        f"burst={report['limits']['burst_per_minute']} "
        f"competitions={report['competition_count_page_1']} "
        f"sha256={report['report_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
