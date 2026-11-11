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
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg.rows import dict_row

# Direct script execution places scripts/ on sys.path, not the repository root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.verify_strikerapi import ProbeError, call_api, validate_game
from scripts.reconcile_provider_fixtures import fivedollar_record, reconcile, striker_record

SCOPES = (
    ("soccer", "EPL", "strikerapi-free-fixtures-epl"),
    ("argentina", "ARG", "strikerapi-free-fixtures-argentina"),
    ("brazil", "BRA", "strikerapi-free-fixtures-brazil"),
)
PAGE_LIMIT = 50
EXPECTED_DRY_RUN_HOSTS = {
    "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech",
    "ep-ancient-block-bcb439pk-pooler.c-16.us-east-1.aws.neon.tech",
}
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


def fetch_fivedollar_epl(api_key: str, start: str, end: str) -> tuple[list[dict], int]:
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)
    end_dt = (datetime.fromisoformat(end) + timedelta(days=1)).replace(tzinfo=timezone.utc)
    params = {
        "start_time": int(start_dt.timestamp()),
        "end_time": int(end_dt.timestamp()),
        "status": "finished",
        "page": 1,
        "per_page": 100,
    }
    rows: list[dict] = []
    page = calls = 0
    while page < 10:
        page += 1
        calls += 1
        params["page"] = page
        url = "https://api.5dollarfootballapi.com/v1/leagues/4160026622/fixtures?" + urlencode(params)
        request = Request(url, headers={"Accept": "application/json",
                          "Authorization": f"Bearer {api_key}",
                          "User-Agent": "VELTRIX-FOOTBALL-read-only-import-dry-run/1.0"})
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"5Dollar EPL read-only request failed ({type(exc).__name__})") from None
        if not isinstance(payload, dict) or payload.get("success") != 1 or not isinstance(payload.get("data"), list):
            raise RuntimeError("5Dollar EPL response schema or success flag is invalid")
        rows.extend(item for item in payload["data"] if isinstance(item, dict))
        if not (payload.get("pagination") or {}).get("has_more"):
            return rows, calls
    raise RuntimeError("5Dollar EPL pagination exceeded 10-page dry-run safety cap")


def assert_isolated_database_target(dsn: str) -> str:
    """Refuse any DB host except the dedicated isolated Neon branch endpoint."""
    try:
        host = urlsplit(dsn).hostname
    except Exception:
        host = None
    if not host or host.lower() not in EXPECTED_DRY_RUN_HOSTS:
        raise RuntimeError("DRY_RUN_DATABASE_URL host is not the approved isolated Neon branch")
    return host.lower()


def read_database_snapshot(dsn: str) -> dict[str, int]:
    assert_isolated_database_target(dsn)
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


