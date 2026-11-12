#!/usr/bin/env python3
"""Independent post-import audit for the VELTRIX isolated staging database."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
EXPECTED_ROLE = "neondb_owner"
MIGRATIONS = {
    "0001_persistent_foundation": "b5f6f1b5dbe6d7587c4876578f50d8327711f7fd26d03410f31a04db659d267c",
    "0002_historical_provenance": "619c556674e409ad5cd3a9ddc9ae578455207545d3435b9ece4e91a953fef49a",
    "0003_source_approval_status_events": "8c70a8a1a060949a4fca924b1b0854d94e125b2cbf6f677049e7e70b4a836a19",
}
COMPETITIONS = {
    "3118717965", "522514093", "4160026622", "3614399544",
    "686337048", "3405541143", "4212821298",
}


def _canonical_hash(value: dict) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_key_scan(value) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            name = str(key).casefold().replace("-", "_")
            if any(term in name for term in ("api_key", "authorization", "token", "password", "secret", "cookie")):
                return False
            if not _safe_key_scan(child):
                return False
    elif isinstance(value, list):
        return all(_safe_key_scan(item) for item in value)
    return True


def run_audit(database_url: str) -> dict:
    if os.getenv("VELTRIX_ENABLE_STAGING_IMPORT") != "YES":
        raise RuntimeError("STAGING_AUDIT_EXPLICIT_ENABLE_REQUIRED")
    if not database_url:
        raise RuntimeError("STAGING_DATABASE_URL_REQUIRED")
    if (urlparse(database_url).hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("STAGING_DATABASE_HOST_ALLOWLIST_MISMATCH")

    import psycopg

    failures = []
    report = {
        "schema_version": 1,
        "database": EXPECTED_DATABASE,
        "endpoint_host": EXPECTED_HOST,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_user")
            database, role = cur.fetchone()
            if database != EXPECTED_DATABASE:
                failures.append("DATABASE_NAME_MISMATCH")
            if role != EXPECTED_ROLE:
                failures.append("DATABASE_ROLE_MISMATCH")
            if role != EXPECTED_ROLE:
                failures.append("DATABASE_ROLE_MISMATCH")

            cur.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")
            observed_migrations = {v: h.strip() for v, h in cur.fetchall()}
            if observed_migrations != MIGRATIONS:
                failures.append("MIGRATION_CHECKSUM_MISMATCH")

            cur.execute("""
                SELECT id,provider,source_id,endpoint,request_id,http_status,
                       response_sha256,raw_body,response_headers,request_params,fetched_at
                FROM provider_responses ORDER BY id
            """)
            responses = {}
            response_hash_failures = 0
            secret_metadata_failures = 0
            raw_page_rows = {}
            for row in cur.fetchall():
                (response_id, provider, source_id, endpoint, request_id, status,
                 expected_hash, raw_body, response_headers, request_params, fetched_at) = row
                actual_hash = hashlib.sha256(bytes(raw_body)).hexdigest()
                if actual_hash != expected_hash.strip() or status != 200:
                    response_hash_failures += 1
                if not _safe_key_scan(response_headers) or not _safe_key_scan(request_params):
                    secret_metadata_failures += 1
                responses[response_id] = {
                    "provider": provider, "source_id": source_id, "endpoint": endpoint,
                    "request_id": request_id, "fetched_at": fetched_at,
                    "response_sha256": actual_hash,
                }
                if endpoint.endswith("/fixtures"):
                    try:
                        body = json.loads(bytes(raw_body).decode("utf-8"))
                        rows = body.get("data") if isinstance(body, dict) else None
                        if not isinstance(rows, list):
                            failures.append("RAW_FIXTURE_RESPONSE_SCHEMA_INVALID")
                            continue
                        for raw_row in rows:
                            fixture_id = str(int(raw_row["id"]))
                            key = (response_id, fixture_id)
                            if key in raw_page_rows:
                                failures.append("DUPLICATE_FIXTURE_ID_IN_RAW_PAGE")
                            raw_page_rows[key] = _canonical_hash(raw_row)
                    except Exception:
                        failures.append("RAW_FIXTURE_RESPONSE_PARSE_FAILED")

            cur.execute("""
                SELECT so.id,so.provider,so.source_id,so.data_type,so.provider_entity_id,
                       so.payload_sha256,so.payload,so.rights_approval_id,
                       so.provider_response_id,so.point_in_time_certifiable,
                       so.availability_basis,so.available_at,so.source_event_time,
                       pr.fetched_at,sa.competition_scope,f.kickoff_at,
                       COALESCE((
                           SELECT ev.status FROM source_approval_status_events ev
                           WHERE ev.approval_id=so.rights_approval_id
                             AND ev.effective_at<=pr.fetched_at
                           ORDER BY ev.effective_at DESC,ev.event_id DESC LIMIT 1
                       ),'MISSING') AS approval_status_at_fetch
                FROM source_observations so
                LEFT JOIN provider_responses pr ON pr.id=so.provider_response_id
                LEFT JOIN source_approvals sa ON sa.approval_id=so.rights_approval_id
                LEFT JOIN fixtures f ON f.source_observation_id=so.id
                ORDER BY so.id
            """)
            observations = cur.fetchall()
            payload_hash_failures = 0
            raw_link_failures = 0
            rights_failures = 0
            temporal_flag_failures = 0
            availability_proxy_failures = 0
            for row in observations:
                (obs_id, provider, source_id, data_type, entity_id, payload_hash,
                 payload, approval_id, response_id, point_in_time, availability_basis,
                 available_at, source_event_time, fetched_at, competition_scope,
                 fixture_kickoff, approval_status) = row
                if not isinstance(payload, dict) or _canonical_hash(payload) != payload_hash.strip():
                    payload_hash_failures += 1
                if response_id not in responses or (response_id, entity_id) not in raw_page_rows:
                    raw_link_failures += 1
                elif raw_page_rows[(response_id, entity_id)] != payload_hash.strip():
                    raw_link_failures += 1
                allowed = {x.strip() for x in (competition_scope or "").split(",") if x.strip()}
                league = payload.get("league") if isinstance(payload, dict) else {}
                league_id = str(league.get("id")) if isinstance(league, dict) else ""
                if (
                    provider != "5DollarFootballAPI"
                    or data_type != "fixture_result"
                    or approval_status != "APPROVED"
                    or not approval_id
                    or allowed != COMPETITIONS
                    or "*" in allowed
                    or entity_id != str(payload.get("id"))
                    or league_id not in allowed
                ):
                    rights_failures += 1
                if point_in_time is not False or availability_basis != "provider_finished_status_conservative_4d":
                    temporal_flag_failures += 1
                if (
                    fixture_kickoff is None
                    or source_event_time != fixture_kickoff
                    or available_at != fixture_kickoff + timedelta(days=4)
                ):
                    availability_proxy_failures += 1

            cur.execute("""
                SELECT count(*) FROM fixture_result_versions v
                JOIN source_observations so ON so.id=v.source_observation_id
                JOIN provider_responses pr ON pr.id=so.provider_response_id
                JOIN source_approvals sa ON sa.approval_id=v.rights_approval_id
            """)
            linked_result_versions = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM fixture_result_versions")
            result_versions = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM fixture_results
                WHERE source_observation_id IS NULL OR rights_approval_id IS NULL
            """)
            unprovenanced_results = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM fixtures
                WHERE provider='5DollarFootballAPI' AND source_observation_id IS NULL
            """)
            unprovenanced_fixtures = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM fixture_result_versions v
                JOIN fixtures f ON f.id=v.fixture_id
                JOIN source_observations so ON so.id=v.source_observation_id
                WHERE f.provider_fixture_id<>so.provider_entity_id OR f.provider<>so.provider
            """)
            fixture_observation_mismatches = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM fixture_results fr
                LEFT JOIN fixture_result_versions v ON v.fixture_id=fr.fixture_id
                WHERE v.fixture_id IS NULL
                   OR fr.source_observation_id<>v.source_observation_id
                   OR fr.home_score<>v.home_score OR fr.away_score<>v.away_score
            """)
            canonical_result_mismatches = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM fixtures f
                LEFT JOIN fixture_results fr ON fr.fixture_id=f.id
                WHERE f.provider='5DollarFootballAPI'
                  AND (f.status<>'FINISHED' OR fr.fixture_id IS NULL)
            """)
            unsettled_or_unresulted_fixtures = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM fixtures f
                JOIN competitions c ON c.id=f.competition_id
                WHERE f.provider='5DollarFootballAPI'
                  AND c.provider_competition_id NOT IN (
                    '3118717965','522514093','4160026622','3614399544',
                    '686337048','3405541143','4212821298'
                  )
            """)
            out_of_scope_fixtures = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM provider_entitlement_observations
                WHERE provider='5DollarFootballAPI'
                  AND source_id='5dollarfootballapi'
                  AND entitlement_status='ACTIVE'
                  AND competition_ids = %s::jsonb
            """, (json.dumps(sorted(COMPETITIONS)),))
            entitlement_snapshots = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM import_runs
                WHERE provider='5DollarFootballAPI' AND status='COMPLETED'
                  AND requests_used<=request_budget
                  AND records_seen=records_inserted+records_rejected+records_quarantined
                  AND manifest_sha256 IS NOT NULL
            """)
            completed_runs = cur.fetchone()[0]
            cur.execute("""
                SELECT count(*) FROM import_checkpoints
                WHERE status='COMPLETED'
            """)
            completed_checkpoints = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM ingestion_quarantine WHERE resolved_at IS NULL")
            open_quarantine = cur.fetchone()[0]

            report.update({
                "migration_count": len(observed_migrations),
                "provider_response_count": len(responses),
                "raw_response_hash_failures": response_hash_failures,
                "secret_metadata_failures": secret_metadata_failures,
                "source_observation_count": len(observations),
                "payload_hash_failures": payload_hash_failures,
                "raw_response_link_failures": raw_link_failures,
                "rights_provenance_failures": rights_failures,
                "point_in_time_flag_failures": temporal_flag_failures,
                "availability_proxy_failures": availability_proxy_failures,
                "result_version_count": result_versions,
                "linked_result_versions": linked_result_versions,
                "unprovenanced_results": unprovenanced_results,
                "unprovenanced_fixtures": unprovenanced_fixtures,
                "out_of_scope_fixtures": out_of_scope_fixtures,
                "fixture_observation_mismatches": fixture_observation_mismatches,
                "canonical_result_mismatches": canonical_result_mismatches,
                "unsettled_or_unresulted_fixtures": unsettled_or_unresulted_fixtures,
                "active_entitlement_snapshots": entitlement_snapshots,
                "completed_import_runs": completed_runs,
                "completed_checkpoints": completed_checkpoints,
                "open_quarantine_records": open_quarantine,
            })
            if response_hash_failures:
                failures.append("RAW_RESPONSE_HASH_FAILURE")
            if secret_metadata_failures:
                failures.append("SECRET_METADATA_LEAK")
            if payload_hash_failures:
                failures.append("PAYLOAD_HASH_FAILURE")
            if raw_link_failures:
                failures.append("RAW_RESPONSE_LINK_FAILURE")
            if rights_failures:
                failures.append("RIGHTS_PROVENANCE_FAILURE")
            if temporal_flag_failures:
                failures.append("POINT_IN_TIME_FLAG_FAILURE")
            if availability_proxy_failures:
                failures.append("AVAILABILITY_PROXY_RECONCILIATION_FAILURE")
            if linked_result_versions != result_versions:
                failures.append("RESULT_VERSION_LINK_FAILURE")
            if unprovenanced_results or unprovenanced_fixtures or out_of_scope_fixtures or fixture_observation_mismatches or canonical_result_mismatches or unsettled_or_unresulted_fixtures:
                failures.append("CANONICAL_RESULT_PROVENANCE_FAILURE")
            if not observations or not result_versions or len(responses) < 3:
                failures.append("EMPTY_STAGING_IMPORT")
            if entitlement_snapshots < 1:
                failures.append("ACTIVE_ENTITLEMENT_SNAPSHOT_MISSING")
            if completed_runs < 1 or completed_checkpoints < 1:
                failures.append("COMPLETED_IMPORT_ACCOUNTING_MISSING")
            report["failures"] = sorted(set(failures))
            report["status"] = "PASS" if not report["failures"] else "FAIL"
            material = json.dumps(report, sort_keys=True, separators=(",", ":"), default=str).encode()
            report["audit_sha256"] = hashlib.sha256(material).hexdigest()
            cur.execute("""
                INSERT INTO reconciliation_audits(
                    manifest_sha256,expected_migrations,applied_migrations,status,details,checked_at
                ) VALUES (%s,3,%s,%s,%s::jsonb,%s)
            """, (
                hashlib.sha256(material).hexdigest(),
                len(observed_migrations),
                report["status"],
                json.dumps(report, sort_keys=True, default=str),
                datetime.now(timezone.utc),
            ))
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/phase3/staging-audit.json")
    args = parser.parse_args()
    report = run_audit(os.getenv("DATABASE_URL", ""))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True, default=str))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
