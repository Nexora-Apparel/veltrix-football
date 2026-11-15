"""Guarded, idempotent OpenPlay release capture into isolated Neon staging.

Stores exact release asset bytes as immutable provider_responses and one linked
source_observation per asset. It deliberately does not claim historical PIT
availability: source publication remains NULL and point_in_time_certifiable=false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"
SOURCE_ID = "openplay-data-v0.1.0"
PROVIDER = "OpenPlay / WhoScored / Opta"
TAG = "data-v0.1.0"
TAG_COMMIT = "ac0bd9aff52016066433ebebf818bec4278fcf54"
AUTHORIZATION_SHA256 = "5e6bd00416f180109751e422521d76910da8b491c62507c4d9836e6700c38c46"
TIMESTAMP_DICTIONARY_SHA256 = "24a1037a948afa1759e3bc2babeb8b17b9e1e2dc3c8a8beea2e18f9b5b671279"
TIMESTAMP_EVIDENCE_ID = "openplay-data-v0.1.0:DATA_DICTIONARY.md#matches.scraped_at"
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
PARQUET_ROWS = {
    "competitions.parquet": 22,
    "teams.parquet": 422,
    "players.parquet": 20782,
    "matches.parquet": 26547,
    "lineups.parquet": 1068162,
    "formations.parquet": 245468,
    "cards.parquet": 115499,
    "shots.parquet": 669404,
    "player_match_stats.parquet": 775994,
    "team_match_stats.parquet": 53094,
}
CSV_FILES = (
    "coverage.csv", "known_gaps.csv", "data_issues.csv",
    "qualifier_dictionary.csv", "checksums.json",
)
ATTRIBUTION = "openplay (Noah Bair)"
ATTRIBUTION_URL = "https://github.com/nlbair/openplay"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def parse_scraped_at_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("OPENPLAY_SCRAPED_AT_MISSING")
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise RuntimeError("OPENPLAY_SCRAPED_AT_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        # The pinned OpenPlay data dictionary explicitly defines this field as UTC.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_manifest(report: dict) -> dict:
    assets = report.get("assets")
    if not isinstance(assets, dict) or set(assets) != set(PARQUET_ROWS) | set(CSV_FILES):
        raise RuntimeError("OPENPLAY_ASSET_SET_MISMATCH")
    for name, expected in PARQUET_ROWS.items():
        if report["parquet_tables"][name]["rows"] != expected:
            raise RuntimeError("OPENPLAY_PARQUET_ROW_COUNT_MISMATCH:" + name)
    if report.get("status") != "PASS_NONCOMMERCIAL_SOURCE_QUALIFIED":
        raise RuntimeError("OPENPLAY_QUALIFICATION_NOT_PASSED")
    auth = report.get("authorization_evidence") or {}
    if (auth.get("status") != "USER_CONFIRMED_NONCOMMERCIAL_AUTHORIZATION"
            or auth.get("sha256") != AUTHORIZATION_SHA256
            or auth.get("commercial_use_allowed") is not False
            or auth.get("raw_redistribution_allowed") is not False):
        raise RuntimeError("OPENPLAY_AUTHORIZATION_EVIDENCE_MISMATCH")
    scrape = report.get("scrape_timestamp_audit") or {}
    expected_matches = PARQUET_ROWS["matches.parquet"]
    if (scrape.get("temporal_status") != "CAPTURE_TIMESTAMP_CANDIDATE"
        or scrape.get("data_dictionary_documented_definition_verified") is not True
        or scrape.get("timestamp_guarantee_evidence_id") != TIMESTAMP_EVIDENCE_ID
        or scrape.get("timestamp_guarantee_evidence_sha256") != TIMESTAMP_DICTIONARY_SHA256
        or any(scrape.get(key) != expected_matches for key in (
            "match_rows","non_null_scraped_at","parseable_scraped_at","unique_match_ids",
            "safely_after_match_date","not_future_scrape_timestamps"
        ))):
        raise RuntimeError("OPENPLAY_SCRAPE_TIMESTAMP_EVIDENCE_MISMATCH")
    return {
        "provider": PROVIDER, "source_id": SOURCE_ID, "release_tag": TAG,
        "tag_commit": TAG_COMMIT, "license": "CC BY 4.0",
        "attribution": ATTRIBUTION, "attribution_url": ATTRIBUTION_URL,
        "authorization_approval_id": APPROVAL_ID,
        "commercial_use_allowed": False, "monetisation_prohibited": True,
        "scrape_timestamp_evidence": {
            "timestamp_guarantee_evidence_id": TIMESTAMP_EVIDENCE_ID,
            "timestamp_guarantee_evidence_sha256": TIMESTAMP_DICTIONARY_SHA256,
            "data_dictionary_url": scrape.get("data_dictionary_url"),
            "data_dictionary_semantics": "When the page was saved (UTC)",
            "match_rows": expected_matches,
            "first_page_saved_at_utc": scrape.get("first_page_saved_at_utc"),
            "last_page_saved_at_utc": scrape.get("last_page_saved_at_utc"),
            "scope": "prospective cutoffs only after VELTRIX recorded_at; no pre-import historical backdating",
        },
        "assets": assets,
    }


def preflight(conn, database_url: str) -> None:
    if os.getenv("VELTRIX_ENABLE_OPENPLAY_STAGING_IMPORT") != "YES":
        raise RuntimeError("OPENPLAY_STAGING_IMPORT_EXPLICIT_ENABLE_REQUIRED")
    parsed = urlparse(database_url)
    if (parsed.hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("OPENPLAY_STAGING_HOST_ALLOWLIST_MISMATCH")
    if parse_qs(parsed.query).get("sslmode", [""])[0].casefold() not in {"require", "verify-ca", "verify-full"}:
        raise RuntimeError("OPENPLAY_STAGING_TLS_REQUIRED")
    with conn.cursor() as cur:
        cur.execute("SELECT current_database(),current_user")
        database, role = cur.fetchone()
        if database != EXPECTED_DATABASE or role != "neondb_owner":
            raise RuntimeError("OPENPLAY_STAGING_TARGET_MISMATCH")
        cur.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")
        if dict(cur.fetchall()) != MIGRATIONS:
            raise RuntimeError("OPENPLAY_STAGING_MIGRATION_MANIFEST_MISMATCH")
        cur.execute("""
            SELECT status,rights_basis,evidence_sha256,commercial_use_allowed,
                   attribution_required,raw_redistribution_allowed
            FROM source_approvals WHERE approval_id=%s
        """, (APPROVAL_ID,))
        row = cur.fetchone()
        if row != ("APPROVED", "WRITTEN_PERMISSION", AUTHORIZATION_SHA256, False, True, False):
            raise RuntimeError("OPENPLAY_STAGING_RIGHTS_APPROVAL_MISMATCH")


def import_bundle(database_url: str, input_dir: str | Path) -> dict:
    root = Path(input_dir)
    report_path = root / "openplay_qualification_report.json"
    if not report_path.is_file():
        raise RuntimeError("OPENPLAY_QUALIFICATION_REPORT_MISSING")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = build_manifest(report)
    manifest_bytes = canonical_json(manifest)
    manifest_hash = sha256(manifest_bytes)
    now = datetime.now(timezone.utc)

    expected_names = sorted(set(PARQUET_ROWS) | set(CSV_FILES))
    asset_bytes: dict[str, bytes] = {}
    for name in expected_names:
        path = root / name
        if not path.is_file():
            raise RuntimeError("OPENPLAY_ASSET_FILE_MISSING:" + name)
        raw = path.read_bytes()
        evidence = report["assets"][name]
        if len(raw) != evidence["bytes"] or sha256(raw) != evidence["sha256"]:
            raise RuntimeError("OPENPLAY_ASSET_HASH_MISMATCH:" + name)
        asset_bytes[name] = raw

    import psycopg
    from psycopg.types.json import Jsonb

    inserted_responses = inserted_observations = 0
    match_snapshot_count = 0
    with psycopg.connect(database_url) as conn:
        preflight(conn, database_url)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO capture_manifests(manifest_key,manifest_sha256,capture_scope,requests_planned)
                VALUES (%s,%s,%s,16)
                ON CONFLICT (manifest_key) DO NOTHING
                RETURNING capture_manifest_id
            """, ("openplay-" + TAG + "-" + TAG_COMMIT + "-page-saved-v1", manifest_hash, Jsonb(manifest)))
            result = cur.fetchone()
            if result:
                manifest_id = result[0]
            else:
                cur.execute("SELECT capture_manifest_id,manifest_sha256 FROM capture_manifests WHERE manifest_key=%s",
                            ("openplay-" + TAG + "-" + TAG_COMMIT + "-page-saved-v1",))
                existing = cur.fetchone()
                if not existing or existing[1].strip() != manifest_hash:
                    raise RuntimeError("OPENPLAY_CAPTURE_MANIFEST_IDEMPOTENCY_CONFLICT")
                manifest_id = existing[0]
            cur.execute("SELECT capture_manifest_id FROM capture_manifests WHERE capture_manifest_id=%s FOR UPDATE", (manifest_id,))

            for name in expected_names:
                raw = asset_bytes[name]
                digest = sha256(raw)
                endpoint = f"release-assets/{TAG}/{name}"
                request_id = f"{TAG_COMMIT}:{name}"
                headers = {"x-github-release-asset-digest": "sha256:" + digest,
                           "content-type": "application/octet-stream"}
                cur.execute("""
                    INSERT INTO provider_responses(
                        provider,source_id,endpoint,request_id,request_params,http_status,
                        response_sha256,raw_body,response_headers,fetched_at
                    ) VALUES (%s,%s,%s,%s,%s,200,%s,%s,%s,%s)
                    ON CONFLICT (provider,source_id,request_id,response_sha256) DO NOTHING
                """, (PROVIDER,SOURCE_ID,endpoint,request_id,
                      Jsonb({"release_tag":TAG,"tag_commit":TAG_COMMIT,"asset_name":name}),
                      digest,raw,Jsonb(headers),now))
                cur.execute("""
                    SELECT id,response_sha256,octet_length(raw_body)
                    FROM provider_responses
                    WHERE provider=%s AND source_id=%s AND request_id=%s AND response_sha256=%s
                """, (PROVIDER,SOURCE_ID,request_id,digest))
                response = cur.fetchone()
                if not response or response[1].strip() != digest or response[2] != len(raw):
                    raise RuntimeError("OPENPLAY_RAW_RESPONSE_READBACK_FAILED:" + name)
                response_id = response[0]

                row_count = PARQUET_ROWS.get(name)
                payload = {
                    "asset_name":name,"asset_sha256":digest,"asset_bytes":len(raw),
                    "release_tag":TAG,"tag_commit":TAG_COMMIT,"row_count":row_count,
                    "license":"CC BY 4.0","attribution":ATTRIBUTION,
                    "attribution_url":ATTRIBUTION_URL,
                    "authorization_approval_id":APPROVAL_ID,
                    "commercial_use_allowed":False,"monetisation_prohibited":True,
                }
                payload_hash = sha256(canonical_json(payload))
                cur.execute("""
                    INSERT INTO source_observations(
                        provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                        retrieved_at,payload,source_id,data_type,available_at,availability_basis,
                        rights_approval_id,schema_version,provider_response_id,
                        point_in_time_certifiable,source_published_at,source_effective_at,
                        recorded_at,source_timestamp_basis
                    ) VALUES (
                        %s,%s,'dataset_asset',%s,%s,%s,%s,%s,'historical_event_dataset_asset',
                        %s,'archive_first_observed_at_import_v1',%s,'openplay-release-v2',%s,
                        FALSE,NULL,NULL,%s,'unknown'
                    ) ON CONFLICT (provider,endpoint,entity_type,provider_entity_id,payload_sha256)
                    DO NOTHING
                """, (PROVIDER,endpoint,name,payload_hash,now,Jsonb(payload),SOURCE_ID,
                      now,APPROVAL_ID,response_id,now))
                cur.execute("""
                    SELECT id,payload_sha256,provider_response_id,rights_approval_id,
                           point_in_time_certifiable,source_published_at
                    FROM source_observations
                    WHERE provider=%s AND endpoint=%s AND entity_type='dataset_asset'
                      AND provider_entity_id=%s AND payload_sha256=%s
                """, (PROVIDER,endpoint,name,payload_hash))
                observation = cur.fetchone()
                if (not observation or observation[1].strip()!=payload_hash
                    or observation[2]!=response_id or observation[3]!=APPROVAL_ID
                    or observation[4] is not False or observation[5] is not None):
                    raise RuntimeError("OPENPLAY_OBSERVATION_READBACK_FAILED:" + name)
                inserted_responses += 1
                inserted_observations += 1

            # Match-page snapshots carry a documented UTC page-save time. These
            # records are eligible only for cutoffs after both page save and the
            # actual VELTRIX import/recording time; no historical backdating occurs.
            import duckdb
            matches_path = str(root / "matches.parquet").replace("'", "''")
            db = duckdb.connect(database=":memory:")
            match_rows = db.execute(f"""
                SELECT match_id,comp,season,competition,date,home_team_id,home_team,
                       away_team_id,away_team,home_score_90,away_score_90,xg_model,scraped_at
                FROM read_parquet('{matches_path}')
                ORDER BY match_id
            """).fetchall()
            db.close()
            if len(match_rows) != PARQUET_ROWS["matches.parquet"]:
                raise RuntimeError("OPENPLAY_MATCH_SNAPSHOT_ROW_COUNT_MISMATCH")

            matches_digest = sha256(asset_bytes["matches.parquet"])
            matches_request_id = f"{TAG_COMMIT}:matches.parquet"
            cur.execute("""
                SELECT id FROM provider_responses
                WHERE provider=%s AND source_id=%s AND request_id=%s AND response_sha256=%s
            """, (PROVIDER,SOURCE_ID,matches_request_id,matches_digest))
            matches_response = cur.fetchone()
            if not matches_response:
                raise RuntimeError("OPENPLAY_MATCHES_RESPONSE_LINK_MISSING")
            matches_response_id = matches_response[0]

            seen_match_ids: set[str] = set()
            snapshot_batch = []
            for row in match_rows:
                (match_id,comp,season,competition,match_date,home_team_id,home_team,
                 away_team_id,away_team,home_score,away_score,xg_model,scraped_at_raw) = row
                match_key = str(match_id)
                if match_key in seen_match_ids:
                    raise RuntimeError("OPENPLAY_DUPLICATE_MATCH_PAGE_ID:" + match_key)
                seen_match_ids.add(match_key)
                saved_at = parse_scraped_at_utc(str(scraped_at_raw))
                if not isinstance(match_date, date):
                    raise RuntimeError("OPENPLAY_MATCH_DATE_INVALID:" + match_key)
                safe_after_date = datetime.combine(match_date + timedelta(days=2), time.min, tzinfo=timezone.utc)
                if saved_at < safe_after_date or saved_at > now:
                    raise RuntimeError("OPENPLAY_PAGE_SAVE_CHRONOLOGY_INVALID:" + match_key)
                if any(value is None for value in (home_score, away_score, comp, season, home_team_id, away_team_id)):
                    raise RuntimeError("OPENPLAY_MATCH_SNAPSHOT_REQUIRED_FIELD_MISSING:" + match_key)
                payload = {
                    "match_id":match_key,"competition_code":str(comp),"season":str(season),
                    "competition":str(competition),"match_date":match_date.isoformat(),
                    "home_team_id":str(home_team_id),"home_team":str(home_team),
                    "away_team_id":str(away_team_id),"away_team":str(away_team),
                    "home_score_90":int(home_score),"away_score_90":int(away_score),
                    "xg_model":str(xg_model),"scraped_at_raw":str(scraped_at_raw),
                    "scraped_at_utc":saved_at.isoformat(),
                    "timestamp_guarantee_evidence_id":TIMESTAMP_EVIDENCE_ID,
                    "timestamp_guarantee_evidence_sha256":TIMESTAMP_DICTIONARY_SHA256,
                    "source_timestamp_semantics":"page_saved_at_utc",
                    "rights_approval_id":APPROVAL_ID,
                    "capture_manifest_sha256":manifest_hash,
                    "matches_parquet_sha256":matches_digest,
                    "temporal_use_scope":"only for cutoffs at or after actual VELTRIX recorded_at",
                    "commercial_use_allowed":False,
                }
                payload_hash = sha256(canonical_json(payload))
                snapshot_batch.append((
                    PROVIDER,"release-assets/" + TAG + "/matches.parquet",
                    "match_result_snapshot",match_key,payload_hash,now,Jsonb(payload),
                    SOURCE_ID,"match_result_snapshot",str(season),None,saved_at,
                    "openplay_page_saved_at_utc_v1",APPROVAL_ID,
                    "openplay-match-snapshot-v1",matches_response_id,True,saved_at,
                    None,now,str(scraped_at_raw),"documented_guarantee",
                ))
                if len(snapshot_batch) >= 1000:
                    cur.executemany("""
                        INSERT INTO source_observations(
                            provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                            retrieved_at,payload,source_id,data_type,season_key,source_event_time,
                            available_at,availability_basis,rights_approval_id,schema_version,
                            provider_response_id,point_in_time_certifiable,source_published_at,
                            source_effective_at,recorded_at,source_timestamp_raw,source_timestamp_basis
                        ) VALUES (
                            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                        ) ON CONFLICT (provider,endpoint,entity_type,provider_entity_id,payload_sha256)
                        DO NOTHING
                    """,snapshot_batch)
                    snapshot_batch.clear()
            if snapshot_batch:
                cur.executemany("""
                    INSERT INTO source_observations(
                        provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                        retrieved_at,payload,source_id,data_type,season_key,source_event_time,
                        available_at,availability_basis,rights_approval_id,schema_version,
                        provider_response_id,point_in_time_certifiable,source_published_at,
                        source_effective_at,recorded_at,source_timestamp_raw,source_timestamp_basis
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    ) ON CONFLICT (provider,endpoint,entity_type,provider_entity_id,payload_sha256)
                    DO NOTHING
                """,snapshot_batch)

            cur.execute("""
                SELECT count(*),count(DISTINCT provider_entity_id),
                       count(*) FILTER (WHERE point_in_time_certifiable IS TRUE),
                       count(*) FILTER (WHERE source_timestamp_basis='documented_guarantee'),
                       min(source_published_at),max(source_published_at)
                FROM source_observations
                WHERE provider=%s AND source_id=%s AND entity_type='match_result_snapshot'
                  AND endpoint='release-assets/data-v0.1.0/matches.parquet'
            """, (PROVIDER,SOURCE_ID))
            match_snapshot_count,unique_snapshots,pit_snapshots,documented_snapshots,first_saved,last_saved = cur.fetchone()
            if (match_snapshot_count != PARQUET_ROWS["matches.parquet"]
                or unique_snapshots != match_snapshot_count
                or pit_snapshots != match_snapshot_count
                or documented_snapshots != match_snapshot_count
                or first_saved is None or last_saved is None):
                raise RuntimeError("OPENPLAY_MATCH_SNAPSHOT_READBACK_FAILED")

            cur.execute("""
                INSERT INTO capture_manifest_events(
                    capture_manifest_id,status,event_at,reason_code,evidence_sha256,coverage_summary
                ) SELECT %s,'COMPLETED',%s,'OPENPLAY_RELEASE_ASSETS_CAPTURED',%s,%s
                WHERE NOT EXISTS (
                    SELECT 1 FROM capture_manifest_events
                    WHERE capture_manifest_id=%s AND status='COMPLETED' AND evidence_sha256=%s
                )
            """, (manifest_id,now,manifest_hash,Jsonb({
                "asset_count":len(expected_names),
                "match_page_snapshot_observations":match_snapshot_count,
                "timestamp_guarantee_evidence_id":TIMESTAMP_EVIDENCE_ID,
                "timestamp_guarantee_evidence_sha256":TIMESTAMP_DICTIONARY_SHA256,
                "first_page_saved_at_utc":first_saved.isoformat(),
                "last_page_saved_at_utc":last_saved.isoformat(),
                "parquet_tables":len(PARQUET_ROWS),
                "parquet_rows":sum(PARQUET_ROWS.values()),
                "csv_files":len(CSV_FILES),
                "all_raw_asset_hashes_verified":True,
                "point_in_time_certifiable":False,
                "commercial_use_allowed":False,
            }),manifest_id,manifest_hash))
        conn.commit()

    return {
        "status":"IMPORTED_AND_READBACK_VERIFIED",
        "manifest_sha256":manifest_hash,
        "capture_manifest_id":manifest_id,
        "assets":len(expected_names),
        "match_page_snapshot_observations":match_snapshot_count,
        "match_snapshots_point_in_time_certifiable":pit_snapshots,
        "timestamp_guarantee_evidence_sha256":TIMESTAMP_DICTIONARY_SHA256,
        "raw_responses_readback_verified":inserted_responses,
        "source_observations_readback_verified":inserted_observations,
        "parquet_rows":sum(PARQUET_ROWS.values()),
        "point_in_time_certifiable":False,
        "commercial_use_allowed":False,
        "database":EXPECTED_DATABASE,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--input-dir",required=True)
    args=parser.parse_args()
    database_url=os.getenv("DATABASE_URL","")
    if not database_url:
        raise RuntimeError("OPENPLAY_STAGING_DATABASE_URL_REQUIRED")
    result=import_bundle(database_url,args.input_dir)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
