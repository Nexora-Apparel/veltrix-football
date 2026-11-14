#!/usr/bin/env python3
"""Read-only verification of proposed StrikerAPI/5Dollar EPL team-ID aliases."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

STRIKER_URL = "https://mcp.strikerapi.com/v1/list_teams"
DOLLAR_BASE = "https://api.5dollarfootballapi.com/v1/teams"
TIMEOUT = 25
STRIKER_SEASON = 2026
def striker_request_body() -> dict:
    # list_teams documents season as its only request parameter.
    return {"season": STRIKER_SEASON}
# Candidate pairs discovered in docs/STRIKERAPI_ALIAS_CANDIDATE_REVIEW.md.
CANDIDATES = [
    ("306", "2133281510"), ("331", "1298357733"),
    ("337", "2493508502"), ("349", "4091605164"),
    ("357", "2580270069"), ("359", "2592538664"),
    ("360", "762247077"), ("361", "2064095235"),
    ("362", "1807930046"), ("363", "3399423062"),
    ("364", "94606195"), ("366", "2683519683"),
    ("367", "2091670802"), ("368", "761437401"),
    ("370", "248206832"), ("373", "2014429473"),
    ("382", "3103334772"), ("384", "139660649"),
    ("388", "1193753576"), ("393", "2220360869"),
]

MAX_PROVIDER_CALLS = 1 + len(CANDIDATES)


class ProbeError(RuntimeError):
    pass


def request_json(url: str, headers: dict, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=headers, method="GET" if body is None else "POST")
    try:
        with urlopen(req, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if response.status != 200 or not isinstance(payload, dict):
                raise ProbeError("provider returned an unexpected response")
            return payload
    except HTTPError as exc:
        raise ProbeError(f"provider HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("provider network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("provider returned invalid JSON") from None


def unwrap_striker(payload: dict) -> list[dict]:
    data = payload.get("data", payload)
    teams = data.get("teams") if isinstance(data, dict) else None
    if not isinstance(teams, list):
        raise ProbeError("StrikerAPI list_teams response missing teams array")
    return teams


def unwrap_dollar(payload: dict, expected_id: str) -> dict:
    if payload.get("success") not in (1, True, "1"):
        raise ProbeError("5DollarFootballAPI team lookup was not successful")
    team = payload.get("data")
    if not isinstance(team, dict):
        raise ProbeError("5DollarFootballAPI team lookup missing data object")
    if str(team.get("id", "")) != expected_id or not isinstance(team.get("name"), str):
        raise ProbeError("5DollarFootballAPI team identity response is invalid")
    return team


def build_report(striker_teams: list[dict], dollar_teams: dict[str, dict]) -> dict:
    striker_by_id = {
        str(team.get("team_id")): team for team in striker_teams
        if isinstance(team, dict) and team.get("team_id") is not None
    }
    rows = []
    for striker_id, dollar_id in CANDIDATES:
        s = striker_by_id.get(striker_id)
        d = dollar_teams.get(dollar_id)
        if not s or not d:
            rows.append({
                "striker_team_id": striker_id, "fivedollar_team_id": dollar_id,
                "status": "NOT_VERIFIED", "reason": "team ID absent from provider catalogue response",
            })
            continue
        s_name = s.get("name") or s.get("display_name")
        d_name = d.get("name")
        if not isinstance(s_name, str) or not isinstance(d_name, str):
            status, reason = "NOT_VERIFIED", "provider catalogue name missing"
        else:
            status, reason = "CATALOGUE_CONFIRMED", "each provider returned this ID and its own team name"
        rows.append({
            "striker_team_id": striker_id, "striker_name": s_name,
            "striker_short_name": s.get("short_name"), "striker_abbrev": s.get("abbrev"),
            "fivedollar_team_id": dollar_id, "fivedollar_name": d_name,
            "status": status, "reason": reason,
        })
    verified = sum(x["status"] == "CATALOGUE_CONFIRMED" for x in rows)
    return {
        "schema_version": 1,
        "mode": "read_only_provider_catalogue_verification",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "striker_endpoint": "POST /v1/list_teams",
        "striker_query": {"season": STRIKER_SEASON},
        "documented_striker_credits": 1,
        "fivedollar_calls": len(CANDIDATES),
        "maximum_provider_calls": MAX_PROVIDER_CALLS,
        "fivedollar_endpoint": "GET /v1/teams/{id}",
        "candidate_count": len(CANDIDATES),
        "verified_count": verified,
        "all_candidates_verified": verified == len(CANDIDATES),
        "database_writes": 0,
        "imports": 0,
        "canonical_merges": 0,
        "candidates": rows,
    }


def main() -> int:
    striker_key = os.getenv("STRIKERAPI_API_KEY", "").strip()
    dollar_key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not striker_key or not dollar_key:
        print("TEAM_ALIAS_VERIFICATION: BLOCKED_MISSING_SECRET")
        return 2
    try:
        striker_payload = request_json(
            STRIKER_URL,
            {"Accept": "application/json", "Content-Type": "application/json", "x-api-key": striker_key},
            striker_request_body(),
        )
        striker_teams = unwrap_striker(striker_payload)
        dollar_teams = {}
        for _, dollar_id in CANDIDATES:
            payload = request_json(
                f"{DOLLAR_BASE}/{dollar_id}",
                {"Accept": "application/json", "Authorization": f"Bearer {dollar_key}"},
            )
            dollar_teams[dollar_id] = unwrap_dollar(payload, dollar_id)
            time.sleep(0.2)
    except ProbeError as exc:
        print(f"TEAM_ALIAS_VERIFICATION_FAILED: {str(exc)[:160]}")
        print("DATABASE_WRITES: 0; IMPORTS: 0; CANONICAL_MERGES: 0")
        return 1

    report = build_report(striker_teams, dollar_teams)
    out = Path("strikerapi_5dollar_team_alias_verification.json")
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"TEAM_ALIAS_VERIFIED: {report['verified_count']}/{report['candidate_count']}")
    print(f"TEAM_ALIAS_REPORT: {out.name}")
    print("DATABASE_WRITES: 0; IMPORTS: 0; CANONICAL_MERGES: 0")
    return 0 if report["all_candidates_verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
