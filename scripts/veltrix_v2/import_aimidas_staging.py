#!/usr/bin/env python3
"""Import a pinned AI Midas CSV pack into isolated Neon staging only.

The importer stores exact file bytes and file-level provenance. It does not
normalize match rows, create fixture crosswalks, write production, or admit
features to a model. Every observation is explicitly non-PIT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.veltrix_v2.collect_aimidas_snapshot import (
    APPROVAL_ID, REPOSITORY, SOURCE_COMMIT, SOURCE_FILES,
)
from scripts.veltrix_v2.verify_aimidas_snapshot import verify_pack

EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
EXPECTED_ROLE = "neondb_owner"
PROVIDER = "AI Midas Football Data"
SOURCE_ID = "ai-midas-github-csv"
APPROVAL_EVIDENCE_SHA256 = "c4e227329b08e7d75db41cc197a9c073f99100b3b1dc5930d68ad591cfc1f7c7"
APPROVAL_EVIDENCE_URI = (
    "https://github.com/Nexora-Apparel/veltrix-football/blob/"
    "5b887c03604f45f6972bbf6c53613f064264e528/docs/legal/"
    "veltrix-all-source-noncommercial-authorization-2026-11-15.md"
)
MIGRATIONS = {
    "0001_persistent_foundation": "b5f6f1b5dbe6d7587c4876578f50d8327711f7fd26d03410f31a04db659d267c",
    "0002_historical_provenance": "619c556674e409ad5cd3a9ddc9ae578455207545d3435b9ece4e91a953fef49a",
    "0003_source_approval_status_events": "8c70a8a1a060949a4fca924b1b0854d94e125b2cbf6f677049e7e70b4a836a19",
    "0004_point_in_time_feature_capture": "74fe07102dd038f79da380744becdc596537fbc063ada4b70022b075af0a108d",
    "0005_provider_credit_reservation_ledger": "185097a7af0c54b35ff11be873518a82e105ffe52e1def4c236dd6a3f07bc29a",
    "0006_provider_quota_evidence": "654816ebb4a93e52178f32896519d8ec6fd00f5c4532fdd29dd5c57be6bd7c10",
    "0007_provider_capture_state_events": "6b21862a5820fb3a2bbf501dbaa363a00d9036083ac27d9ef10aff2855cabc50",
    "0008_prospective_paper_ledger": "d679e9c3521e325b39cd74b059b2f7e229ad0336403e519dd176315d7dc119da",
    "0009_telegram_delivery_claims": "60f147864651c7da9d06cd5cf5914115bcc77205a7ba181d6760e129f8a7895f",
    "0010_telegram_delivery_reconciliation": "2aa079df0c16eefbab9eb55961419d208a6788764c85fe2a0fd81e2bd00d9378",
    "0011_odds_quote_observations": "c72763fe3ea9f5b004731c0bfb03a38dc06633c9effc8ef0c0d678ad207c7a4d",
}
MANIFEST_KEY = f"aimidas-{SOURCE_COMMIT}-csv-pack-v1"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def validate_manifest(input_dir: Path) -> tuple[dict, dict[str, bytes], str]:
    verification = verify_pack(input_dir)
    if verification.get("status") != "PASS" or verification.get("files_verified") != len(SOURCE_FILES):
        raise RuntimeError("AIMIDAS_INDEPENDENT_SNAPSHOT_VERIFICATION_FAILED")
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("rights_approval_id") != APPROVAL_ID:
        raise RuntimeError("AIMIDAS_APPROVAL_ID_MISMATCH")
    if manifest.get("source_commit_sha") != SOURCE_COMMIT or manifest.get("source_repository") != REPOSITORY:
        raise RuntimeError("AIMIDAS_SOURCE_PIN_MISMATCH")
    files: dict[str, bytes] = {}
    for spec in SOURCE_FILES:
        record = next((item for item in manifest["files"] if item.get("path") == spec.path), None)
        if not record:
            raise RuntimeError("AIMIDAS_FILE_RECORD_MISSING:" + spec.path)
        raw_path = input_dir / "snapshots" / spec.path
        raw = raw_path.read_bytes()
        if sha256(raw) != record.get("sha256") or len(raw) != record.get("actual_bytes"):
            raise RuntimeError("AIMIDAS_FILE_HASH_MISMATCH:" + spec.path)
        files[spec.path] = raw
    return manifest, files, sha256(canonical_json(manifest))


def preflight(conn, database_url: str) -> None:
    if os.getenv("VELTRIX_ENABLE_AIMIDAS_STAGING_IMPORT") != "YES":
        raise RuntimeError("AIMIDAS_STAGING_IMPORT_EXPLICIT_ENABLE_REQUIRED")
    parsed = urlparse(database_url)
    if (parsed.hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("AIMIDAS_STAGING_HOST_ALLOWLIST_MISMATCH")
    if parse_qs(parsed.query).get("sslmode", [""])[0].casefold() not in {
        "require", "verify-ca", "verify-full"
    }:
        raise RuntimeError("AIMIDAS_STAGING_TLS_REQUIRED")
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(),current_user")
        database, role = cur.fetchone()
        if database != EXPECTED_DATABASE or role != EXPECTED_ROLE:
            raise RuntimeError("AIMIDAS_STAGING_TARGET_MISMATCH")
        cur.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")
        if {version: checksum.strip() for version, checksum in cur.fetchall()} != MIGRATIONS:
            raise RuntimeError("AIMIDAS_STAGING_MIGRATION_MANIFEST_MISMATCH")
        cur.execute(
            """
            SELECT status,rights_basis,evidence_sha256,commercial_use_allowed,
                   attribution_required,raw_redistribution_allowed,permitted_uses,
                   evidence_uri,terms_url
            FROM source_approvals WHERE approval_id=%s
            """,
            (APPROVAL_ID,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("AIMIDAS_STAGING_RIGHTS_APPROVAL_MISSING")
        status, basis, evidence_hash, commercial, attribution, redistribution, uses, uri, terms = row
        required_uses = {
            "collection", "storage", "historical_import", "internal_analysis",
            "feature_engineering", "model_training", "model_validation",
            "benchmarking", "backtesting", "derived_research", "cache",
        }
        if (
            status != "APPROVED" or basis != "WRITTEN_PERMISSION"
            or evidence_hash.strip() != APPROVAL_EVIDENCE_SHA256
            or commercial is not False or attribution is not True
            or redistribution is not False or not required_uses.issubset(set(uses))
            or uri != APPROVAL_EVIDENCE_URI or terms != APPROVAL_EVIDENCE_URI
        ):
            raise RuntimeError("AIMIDAS_STAGING_RIGHTS_APPROVAL_MISMATCH")
        cur.execute(
            """
            SELECT status,evidence_sha256 FROM source_approval_status_events
            WHERE approval_id=%s ORDER BY effective_at DESC LIMIT 1
            """,
            (APPROVAL_ID,),
        )
        event = cur.fetchone()
        if not event or event[0] != "APPROVED" or event[1].strip() != APPROVAL_EVIDENCE_SHA256:
            raise RuntimeError("AIMIDAS_STAGING_RIGHTS_STATUS_EVENT_MISSING")


def import_pack(database_url: str, input_dir: Path) -> dict:
    manifest, file_bytes, manifest_hash = validate_manifest(input_dir)
    retrieved_at = datetime.fromisoformat(manifest["generated_at"].replace("Z", "+00:00"))
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise RuntimeError("AIMIDAS_RETRIEVAL_CLOCK_NOT_AWARE")
    now = datetime.now(timezone.utc)

    import psycopg
    from psycopg.types.json import Jsonb

    response_count = observation_count = 0
    with psycopg.connect(database_url) as conn:
        preflight(conn, database_url)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO capture_manifests(manifest_key,manifest_sha256,capture_scope,requests_planned)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (manifest_key) DO NOTHING
                RETURNING capture_manifest_id
                """,
                (
                    MANIFEST_KEY, manifest_hash,
                    Jsonb({
                        "provider": PROVIDER, "source_id": SOURCE_ID,
                        "repository": REPOSITORY, "source_commit": SOURCE_COMMIT,
                        "approval_id": APPROVAL_ID,
                        "file_paths": [spec.path for spec in SOURCE_FILES],
                        "noncommercial": True, "raw_redistribution_allowed": False,
                        "point_in_time_certifiable": False,
                    }),
                    len(SOURCE_FILES),
                ),
            )
            result = cur.fetchone()
            if result:
                manifest_id = result[0]
            else:
                cur.execute(
                    "SELECT capture_manifest_id,manifest_sha256 FROM capture_manifests WHERE manifest_key=%s",
                    (MANIFEST_KEY,),
                )
                existing = cur.fetchone()
                if not existing or existing[1].strip() != manifest_hash:
                    raise RuntimeError("AIMIDAS_CAPTURE_MANIFEST_IDEMPOTENCY_CONFLICT")
                manifest_id = existing[0]
            cur.execute(
                "SELECT capture_manifest_id FROM capture_manifests WHERE capture_manifest_id=%s FOR UPDATE",
                (manifest_id,),
            )

            for spec in SOURCE_FILES:
                raw = file_bytes[spec.path]
                record = next(item for item in manifest["files"] if item["path"] == spec.path)
                digest = sha256(raw)
                request_id = f"{SOURCE_COMMIT}:{spec.path}"
                endpoint = "github_raw/" + spec.path
                request_params = {
                    "repository": REPOSITORY, "commit": SOURCE_COMMIT,
                    "path": spec.path, "git_blob_sha1": spec.git_blob_sha,
                    "response_sha256": digest, "bytes": len(raw),
                }
                headers = {
                    "content-type": "text/csv; charset=utf-8",
                    "x-veltrix-source-commit": SOURCE_COMMIT,
                    "x-veltrix-git-blob-sha1": spec.git_blob_sha,
                }
                cur.execute(
                    """
                    INSERT INTO provider_responses(
                        provider,source_id,endpoint,request_id,request_params,http_status,
                        response_sha256,raw_body,response_headers,fetched_at
                    ) VALUES (%s,%s,%s,%s,%s,200,%s,%s,%s,%s)
                    ON CONFLICT (provider,source_id,request_id,response_sha256) DO NOTHING
                    """,
                    (
                        PROVIDER, SOURCE_ID, endpoint, request_id, Jsonb(request_params),
                        digest, raw, Jsonb(headers), retrieved_at,
                    ),
                )
                cur.execute(
                    """
                    SELECT id,response_sha256,octet_length(raw_body)
                    FROM provider_responses
                    WHERE provider=%s AND source_id=%s AND request_id=%s AND response_sha256=%s
                    """,
                    (PROVIDER, SOURCE_ID, request_id, digest),
                )
                response = cur.fetchone()
                if not response or response[1].strip() != digest or response[2] != len(raw):
                    raise RuntimeError("AIMIDAS_RAW_RESPONSE_READBACK_FAILED:" + spec.path)
                response_id = response[0]
                payload = {
                    "dataset_path": spec.path, "dataset_kind": record["kind"],
                    "source_repository": REPOSITORY, "source_commit": SOURCE_COMMIT,
                    "git_blob_sha1": spec.git_blob_sha, "response_sha256": digest,
                    "bytes": len(raw), "row_count": record["row_count"],
                    "column_count": record["column_count"],
                    "date_field": record["date_field"],
                    "date_min": record["date_min"], "date_max": record["date_max"],
                    "valid_average_1x2_rows": record["valid_average_1x2_rows"],
                    "distinct_match_labels": record["distinct_match_labels"],
                    "distinct_teams": record["distinct_teams"],
                    "has_prematch_named_fields": record["has_prematch_named_fields"],
                    "point_in_time_certifiable": False,
                    "rights_approval_id": APPROVAL_ID,
                    "attribution": "AI Midas Football Data",
                    "upstream_lineage": (
                        "griffisben/Post_Match_App/Stat_Files"
                        if record["kind"] == "advanced_team_match_csv" else None
                    ),
                }
                payload_hash = sha256(canonical_json(payload))
                cur.execute(
                    """
                    INSERT INTO source_observations(
                        provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                        retrieved_at,payload,source_id,data_type,available_at,availability_basis,
                        rights_approval_id,schema_version,provider_response_id,
                        point_in_time_certifiable,source_event_time,source_published_at,
                        source_effective_at,recorded_at,source_timestamp_raw,source_timestamp_basis
                    ) VALUES (
                        %s,%s,'dataset_asset',%s,%s,%s,%s,%s,%s,%s,
                        'archive_first_observed_at_import_v1',%s,'aimidas-csv-pack-v1',%s,
                        FALSE,NULL,NULL,NULL,%s,NULL,'unknown'
                    ) ON CONFLICT (provider,endpoint,entity_type,provider_entity_id,payload_sha256)
                    DO NOTHING
                    """,
                    (
                        PROVIDER, endpoint, spec.path, payload_hash, retrieved_at,
                        Jsonb(payload), SOURCE_ID, record["kind"], retrieved_at,
                        APPROVAL_ID, response_id, now,
                    ),
                )
                cur.execute(
                    """
                    SELECT id,payload_sha256,provider_response_id,rights_approval_id,
                           point_in_time_certifiable,source_published_at,source_effective_at,
                           source_timestamp_basis
                    FROM source_observations
                    WHERE provider=%s AND endpoint=%s AND entity_type='dataset_asset'
                      AND provider_entity_id=%s AND payload_sha256=%s
                    """,
                    (PROVIDER, endpoint, spec.path, payload_hash),
                )
                observation = cur.fetchone()
                if (
                    not observation or observation[1].strip() != payload_hash
                    or observation[2] != response_id or observation[3] != APPROVAL_ID
                    or observation[4] is not False or observation[5] is not None
                    or observation[6] is not None or observation[7] != "unknown"
                ):
                    raise RuntimeError("AIMIDAS_OBSERVATION_READBACK_FAILED:" + spec.path)
                response_count += 1
                observation_count += 1

            cur.execute(
                """
                INSERT INTO capture_manifest_events(
                    capture_manifest_id,status,event_at,reason_code,evidence_sha256,coverage_summary
                )
                SELECT %s,'COMPLETED',%s,'AIMIDAS_STAGING_IMPORT_VERIFIED',%s,%s
                WHERE NOT EXISTS (
                    SELECT 1 FROM capture_manifest_events
                    WHERE capture_manifest_id=%s AND status='COMPLETED'
                      AND evidence_sha256=%s
                )
                """,
                (
                    manifest_id, now, manifest_hash,
                    Jsonb({
                        "files": len(SOURCE_FILES), "responses": response_count,
                        "observations": observation_count, "raw_bytes": manifest["total_bytes"],
                        "point_in_time_certifiable": False,
                    }),
                    manifest_id, manifest_hash,
                ),
            )

    # Independent post-commit read using a fresh connection.
    audit = audit_import(database_url, manifest_hash)
    if audit["status"] != "PASS":
        raise RuntimeError("AIMIDAS_POST_COMMIT_AUDIT_FAILED")
    return {
        "status": "PASS", "manifest_sha256": manifest_hash,
        "files": len(SOURCE_FILES), "provider_responses": response_count,
        "source_observations": observation_count,
        "raw_bytes": manifest["total_bytes"],
        "point_in_time_certifiable": False,
        "model_admitted": False, "production_written": False,
        "predictions_changed": False, "post_commit_audit": audit,
    }


