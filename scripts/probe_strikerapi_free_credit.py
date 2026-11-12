#!/usr/bin/env python3
"""One-credit StrikerAPI free-balance check; no match data or bulk collection."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://mcp.strikerapi.com/v1/list_teams"


class ProbeError(RuntimeError):
    pass


def _send(api_key: str):
    request = Request(
        URL,
        data=json.dumps({"season": 2025, "league": "soccer"}).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "User-Agent": "VELTRIX-Phase1-StrikerAPI-credit-check/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload, response.headers
    except HTTPError as exc:
        if exc.code == 402:
            return 402, {}, exc.headers
        raise ProbeError(f"HTTP_{exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("NETWORK_ERROR") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("INVALID_JSON") from None


def _int_header(headers, name):
    try:
        return int(headers.get(name))
    except (TypeError, ValueError):
        return None


def _hash(report: dict) -> str:
    body = dict(report)
    body.pop("report_sha256", None)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def probe(api_key: str, send=_send) -> dict:
    if not api_key.strip():
        status, payload, headers = 0, {}, {}
        probe_status = "MISSING_SECRET"
    else:
        status, payload, headers = send(api_key)
        if status == 200 and isinstance(payload, dict):
            teams = payload.get("teams")
            probe_status = "AUTH_OK" if isinstance(teams, list) and teams else "AUTH_OK_EMPTY_TEAMS"
        elif status == 402:
            probe_status = "HTTP_402_CREDITS_EXHAUSTED"
        else:
            probe_status = f"HTTP_{status}_UNEXPECTED"
    remaining = _int_header(headers, "X-Credits-Remaining")
    used = _int_header(headers, "X-Credits-Used")
    if probe_status == "HTTP_402_CREDITS_EXHAUSTED":
        remaining = 0
        used = 0
    report = {
        "schema_version": 1,
        "provider": "StrikerAPI",
        "mode": "one_credit_static_team_reference_balance_check",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": probe_status,
        "http_status": status,
        "credits_used": used,
        "credits_remaining": remaining,
        "team_count": len(payload.get("teams", [])) if isinstance(payload, dict) and isinstance(payload.get("teams"), list) else 0,
        "request_count": 1 if api_key.strip() else 0,
        "maximum_credits_spent": 1,
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
    if report.get("provider") != "StrikerAPI" or report.get("mode") != "one_credit_static_team_reference_balance_check":
        raise ValueError("scope_invalid")
    if report.get("request_count") not in (0, 1):
        raise ValueError("request_count_invalid")
    if report.get("maximum_credits_spent") != 1:
        raise ValueError("credit_cap_invalid")
    if report.get("side_effects", {}).get("database_writes") != 0:
        raise ValueError("side_effects_invalid")
    if report.get("report_sha256") != _hash(report):
        raise ValueError("report_hash_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/phase1/strikerapi-account.json")
    args = parser.parse_args()
    try:
        report = probe(os.getenv("STRIKERAPI_API_KEY", ""))
        validate_report(report)
    except ProbeError as exc:
        print(f"STRIKERAPI_ACCOUNT_PROBE: {exc}")
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    github_output = os.getenv("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as handle:
            handle.write(f"credits_remaining={report.get('credits_remaining') or 0}\n")
            handle.write(f"probe_status={report['status']}\n")
    print(
        "STRIKERAPI_ACCOUNT_PROBE: "
        f"status={report['status']} "
        f"credits_remaining={report.get('credits_remaining')} "
        f"credits_used={report.get('credits_used')} "
        f"sha256={report['report_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