def read_existing_fixtures(dsn: str) -> dict[tuple[str, str], dict[str, Any]]:
    assert_isolated_database_target(dsn)
    query = """
        SELECT f.provider, f.provider_fixture_id, f.kickoff_at, f.status,
               c.provider AS competition_provider, c.provider_competition_id,
               ht.provider_team_id AS home_provider_team_id,
               at.provider_team_id AS away_provider_team_id,
               ht.name AS home_name, at.name AS away_name,
               r.home_score, r.away_score
        FROM public.fixtures f
        JOIN public.teams ht ON ht.id = f.home_team_id
        JOIN public.teams at ON at.id = f.away_team_id
        LEFT JOIN public.competitions c ON c.id = f.competition_id
        LEFT JOIN public.fixture_results r ON r.fixture_id = f.id
    """
    with psycopg.connect(dsn, connect_timeout=10, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            rows = conn.execute(query).fetchall()
    return {(row["provider"], row["provider_fixture_id"]): dict(row) for row in rows}


def compare_existing(candidate_records: list[dict], existing: dict[tuple[str, str], dict]) -> list[dict]:
    conflicts = []
    for candidate in candidate_records:
        key = (candidate["provider"], candidate["provider_fixture_id"])
        stored = existing.get(key)
        if stored is None:
            continue
        stored_kickoff = stored["kickoff_at"].astimezone(timezone.utc)
        incoming_kickoff = utc_timestamp(candidate["kickoff_utc"])
        if stored_kickoff != incoming_kickoff:
            conflicts.append({"kind": "provider_id_kickoff_conflict", "provider_fixture_id": key[1]})
        if str(stored["home_provider_team_id"]) != candidate["home_provider_team_id"] or str(stored["away_provider_team_id"]) != candidate["away_provider_team_id"]:
            conflicts.append({"kind": "provider_id_team_identity_conflict", "provider_fixture_id": key[1]})
        if (stored["competition_provider"] != candidate["provider"]
                or str(stored["provider_competition_id"]) != candidate["competition_key"]):
            conflicts.append({"kind": "provider_id_competition_identity_conflict", "provider_fixture_id": key[1]})
        if stored["status"] != "FINISHED":
            conflicts.append({"kind": "provider_id_status_conflict", "provider_fixture_id": key[1]})
        if stored["home_score"] is None or stored["away_score"] is None:
            conflicts.append({"kind": "provider_id_missing_existing_result", "provider_fixture_id": key[1]})
        elif (int(stored["home_score"]) != candidate["home_score"]
              or int(stored["away_score"]) != candidate["away_score"]):
            conflicts.append({"kind": "provider_id_score_conflict", "provider_fixture_id": key[1]})
    return conflicts


def main() -> int:
    key = os.getenv("STRIKERAPI_API_KEY", "").strip()
    dsn = os.getenv("DRY_RUN_DATABASE_URL", "").strip()
    dollar_key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not key or not dsn or not dollar_key:
        print(json.dumps({
            "status": "BLOCKED_MISSING_SECRET",
            "required_secrets": [
                name for name, value in (("STRIKERAPI_API_KEY", key), ("DRY_RUN_DATABASE_URL", dsn), ("FIVEDOLLARFOOTBALL_API_KEY", dollar_key)) if not value
            ],
            "database_writes": 0,
        }, indent=2))
        return 2

    now = datetime.now(timezone.utc)
    start = (now.date() - timedelta(days=WINDOW_DAYS)).isoformat()
    end = now.date().isoformat()
    assert_isolated_database_target(dsn)
    before = read_database_snapshot(dsn)
    existing = read_existing_fixtures(dsn)
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
    epl_striker_records: list[dict] = []
    all_issues = []
    candidate_records: list[dict] = []
    for league, code, rights_id in SCOPES:
        rows, calls, truncated = fetch_scope(key, league, start, end)
        total_calls += calls
        result = inspect_rows(rows, league, rights_id)
        all_issues.extend({"competition": code, **issue} for issue in result["issues"])
        candidate_records.extend(result["records"])
        if code == "EPL":
            epl_striker_records = [striker_record(row, league) for row in rows]
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
    all_issues.extend(compare_existing(candidate_records, existing))

    dollar_rows, dollar_calls = fetch_fivedollar_epl(dollar_key, start, end)
    dollar_records = [fivedollar_record(row) for row in dollar_rows]
    cross = reconcile(
        epl_striker_records,
        dollar_records,
        competition_map={"EPL": "4160026622"},
        tolerance_seconds=300,
    )
    total_calls += dollar_calls
    cross_conflicts = [
        item for item in cross["decisions"]
        if item["outcome"] in {"STATUS_CONFLICT", "RESULT_CONFLICT", "IDENTITY_CONFLICT",
                               "AMBIGUOUS_MULTIPLE_CANDIDATES", "DUPLICATE_SOURCE_ID",
                               "INVALID_SOURCE_ROW"}
    ]
    if cross_conflicts:
        all_issues.extend({"competition": "EPL", "kind": "cross_provider_" + item["outcome"].lower()}
                           for item in cross_conflicts)
    if not cross["acceptance_pass"]:
        all_issues.append({"competition": "EPL", "kind": "cross_provider_reconciliation_not_accepted"})
    if (cross["accounting"]["striker"]["matched"] != cross["accounting"]["striker"]["total"]
            or cross["accounting"]["fivedollar"]["matched"] != cross["accounting"]["fivedollar"]["total"]):
        all_issues.append({"competition": "EPL", "kind": "cross_provider_source_accounting_not_fully_matched"})
    after = read_database_snapshot(dsn)
    report["database_after"] = after
    report["database_unchanged"] = before == after
    report["database_writes"] = 0
    report["imports"] = 0
    report["provider_api_calls"] = total_calls
    report["cross_provider_epl"] = {k: v for k, v in cross.items() if k != "decisions"}
    report["cross_provider_epl"]["decision_counts"] = {outcome: sum(1 for item in cross["decisions"] if item["outcome"] == outcome) for outcome in sorted({item["outcome"] for item in cross["decisions"]})}
    report["issues"] = all_issues
    report["pass"] = report["database_unchanged"] and not all_issues
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