def audit_import(database_url: str, manifest_hash: str) -> dict:
    import psycopg
    failures: list[str] = []
    with psycopg.connect(database_url) as conn:
        preflight(conn, database_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT capture_manifest_id,manifest_sha256,requests_planned FROM capture_manifests WHERE manifest_key=%s",
                (MANIFEST_KEY,),
            )
            manifest_row = cur.fetchone()
            if not manifest_row or manifest_row[1].strip() != manifest_hash or manifest_row[2] != len(SOURCE_FILES):
                failures.append("CAPTURE_MANIFEST_MISMATCH")
                manifest_id = manifest_row[0] if manifest_row else None
            else:
                manifest_id = manifest_row[0]
            verified = []
            for spec in SOURCE_FILES:
                endpoint = "github_raw/" + spec.path
                request_id = f"{SOURCE_COMMIT}:{spec.path}"
                cur.execute(
                    """
                    SELECT r.id,r.response_sha256,r.raw_body,o.id,o.payload_sha256,
                           o.provider_response_id,o.rights_approval_id,o.point_in_time_certifiable,
                           o.source_published_at,o.source_effective_at,o.source_timestamp_basis,
                           o.recorded_at,o.available_at
                    FROM provider_responses r
                    JOIN source_observations o
                      ON o.provider_response_id=r.id
                    WHERE r.provider=%s AND r.source_id=%s AND r.request_id=%s
                      AND o.provider=%s AND o.source_id=%s AND o.endpoint=%s
                      AND o.entity_type='dataset_asset' AND o.provider_entity_id=%s
                    """,
                    (PROVIDER,SOURCE_ID,request_id,PROVIDER,SOURCE_ID,endpoint,spec.path),
                )
                rows = cur.fetchall()
                if len(rows) != 1:
                    failures.append("FILE_OBSERVATION_CARDINALITY:" + spec.path)
                    continue
                row = rows[0]
                response_id, response_hash, raw, observation_id, payload_hash, linked_response, approval, pit, published, effective, basis, recorded, available = row
                actual_hash = sha256(bytes(raw))
                if response_hash.strip() != actual_hash or linked_response != response_id:
                    failures.append("RAW_RESPONSE_HASH_MISMATCH:" + spec.path)
                if approval != APPROVAL_ID or pit is not False or published is not None or effective is not None or basis != "unknown":
                    failures.append("TEMPORAL_OR_RIGHTS_CLASSIFICATION_MISMATCH:" + spec.path)
                if recorded is None or available is None or available.tzinfo is None:
                    failures.append("OBSERVATION_CLOCK_MISSING:" + spec.path)
                verified.append(spec.path)
            if manifest_id is not None:
                cur.execute(
                    """
                    SELECT count(*) FROM capture_manifest_events
                    WHERE capture_manifest_id=%s AND status='COMPLETED' AND evidence_sha256=%s
                    """,
                    (manifest_id, manifest_hash),
                )
                if cur.fetchone()[0] != 1:
                    failures.append("COMPLETION_EVENT_MISSING_OR_DUPLICATED")
    return {
        "status": "FAIL" if failures else "PASS",
        "files_verified": len(verified), "expected_files": len(SOURCE_FILES),
        "failures": failures, "point_in_time_certifiable": False,
        "model_admitted": False, "production_written": False,
        "predictions_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL_REQUIRED")
    if args.audit_only:
        pack_manifest = json.loads((Path(args.input_dir) / "manifest.json").read_text(encoding="utf-8"))
        digest = sha256(canonical_json(pack_manifest))
        result = audit_import(database_url, digest)
    else:
        result = import_pack(database_url, Path(args.input_dir))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "post_commit_audit"}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
