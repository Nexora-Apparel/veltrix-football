"""Persist only exact, unique, competition-overlap OpenPlay identity mappings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
EXPECTED_DATABASE = "veltrix_football_staging"
OPENPLAY_PROVIDER = "OpenPlay / WhoScored / Opta"
OPENPLAY_SOURCE_ID = "openplay-data-v0.1.0"
OPENPLAY_APPROVAL = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"
GLOBAL_APPROVAL = "approval-veltrix-all-source-noncommercial-2026-11-15"
FIVEDOLLAR_PROVIDER = "5DollarFootballAPI"
FIVEDOLLAR_SOURCE_ID = "5dollarfootballapi"
REVIEWER_ID = "automated-exact-crosswalk-v1"


def apply_crosswalk(database_url: str, candidate_path: str | Path) -> dict:
    if os.getenv("VELTRIX_ENABLE_OPENPLAY_CROSSWALK_WRITE") != "YES":
        raise RuntimeError("OPENPLAY_CROSSWALK_WRITE_NOT_EXPLICITLY_ENABLED")
    if (urlparse(database_url).hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("OPENPLAY_CROSSWALK_DATABASE_HOST_MISMATCH")
    candidates = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
    summary = candidates.get("summary") or {}
    if summary.get("status") != "READ_ONLY_CROSSWALK_CANDIDATES_BUILT":
        raise RuntimeError("OPENPLAY_CROSSWALK_CANDIDATES_NOT_QUALIFIED")
    teams = [row for row in candidates.get("teams", [])
             if row.get("status") == "EXACT_UNIQUE_NAME_AND_COMPETITION_OVERLAP"]
    competitions = [row for row in candidates.get("competitions", [])
                    if row.get("status") == "EXACT_REGION_NAME_ALIAS"]
    if len(teams) != 89 or len(competitions) != 5:
        raise RuntimeError("OPENPLAY_CROSSWALK_CANDIDATE_COUNTS_CHANGED")
    if len({row["openplay_team_id"] for row in teams}) != len(teams):
        raise RuntimeError("OPENPLAY_DUPLICATE_TEAM_CANDIDATES")
    if len({row["openplay_comp"] for row in competitions}) != len(competitions):
        raise RuntimeError("OPENPLAY_DUPLICATE_COMPETITION_CANDIDATES")
    if len({row["candidate_canonical_entity_key"] for row in teams}) != len(teams):
        raise RuntimeError("OPENPLAY_NON_UNIQUE_CANONICAL_TEAM_TARGETS")

    import psycopg
    from psycopg.types.json import Jsonb

    inserted_team_rows = inserted_comp_rows = 0
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_user")
            database, role = cur.fetchone()
            if database != EXPECTED_DATABASE or role != "neondb_owner":
                raise RuntimeError("OPENPLAY_CROSSWALK_DATABASE_TARGET_MISMATCH")

            cur.execute("""
                SELECT approval_id,status,commercial_use_allowed,permitted_uses
                FROM source_approvals
                WHERE approval_id IN (%s,%s)
            """, (OPENPLAY_APPROVAL,GLOBAL_APPROVAL))
            approvals = {row[0]:row for row in cur.fetchall()}
            for approval_id in (OPENPLAY_APPROVAL,GLOBAL_APPROVAL):
                row = approvals.get(approval_id)
                if not row or row[1] != "APPROVED" or row[2] is not False:
                    raise RuntimeError("OPENPLAY_CROSSWALK_NONCOMMERCIAL_RIGHTS_NOT_ACTIVE")
            if "model_training" not in approvals[OPENPLAY_APPROVAL][3]:
                raise RuntimeError("OPENPLAY_CROSSWALK_MODEL_TRAINING_NOT_PERMITTED")

            expected_map = {
                **{("TEAM",str(row["openplay_team_id"])):str(row["candidate_canonical_entity_key"]) for row in teams},
                **{("COMPETITION",str(row["openplay_comp"])):str(row["canonical_competition_key"]) for row in competitions},
            }
            cur.execute("""
                SELECT entity_type,provider_entity_id,canonical_entity_key,mapping_method,mapping_status
                FROM entity_crosswalk_versions
                WHERE provider=%s AND source_id=%s AND entity_type IN ('TEAM','COMPETITION')
            """, (OPENPLAY_PROVIDER,OPENPLAY_SOURCE_ID))
            existing_rows = cur.fetchall()
            if existing_rows:
                existing_map = {(row[0],row[1]):row[2] for row in existing_rows}
                methods_ok = all(
                    row[3] == ("EXACT_NAME_AND_COMPETITION_OVERLAP" if row[0] == "TEAM" else "EXPLICIT_REGION_NAME_ALIAS")
                    and row[4] == "RESOLVED"
                    for row in existing_rows
                )
                if len(existing_rows) == len(expected_map) and existing_map == expected_map and methods_ok:
                    return {
                        "status":"OPENPLAY_EXACT_CROSSWALKS_ALREADY_PRESENT",
                        "team_mappings":len(teams),
                        "competition_mappings":len(competitions),
                        "total_mappings":len(expected_map),
                        "ambiguous_or_unmatched_entities_written":0,
                        "commercial_use_allowed":False,
                    }
                raise RuntimeError("OPENPLAY_CROSSWALK_PARTIAL_OR_CONFLICTING_STATE")

            evidence_ids = {
                "teams.parquet":teams[0]["evidence_source_observation_id"],
                "competitions.parquet":competitions[0]["source_evidence_observation_id"],
            }
            for asset_name,evidence_id in evidence_ids.items():
                cur.execute("""
                    SELECT payload FROM source_observations
                    WHERE id=%s AND provider=%s AND source_id=%s
                      AND entity_type='dataset_asset' AND point_in_time_certifiable IS FALSE
                """, (evidence_id,OPENPLAY_PROVIDER,OPENPLAY_SOURCE_ID))
                evidence = cur.fetchone()
                if not evidence or not evidence[0].get("asset_sha256"):
                    raise RuntimeError("OPENPLAY_CROSSWALK_SOURCE_EVIDENCE_INVALID:" + asset_name)

            team_asset_hash = None
            comp_asset_hash = None
            cur.execute("SELECT payload FROM source_observations WHERE id=%s", (evidence_ids["teams.parquet"],))
            team_asset_hash = cur.fetchone()[0].get("asset_sha256")
            cur.execute("SELECT payload FROM source_observations WHERE id=%s", (evidence_ids["competitions.parquet"],))
            comp_asset_hash = cur.fetchone()[0].get("asset_sha256")

            team_rows = []
            for row in teams:
                if row.get("source_asset_sha256") != team_asset_hash:
                    raise RuntimeError("OPENPLAY_TEAM_CROSSWALK_ASSET_HASH_MISMATCH")
                canonical = str(row["candidate_canonical_entity_key"])
                target_provider_id = str(row["candidate_5dollar_team_id"])
                cur.execute("""
                    SELECT count(*) FROM entity_crosswalk_versions
                    WHERE entity_type='TEAM' AND provider=%s AND source_id=%s
                      AND provider_entity_id=%s AND canonical_entity_key=%s
                      AND mapping_status='RESOLVED'
                """, (FIVEDOLLAR_PROVIDER,FIVEDOLLAR_SOURCE_ID,target_provider_id,canonical))
                if cur.fetchone()[0] != 1:
                    raise RuntimeError("OPENPLAY_TEAM_CROSSWALK_TARGET_NOT_UNIQUE:" + row["team"])
                overlap = sorted(str(value) for value in row["mapped_openplay_competition_keys"])
                if not overlap:
                    raise RuntimeError("OPENPLAY_TEAM_CROSSWALK_COMPETITION_OVERLAP_MISSING")
                reason = (
                    f"Exact normalized team-name match; unique in both source inventories; "
                    f"overlapping resolved competition canonical keys={','.join(overlap)}; "
                    f"OpenPlay team={row['team']!r}, country={row['country']!r}; "
                    f"5Dollar team ID={target_provider_id}; evidence asset SHA-256={team_asset_hash}."
                )
                team_rows.append((
                    "TEAM",OPENPLAY_PROVIDER,OPENPLAY_SOURCE_ID,str(row["openplay_team_id"]),
                    canonical,1,"RESOLVED","EXACT_NAME_AND_COMPETITION_OVERLAP",1.0,
                    REVIEWER_ID,evidence_ids["teams.parquet"],reason,
                ))

            comp_rows = []
            for row in competitions:
                if row.get("source_asset_sha256") != comp_asset_hash:
                    raise RuntimeError("OPENPLAY_COMPETITION_CROSSWALK_ASSET_HASH_MISMATCH")
                canonical = str(row["canonical_competition_key"])
                cur.execute("""
                    SELECT count(*) FROM entity_crosswalk_versions
                    WHERE entity_type='COMPETITION' AND provider=%s AND source_id=%s
                      AND canonical_entity_key=%s AND mapping_status='RESOLVED'
                """, (FIVEDOLLAR_PROVIDER,FIVEDOLLAR_SOURCE_ID,canonical))
                if cur.fetchone()[0] < 1:
                    raise RuntimeError("OPENPLAY_COMPETITION_CROSSWALK_TARGET_NOT_RESOLVED")
                reason = (
                    f"Explicit region+competition alias: {row['region']} / {row['competition']}; "
                    f"mapped to resolved 5Dollar canonical competition key={canonical}; "
                    f"evidence asset SHA-256={comp_asset_hash}."
                )
                comp_rows.append((
                    "COMPETITION",OPENPLAY_PROVIDER,OPENPLAY_SOURCE_ID,str(row["openplay_comp"]),
                    canonical,1,"RESOLVED","EXPLICIT_REGION_NAME_ALIAS",1.0,
                    REVIEWER_ID,evidence_ids["competitions.parquet"],reason,
                ))

            now_sql = "NOW()"
            cur.executemany(f"""
                INSERT INTO entity_crosswalk_versions(
                    entity_type,provider,source_id,provider_entity_id,canonical_entity_key,
                    mapping_version,mapping_status,mapping_method,confidence,reviewer_id,
                    evidence_observation_id,decision_reason,valid_from,recorded_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,{now_sql},{now_sql}
                )
            """,team_rows)
            inserted_team_rows = cur.rowcount
            cur.executemany(f"""
                INSERT INTO entity_crosswalk_versions(
                    entity_type,provider,source_id,provider_entity_id,canonical_entity_key,
                    mapping_version,mapping_status,mapping_method,confidence,reviewer_id,
                    evidence_observation_id,decision_reason,valid_from,recorded_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,{now_sql},{now_sql}
                )
            """,comp_rows)
            inserted_comp_rows = cur.rowcount

            cur.execute("""
                SELECT entity_type,count(*),count(DISTINCT provider_entity_id),
                       count(*) FILTER (WHERE mapping_status='RESOLVED')
                FROM entity_crosswalk_versions
                WHERE provider=%s AND source_id=%s
                GROUP BY entity_type
            """, (OPENPLAY_PROVIDER,OPENPLAY_SOURCE_ID))
            readback = {row[0]:row[1:] for row in cur.fetchall()}
            if readback.get("TEAM") != (89,89,89) or readback.get("COMPETITION") != (5,5,5):
                raise RuntimeError("OPENPLAY_CROSSWALK_READBACK_MISMATCH")
        conn.commit()

    return {
        "status":"OPENPLAY_EXACT_CROSSWALKS_PERSISTED",
        "team_mappings":len(teams),
        "competition_mappings":len(competitions),
        "total_mappings":len(teams)+len(competitions),
        "ambiguous_or_unmatched_entities_written":0,
        "commercial_use_allowed":False,
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--candidates",required=True)
    args=parser.parse_args()
    result=apply_crosswalk(os.getenv("DATABASE_URL",""),args.candidates)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
