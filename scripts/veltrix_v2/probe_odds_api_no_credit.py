#!/usr/bin/env python3
"""No-credit The Odds API preflight for historical football odds research.

Calls only GET /v4/sports/?all=true. It does not call historical odds,
historical events, markets, or price endpoints and does not write to Neon.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.phase4_odds_account_probe import _fetch_sports

BRAZIL_SERIE_B_KEY = "soccer_brazil_serie_b"
ENDPOINT = "/v4/sports/?all=true"


def build_report(fetcher=_fetch_sports, api_key: str | None = None) -> dict:
    key = api_key if api_key is not None else os.environ.get("THE_ODDS_API_KEY", "")
    if not key.strip():
        raise RuntimeError("THE_ODDS_API_KEY_MISSING")
    requested_at, retrieved_at, body, headers, envelope, sports = fetcher(key)
    quota = envelope.quota_evidence
    brazil_available = BRAZIL_SERIE_B_KEY in sports
    zero_credit = quota.complete and quota.requests_last == 0
    return {
        "status": "PASS_NO_CREDIT" if brazil_available and zero_credit else "UNVERIFIED",
        "provider": "the_odds_api",
        "endpoint": ENDPOINT,
        "request_started_at": requested_at.isoformat(),
        "response_received_at": retrieved_at.isoformat(),
        "response_sha256": hashlib.sha256(body).hexdigest(),
        "sports_returned": len(sports),
        "brazil_serie_b_sport_key": BRAZIL_SERIE_B_KEY,
        "brazil_serie_b_available": brazil_available,
        "quota_headers_complete": quota.complete,
        "quota_requests_used": quota.requests_used,
        "quota_requests_remaining": quota.requests_remaining,
        "quota_requests_last": quota.requests_last,
        "request_cost_credits": quota.requests_last,
        "historical_odds_calls_made": 0,
        "database_writes": 0,
        "raw_response_uploaded": False,
        "api_key_emitted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    report = build_report()
    print(json.dumps(report, sort_keys=True))
    if report["status"] != "PASS_NO_CREDIT":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
