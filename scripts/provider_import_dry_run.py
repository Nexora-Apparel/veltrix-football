#!/usr/bin/env python3
"""Provider-backed, zero-write import qualification for approved fixture scopes.

Connects only to DRY_RUN_DATABASE_URL (must point to the isolated Neon child
branch), reads provider pages, validates identity/time/provenance/score integrity,
and compares against existing isolated records. No SQL write statements exist.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

from scripts.verify_strikerapi import ProbeError, call_api, validate_game

SCOPES = (
    ("soccer", "EPL", "strikerapi-free-fixtures-epl"),
    ("argentina", "ARG", "strikerapi-free-fixtures-argentina"),
    ("brazil", "BRA", "strikerapi-free-fixtures-brazil"),
)
PAGE_LIMIT = 50
MAX_PAGES = 3
WINDOW_DAYS = 90
DOMAIN_TABLES = ("competitions", "teams", "fixtures", "fixture_results", "source_observations", "import_runs", "import_checkpoints")


def canonical_json_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing kickoff")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff timezone missing")
    return parsed.astimezone(timezone.utc)


def fetch_scope(key: str, league: str, start: str, end: str) -> tuple[list[dict], int, bool]:
    rows: list[dict] = []
    offset = calls = 0
    for _ in range(MAX_PAGES):
        data = call_api(key, league, "final", start, end, offset)
        calls += 1
        games = data.get("games")
        if not isinstance(games, list):
            raise ProbeError("provider response missing games array")
        rows.extend(games)
        next_offset = data.get("next_offset")
        if next_offset is None:
            return rows, calls, False
        if isinstance(next_offset, bool) or not isinstance(next_offset, int) or next_offset <= offset or not games:
            raise ProbeError("provider pagination is invalid")
        offset = next_offset
    return rows, calls, True


def inspect_rows(rows: list[dict], league: str, rights_id: str) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    ids: dict[str, int] = defaultdict(int)
    identities: dict[tuple, list[dict]] = defaultdict(list)
    accepted = []
    for row in rows:
        valid, reason = validate_game(row, "final")
        if not valid:
            issues.append({"kind": "invalid_record", "reason": reason})
            continue
        source_id = str(row["game_id"])
        ids[source_id] += 1
        home, away = row["home"], row["away"]
        home_id, away_id = str(home["team_id"]), str(away["team_id"])
        if home_id == away_id or clean_name(home["name"]) == clean_name(away["name"]):
            issues.append({"kind": "identity_collision", "provider_fixture_id": source_id})
            continue
        kickoff = utc_timestamp(row["starts_at"])
        hs, aws = home.get("score"), away.get("score")
        if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (hs, aws)):
            issues.append({"kind": "score_invalid", "provider_fixture_id": source_id})
            continue
        digest = canonical_json_hash(row)
        normalized = {
            "provider": "strikerapi",
            "provider_fixture_id": source_id,
            "competition_key": league,
            "rights_approval_id": rights_id,
            "home_provider_team_id": home_id,
            "away_provider_team_id": away_id,
            "home_name": str(home["name"]).strip(),
            "away_name": str(away["name"]).strip(),
            "kickoff_utc": kickoff.isoformat(),
            "status": row["status"],
            "home_score": hs,
            "away_score": aws,
            "payload_sha256": digest,
        }
        identity = (league, kickoff.isoformat(), home_id, away_id)
        identities[identity].append(normalized)
        accepted.append(normalized)

    for source_id, count in ids.items():
        if count > 1:
            issues.append({"kind": "duplicate_provider_fixture_id", "provider_fixture_id": source_id})
    for identity, records in identities.items():
        if len(records) > 1:
            issues.append({"kind": "duplicate_fixture_identity", "identity": repr(identity)})
        score_pairs = {(x["home_score"], x["away_score"]) for x in records}
        if len(score_pairs) > 1:
            issues.append({"kind": "score_conflict_within_provider", "identity": repr(identity)})

    return {
        "rows_received": len(rows),
        "records_normalized": len(accepted),
        "unique_provider_ids": len(ids),
        "duplicate_provider_ids": sum(1 for n in ids.values() if n > 1),
        "issues": issues,
        "records": accepted,
    }


def read_database_snapshot(dsn: str) -> dict[str, int]:
    snapshot: dict[str, int] = {}
    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL statement_timeout = '15s'")
            dbname = conn.execute("SELECT current_database() AS name").fetchone()["name"]
            if dbname != "veltrix-football":
                raise RuntimeError("DRY_RUN_DATABASE_URL is not the expected football database")
            for table in DOMAIN_TABLES:
                snapshot[table] = conn.execute(
                    "SELECT count(*) AS n FROM public." + table
                ).fetchone()["n"]
    return snapshot


def main() -> int:
    key = os.getenv("STRIKERAPI_API_KEY", "").strip()
    dsn = os.getenv("DRY_RUN_DATABASE_URL", "").strip()
    if not key or not dsn:
        print(json.dumps({
            "status": "BLOCKED_MISSING_SECRET",
            "required_secrets": [
                name for name, value in (("STRIKERAPI_API_KEY", key), ("DRY_RUN_DATABASE_URL", dsn)) if not value
            ],
            "database_writes": 0,
        }, indent=2))
        return 2

    now = datetime.now(timezone.utc)
    start = (now.date() - timedelta(days=WINDOW_DAYS)).isoformat()
    end = now.date().isoformat()
    before = read_database_snapshot(dsn)
    report: dict[str, Any] = {
        "mode": "provider_backed_import_dry_run",
        "retrieved_at_utc": now.isoformat(),
        "window": {"start": start, "end": end},
        "approved_scopes": [],
        "excluded_scopes": {"NWSL": "vendor fixture-count clarification outstanding"},
        "database_before": before,
        "database_writes": 0,
        "imports": 0,
    }
    total_calls = 0
    all_issues = []
    for league, code, rights_id in SCOPES:
        rows, calls, truncated = fetch_scope(key, league, start, end)
        total_calls += calls
        result = inspect_rows(rows, league, rights_id)
        all_issues.extend({"competition": code, **issue} for issue in result["issues"])
        report["approved_scopes"].append({
            "competition": code,
            "provider": "StrikerAPI",
            "rights_approval_id": rights_id,
            "api_calls": calls,
            "pagination_truncated": truncated,
            **{k: v for k, v in result.items() if k != "records"},
            "candidate_imports": len(result["records"]),
            "records": result["records"],
        })
        if truncated:
            all_issues.append({"competition": code, "kind": "pagination_truncated"})
    after = read_database_snapshot(dsn)
    report["database_after"] = after
    report["database_unchanged"] = before == after
    report["database_writes"] = 0
    report["imports"] = 0
    report["provider_api_calls"] = total_calls
    report["issues"] = all_issues
    report["pass"] = report["database_unchanged"] and not all_issues
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
