#!/usr/bin/env python3
"""One-request, read-only 5DollarFootballAPI entitlement check.

This module calls only GET /v1/status. It never calls leagues, fixtures, odds,
or odds-history endpoints and never writes to a database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://api.5dollarfootballapi.com/v1/status"
USER_AGENT = "VELTRIX-5Dollar-Status-Only/1.0"
ALLOWED_HEADERS = (
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "retry-after",
)


class ProbeError(RuntimeError):
    """Safe, non-secret-bearing probe failure."""


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def fetch_status(api_key: str, opener=urlopen) -> tuple[int, bytes, dict[str, str]]:
    if not api_key or not api_key.strip():
        raise ProbeError("MISSING_SECRET")
    request = Request(
        BASE_URL,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with opener(request, timeout=20) as response:
            status_code = int(response.status)
            body = response.read()
            headers = {name.lower(): str(response.headers.get(name)) for name in ALLOWED_HEADERS
                       if response.headers.get(name) is not None}
    except HTTPError as exc:
        # Do not serialize provider error bodies or headers; they may contain
        # account-specific information. No retry is attempted.
        raise ProbeError(f"HTTP_{exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("NETWORK_ERROR") from None
    return status_code, body, headers


def build_evidence(api_key: str, request_fn=fetch_status, now_fn=None) -> dict:
    now = now_fn() if now_fn else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ProbeError("CLOCK_NOT_TIMEZONE_AWARE")
    status_code, raw_body, quota_headers = request_fn(api_key)
    raw_hash = hashlib.sha256(raw_body).hexdigest()
    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = None

    schema_ok = (
        status_code == 200
        and isinstance(parsed, dict)
        and parsed.get("success") in (1, True)
        and isinstance(parsed.get("data"), dict)
    )
    data = parsed.get("data") if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict) else {}
    # Keep the exact provider value. Do not infer a plan from limits or quota.
    plan_value = data.get("plan")
    plan = plan_value if isinstance(plan_value, str) else None
    ultra_confirmed = bool(schema_ok and plan is not None and plan.strip().casefold() == "ultra")
    evidence = {
        "schema_version": 1,
        "provider": "5DollarFootballAPI",
        "endpoint": "/v1/status",
        "http_status": status_code,
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "request_count": 1,
        "provider_calls_performed": ["/v1/status"],
        "provider_calls_forbidden_and_not_attempted": [
            "/v1/leagues",
            "/v1/fixtures",
            "/v1/odds",
            "/v1/fixtures/{id}/odds/history",
        ],
        "response_schema_valid": bool(schema_ok),
        "plan": plan,
        "ultra_confirmed": ultra_confirmed,
        "entitlement_decision": (
            "ULTRA_CONFIRMED_STATUS_ONLY"
            if ultra_confirmed
            else "ULTRA_NOT_CONFIRMED_DO_NOT_CALL_ODDS_HISTORY"
        ),
        "limits": data.get("limits") if isinstance(data.get("limits"), dict) else None,
        "usage": data.get("usage") if isinstance(data.get("usage"), dict) else None,
        "quota_headers": quota_headers,
        "raw_response_utf8": raw_body.decode("utf-8", errors="replace"),
        "raw_response_sha256": raw_hash,
        "side_effects": {
            "database_writes": 0,
            "odds_requests": 0,
            "odds_history_requests": 0,
            "fixture_requests": 0,
            "league_requests": 0,
            "prediction_writes": 0,
            "telegram_messages": 0,
        },
    }
    evidence["evidence_sha256"] = canonical_sha256(evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="artifacts/5dollar-status/evidence.json")
    args = parser.parse_args()
    try:
        evidence = build_evidence(os.environ.get("FIVEDOLLARFOOTBALL_API_KEY", ""))
    except ProbeError as exc:
        print(f"VELTRIX_5D_STATUS_PROBE: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "VELTRIX_5D_STATUS_PROBE: "
        f"http={evidence['http_status']} "
        f"schema_valid={str(evidence['response_schema_valid']).lower()} "
        f"plan={evidence['plan'] or 'NOT_REPORTED'} "
        f"ultra_confirmed={str(evidence['ultra_confirmed']).lower()} "
        f"requests=1 "
        f"raw_sha256={evidence['raw_response_sha256']} "
        f"evidence_sha256={evidence['evidence_sha256']}"
    )
    return 0 if evidence["response_schema_valid"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
