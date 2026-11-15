"""Independent read-only audit of the persisted OpenPlay release in Neon staging."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.veltrix_v2.import_openplay_staging import (
    APPROVAL_ID, EXPECTED_DATABASE, EXPECTED_HOST, PARQUET_ROWS, CSV_FILES,
    PROVIDER, SOURCE_ID, TIMESTAMP_DICTIONARY_SHA256, TIMESTAMP_EVIDENCE_ID,
    build_manifest, canonical_json, preflight, sha256,
)


def audit(database_url: str, input_dir: str | Path) -> dict:
    if not database_url or (urlparse(database_url).hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("OPENPLAY_AUDIT_STAGING_HOST_MISMATCH")
    root = Path(input_dir)
    report = json.loads((root / "openplay_qualification_report.json").read_text(encoding="utf-8"))
    expected_manifest_hash = sha256(canonical_json(build_manifest(report)))

    import psycopg

    with psycopg.connect(database_url) as conn:
        preflight(conn, database_url)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT pr.id,pr.endpoint,pr.response_sha256,pr.raw_body,pr.fetched_at,
                       so.payload,so.payload_sha256,so.retrieved_at,so.available_at,
                       so.point_in_time_certifiable,so.source_published_at,
                       so.source_timestamp_basis,so.availability_basis,
                       so.rights_approval_id,so.provider_response_id
                FROM provider_responses pr
                JOIN source_observations so ON so.provider_response_id=pr.id
                WHERE pr.provider=%s AND pr.source_id=%s
                  AND so.provider=%s AND so.source_id=%s
                  AND so.entity_type='dataset_asset'
                ORDER BY pr.endpoint
            """, (PROVIDER,SOURCE_ID,PROVIDER,SOURCE_ID))
            rows = cur.fetchall()
            expected_names = set(PARQUET_ROWS) | set(CSV_FILES)
            observed_names = set()
            raw_bytes = 0
            for row in rows:
                response_id,endpoint,response_hash,raw,fetched_at,payload,payload_hash,retrieved_at,available_at,pit,published,timestamp_basis,availability_basis,rights_id,linked_response_id = row
                name = endpoint.rsplit("/",1)[-1]
                if name in observed_names:
                    raise RuntimeError("OPENPLAY_DUPLICATE_ASSET_OBSERVATION:" + name)
                observed_names.add(name)
                actual_hash = sha256(bytes(raw))
                if actual_hash != response_hash.strip() or payload.get("asset_sha256") != actual_hash:
                    raise RuntimeError("OPENPLAY_RAW_ASSET_HASH_MISMATCH:" + name)
                if sha256(canonical_json(payload)) != payload_hash.strip():
                    raise RuntimeError("OPENPLAY_ASSET_METADATA_HASH_MISMATCH:" + name)
                if (linked_response_id != response_id or rights_id != APPROVAL_ID
                    or pit is not False or published is not None
                    or timestamp_basis != "unknown"
                    or availability_basis != "archive_first_observed_at_import_v1"
                    or retrieved_at != available_at):
                    raise RuntimeError("OPENPLAY_TEMPORAL_OR_RIGHTS_METADATA_MISMATCH:" + name)
                if payload.get("commercial_use_allowed") is not False:
                    raise RuntimeError("OPENPLAY_COMMERCIAL_FLAG_MISMATCH:" + name)
                raw_bytes += len(raw)
            if observed_names != expected_names or len(rows) != 15:
                raise RuntimeError("OPENPLAY_STAGING_ASSET_SET_MISMATCH")

            cur.execute("""
                SELECT count(*),count(DISTINCT provider_entity_id),
                       count(*) FILTER (WHERE point_in_time_certifiable IS TRUE),
                       count(*) FILTER (WHERE source_timestamp_basis='documented_guarantee'),
                       count(*) FILTER (WHERE source_published_at IS NOT NULL
                                          AND available_at=source_published_at
                                          AND recorded_at>=source_published_at
                                          AND rights_approval_id=%s
                                          AND provider_response_id IS NOT NULL),
                       min(source_published_at),max(source_published_at)
                FROM source_observations
                WHERE provider=%s AND source_id=%s
                  AND entity_type='match_result_snapshot'
                  AND endpoint='release-assets/data-v0.1.0/matches.parquet'
            """, (APPROVAL_ID,PROVIDER,SOURCE_ID))
            snapshot_rows,unique_snapshots,pit_snapshots,documented_snapshots,valid_chronology,first_saved,last_saved = cur.fetchone()
            expected_matches = PARQUET_ROWS["matches.parquet"]
            if not (
                snapshot_rows == unique_snapshots == pit_snapshots
                == documented_snapshots == valid_chronology == expected_matches
                and first_saved is not None and last_saved is not None
            ):
                raise RuntimeError("OPENPLAY_MATCH_SNAPSHOT_READBACK_MISMATCH")

            cur.execute("""
                SELECT payload FROM source_observations
                WHERE provider=%s AND source_id=%s AND entity_type='match_result_snapshot'
                LIMIT 1
            """, (PROVIDER,SOURCE_ID))
            sample_payload = cur.fetchone()
            if (
                not sample_payload
                or sample_payload[0].get("timestamp_guarantee_evidence_id") != TIMESTAMP_EVIDENCE_ID
                or sample_payload[0].get("timestamp_guarantee_evidence_sha256") != TIMESTAMP_DICTIONARY_SHA256
                or sample_payload[0].get("temporal_use_scope") != "only for cutoffs at or after actual VELTRIX recorded_at"
            ):
                raise RuntimeError("OPENPLAY_MATCH_SNAPSHOT_TIMESTAMP_EVIDENCE_MISMATCH")

            cur.execute("""
                SELECT manifest_sha256,capture_manifest_id
                FROM capture_manifests
                WHERE manifest_key=%s
            """, ("openplay-data-v0.1.0-ac0bd9aff52016066433ebebf818bec4278fcf54-page-saved-v1",))
            manifest_row = cur.fetchone()
            if not manifest_row or manifest_row[0].strip() != expected_manifest_hash:
                raise RuntimeError("OPENPLAY_STAGING_MANIFEST_MISMATCH")
            cur.execute("""
                SELECT count(*),count(*) FILTER (WHERE status='COMPLETED'),
                       max(coverage_summary->>'parquet_rows')
                FROM capture_manifest_events
                WHERE capture_manifest_id=%s AND evidence_sha256=%s
            """, (manifest_row[1],expected_manifest_hash))
            event_count,completed_count,parquet_rows = cur.fetchone()
            if event_count != 1 or completed_count != 1 or int(parquet_rows or 0) != sum(PARQUET_ROWS.values()):
                raise RuntimeError("OPENPLAY_STAGING_MANIFEST_EVENT_MISMATCH")

    return {
        "status":"PASS_INDEPENDENT_STAGING_READBACK",
        "database":EXPECTED_DATABASE,
        "assets":len(rows),
        "match_page_snapshot_observations":PARQUET_ROWS["matches.parquet"],
        "timestamp_guarantee_evidence_sha256":TIMESTAMP_DICTIONARY_SHA256,
        "raw_bytes":raw_bytes,
        "parquet_tables":len(PARQUET_ROWS),
        "parquet_rows":sum(PARQUET_ROWS.values()),
        "manifest_sha256":expected_manifest_hash,
        "point_in_time_certifiable":False,
        "commercial_use_allowed":False,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--input-dir",required=True)
    args=parser.parse_args()
    result=audit(os.getenv("DATABASE_URL",""),args.input_dir)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
