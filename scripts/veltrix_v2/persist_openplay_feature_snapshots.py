"""Persist point-in-time eligible OpenPlay feature snapshots for upcoming V2 targets.

Reads the verified derived feature bundle and writes only to the allowlisted
Neon staging database. Each snapshot links every selected team-match row to its
source observation, resolved team crosswalk, rights approval and evidence hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from veltrix_v2.data.openplay_feature_bundle import (
    canonical_json_bytes,
    eligible_openplay_features_as_of,
    iter_openplay_feature_bundle,
)

EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
OPENPLAY_PROVIDER = "OpenPlay / WhoScored / Opta"
OPENPLAY_SOURCE_ID = "openplay-data-v0.1.0"
APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"
FEATURE_SCHEMA = "openplay-team-match-context-v1"
MODEL_BUILD_ID = "veltrix-openplay-feature-admission-v1"
SELECTOR_VERSION = "latest-five-eligible-per-team-before-target-date-v1"
MAX_TEAM_MATCH_ROWS = 5


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.casefold())


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("FEATURE_TIMESTAMP_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _select_team_rows(
    features: list[Mapping[str, Any]], *, team_id: str, competition_id: str,
    cutoff_at: datetime, target_date: date, limit: int = MAX_TEAM_MATCH_ROWS,
) -> tuple[Mapping[str, Any], ...]:
    eligible = eligible_openplay_features_as_of(
        features,
        cutoff_at=cutoff_at,
        canonical_team_id=team_id,
        canonical_competition_id=competition_id,
        before_match_date=target_date,
    )
    ordered = sorted(
        eligible,
        key=lambda row: (str(row["match_date"]), str(row["eligibility_at"]), str(row["provider_match_id"])),
        reverse=True,
    )
    return tuple(ordered[:limit])


def _feature_value(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "provider_match_id": row["provider_match_id"],
        "match_date": row["match_date"],
        "xg_model": row["xg_model"],
        "metrics": row["metrics"],
        "feature_sha256": row["feature_sha256"],
        "eligibility_at": row["eligibility_at"],
        "source_timestamp_basis": row["source_timestamp_basis"],
        "source_observation_payload_sha256": row["source_observation_payload_sha256"],
        "crosswalk_provenance": row["crosswalk_provenance"],
        "asset_provenance": row["asset_provenance"],
    }


def _load_targets(cur, cutoff_at: datetime) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT f.id,f.provider_fixture_id,f.competition_id,f.home_team_id,
               f.away_team_id,f.kickoff_at,c.name,ht.name,at.name,
               fx.crosswalk_version_id,fx.recorded_at
        FROM fixtures f
        JOIN competitions c ON c.id=f.competition_id
        JOIN teams ht ON ht.id=f.home_team_id
        JOIN teams at ON at.id=f.away_team_id
        JOIN LATERAL (
            SELECT x.crosswalk_version_id,x.canonical_entity_key,x.recorded_at
            FROM entity_crosswalk_versions x
            WHERE x.provider='5DollarFootballAPI'
              AND x.source_id='5dollarfootballapi'
              AND x.entity_type='FIXTURE'
              AND x.provider_entity_id=f.provider_fixture_id
              AND x.mapping_status='RESOLVED'
              AND x.valid_from<=%s
              AND (x.valid_until IS NULL OR x.valid_until>%s)
              AND x.recorded_at<=%s
            ORDER BY x.mapping_version DESC
            LIMIT 1
        ) fx ON fx.canonical_entity_key=f.id::text
        WHERE f.provider='5DollarFootballAPI'
          AND f.status='SCHEDULED'
          AND f.kickoff_at>%s
        ORDER BY f.kickoff_at,f.id
        """,
        (cutoff_at, cutoff_at, cutoff_at, cutoff_at),
    )
    rows = []
    for row in cur.fetchall():
        fixture_id, provider_fixture_id, competition_id, home_id, away_id, kickoff, competition, home, away, crosswalk_id, fixture_crosswalk_recorded_at = row
        if home_id == away_id or kickoff <= cutoff_at or fixture_crosswalk_recorded_at > cutoff_at:
            continue
        rows.append({
            "fixture_id": int(fixture_id),
            "provider_fixture_id": str(provider_fixture_id),
            "competition_id": str(competition_id),
            "home_team_id": str(home_id),
            "away_team_id": str(away_id),
            "kickoff_at": kickoff.astimezone(timezone.utc),
            "competition": competition,
            "home_team": home,
            "away_team": away,
            "fixture_crosswalk_version_id": int(crosswalk_id),
        })
    return rows


def _verify_source_rows(cur, selected: list[Mapping[str, Any]], cutoff_at: datetime) -> None:
    ids = sorted({int(row["source_observation_id"]) for row in selected})
    if not ids:
        raise ValueError("FEATURE_SOURCE_OBSERVATIONS_EMPTY")
    cur.execute(
        """
        SELECT so.id,so.provider,so.source_id,so.entity_type,so.provider_entity_id,
               so.payload_sha256,so.source_published_at,so.available_at,so.recorded_at,
               so.point_in_time_certifiable,so.rights_approval_id,so.source_timestamp_basis,
               so.provider_response_id,pr.provider,pr.source_id,pr.response_sha256
        FROM source_observations so
        JOIN provider_responses pr ON pr.id=so.provider_response_id
        WHERE so.id = ANY(%s)
        """,
        (ids,),
    )
    observations = {int(row[0]): row for row in cur.fetchall()}
    for feature in selected:
        observation_id = int(feature["source_observation_id"])
        obs = observations.get(observation_id)
        if obs is None:
            raise ValueError("FEATURE_SOURCE_OBSERVATION_MISSING")
        (_, provider, source_id, entity_type, provider_entity_id, payload_hash,
         published_at, available_at, recorded_at, pit, rights_id, timestamp_basis,
         response_id,response_provider,response_source,response_sha256) = obs
        if (
            provider != OPENPLAY_PROVIDER or source_id != OPENPLAY_SOURCE_ID
            or entity_type != "match_result_snapshot"
            or str(provider_entity_id) != str(feature["provider_match_id"])
            or str(payload_hash).strip() != feature["source_observation_payload_sha256"]
            or published_at is None or available_at is None or recorded_at is None
            or pit is not True or rights_id != APPROVAL_ID
            or timestamp_basis != "documented_guarantee"
            or int(response_id) != int(feature["provider_response_id"])
            or response_provider != OPENPLAY_PROVIDER or response_source != OPENPLAY_SOURCE_ID
            or str(response_sha256).strip() != feature["asset_provenance"]["matches.parquet"]["sha256"]
            or published_at >= cutoff_at or available_at >= cutoff_at or recorded_at >= cutoff_at
            or published_at.astimezone(timezone.utc).isoformat() != parse_time(feature["source_published_at"]).isoformat()
            or available_at.astimezone(timezone.utc).isoformat() != parse_time(feature["available_at"]).isoformat()
            or recorded_at.astimezone(timezone.utc).isoformat() != parse_time(feature["recorded_at"]).isoformat()
        ):
            raise ValueError("FEATURE_SOURCE_OBSERVATION_PROVENANCE_MISMATCH")

        crosswalks = feature.get("crosswalk_provenance") or {}
        team = crosswalks.get("team") or {}
        opponent = crosswalks.get("opponent") or {}
        competition = crosswalks.get("competition") or {}
        for mapping, entity_type_expected, canonical_id in (
            (team, "TEAM", feature["canonical_team_id"]),
            (opponent, "TEAM", feature["canonical_opponent_id"]),
            (competition, "COMPETITION", feature["canonical_competition_id"]),
        ):
            cur.execute(
                """
                SELECT provider,source_id,entity_type,canonical_entity_key,mapping_status,
                       mapping_method,valid_from,valid_until,recorded_at,evidence_observation_id
                FROM entity_crosswalk_versions WHERE crosswalk_version_id=%s
                """,
                (int(mapping["crosswalk_version_id"]),),
            )
            mapped = cur.fetchone()
            if (
                mapped is None or mapped[0] != OPENPLAY_PROVIDER or mapped[1] != OPENPLAY_SOURCE_ID
                or mapped[2] != entity_type_expected or mapped[3] != str(canonical_id)
                or mapped[4] != "RESOLVED"
                or mapped[5] != ("EXACT_NAME_AND_COMPETITION_OVERLAP" if entity_type_expected == "TEAM" else "EXPLICIT_REGION_NAME_ALIAS")
                or mapped[6] >= cutoff_at
                or (mapped[7] is not None and mapped[7] <= cutoff_at)
                or mapped[8] >= cutoff_at
                or int(mapped[9]) != int(
                    feature["asset_provenance"]["teams.parquet"]["source_observation_id"]
                    if entity_type_expected == "TEAM"
                    else feature["asset_provenance"]["competitions.parquet"]["source_observation_id"]
                )
            ):
                raise ValueError("FEATURE_CROSSWALK_PROVENANCE_MISMATCH")


def _insert_snapshot(cur, target: Mapping[str, Any], cutoff_at: datetime,
                     selected_rows: list[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    link_payloads = []
    for key, row in selected_rows:
        value = _feature_value(row)
        link_payloads.append({
            "feature_key": key,
            "feature_value": value,
            "source_observation_id": int(row["source_observation_id"]),
            "crosswalk_version_id": int(row["crosswalk_provenance"]["team"]["crosswalk_version_id"]),
            "source_published_at": row["source_published_at"],
            "retrieved_at": row["recorded_at"],
            "rights_approval_id": row["rights_approval_id"],
            "value_sha256": sha256(canonical_json_bytes(value)),
        })
    # Stable content identity excludes the execution clock. Re-running the
    # workflow with unchanged source rows reuses the immutable snapshot.
    feature_set_sha = sha256(canonical_json_bytes({
        "fixture_id": target["fixture_id"],
        "fixture_crosswalk_version_id": target["fixture_crosswalk_version_id"],
        "feature_schema_version": FEATURE_SCHEMA,
        "selector_version": SELECTOR_VERSION,
        "links": link_payloads,
    }))
    snapshot_key = f"openplay:{target['fixture_id']}:{feature_set_sha}"

    cur.execute(
        """
        SELECT feature_snapshot_id,prediction_cutoff_at,feature_set_sha256
        FROM feature_snapshots WHERE snapshot_key=%s
        """,
        (snapshot_key,),
    )
    existing = cur.fetchone()
    if existing:
        snapshot_id, snapshot_cutoff, stored_hash = int(existing[0]), existing[1], str(existing[2]).strip()
        if stored_hash != feature_set_sha or snapshot_cutoff > cutoff_at:
            raise ValueError("FEATURE_SNAPSHOT_IDEMPOTENCY_CONFLICT")
        for _, row in selected_rows:
            if parse_time(row["eligibility_at"]) >= snapshot_cutoff:
                raise ValueError("FEATURE_SNAPSHOT_REUSE_CUTOFF_INVALID")
        cur.execute(
            """
            SELECT feature_key,value_sha256,source_observation_id,crosswalk_version_id,
                   source_published_at,retrieved_at,rights_approval_id
            FROM feature_snapshot_links WHERE feature_snapshot_id=%s
            ORDER BY feature_key
            """,
            (snapshot_id,),
        )
        actual = cur.fetchall()
        expected = sorted(
            (
                item["feature_key"],item["value_sha256"],item["source_observation_id"],
                item["crosswalk_version_id"],parse_time(item["source_published_at"]),
                parse_time(item["retrieved_at"]),item["rights_approval_id"],
            )
            for item in link_payloads
        )
        normalised_actual = sorted(
            (
                row[0],str(row[1]).strip(),int(row[2]),int(row[3]),
                row[4].astimezone(timezone.utc),row[5].astimezone(timezone.utc),row[6],
            )
            for row in actual
        )
        if normalised_actual != expected:
            raise ValueError("FEATURE_SNAPSHOT_REUSE_LINKS_MISMATCH")
        cur.execute(
            """
            SELECT eligibility_status,evidence_sha256
            FROM feature_snapshot_eligibility_events
            WHERE feature_snapshot_id=%s
            ORDER BY recorded_at DESC,eligibility_event_id DESC LIMIT 1
            """,
            (snapshot_id,),
        )
        event = cur.fetchone()
        if event is None or event[0] != "ELIGIBLE" or not _is_sha256(str(event[1]).strip()):
            raise ValueError("FEATURE_SNAPSHOT_REUSE_ELIGIBILITY_EVENT_INVALID")
        return {
            "fixture_id": target["fixture_id"],
            "provider_fixture_id": target["provider_fixture_id"],
            "home_team": target["home_team"],
            "away_team": target["away_team"],
            "competition": target["competition"],
            "kickoff_at": target["kickoff_at"].isoformat(),
            "prediction_cutoff_at": snapshot_cutoff.astimezone(timezone.utc).isoformat(),
            "feature_snapshot_id": snapshot_id,
            "feature_count": len(link_payloads),
            "home_match_rows": sum(1 for key, _ in selected_rows if key.startswith("home.")),
            "away_match_rows": sum(1 for key, _ in selected_rows if key.startswith("away.")),
            "feature_set_sha256": feature_set_sha,
            "eligibility_evidence_sha256": str(event[1]).strip(),
            "reused_existing_snapshot": True,
        }

    snapshot_cutoff = cutoff_at
    evidence_sha = sha256(canonical_json_bytes({
        "snapshot_key": snapshot_key,
        "fixture_crosswalk_version_id": target["fixture_crosswalk_version_id"],
        "prediction_cutoff_at": snapshot_cutoff.isoformat(),
        "feature_set_sha256": feature_set_sha,
        "links": [
            {k: v for k, v in item.items() if k != "feature_value"}
            for item in link_payloads
        ],
        "eligibility": "ELIGIBLE",
        "rule": "source publication, availability, VELTRIX record, rights and all crosswalk clocks strictly precede cutoff; match date strictly precedes target date",
    }))
    cur.execute(
        """
        INSERT INTO feature_snapshots(
            snapshot_key,fixture_id,prediction_cutoff_at,feature_schema_version,
            model_build_id,feature_set_sha256,selector_version
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        RETURNING feature_snapshot_id
        """,
        (snapshot_key,target["fixture_id"],snapshot_cutoff,FEATURE_SCHEMA,MODEL_BUILD_ID,feature_set_sha,SELECTOR_VERSION),
    )
    snapshot_id = int(cur.fetchone()[0])
    for item in link_payloads:
        cur.execute(
            """
            INSERT INTO feature_snapshot_links(
                feature_snapshot_id,feature_key,feature_status,feature_value,
                source_observation_id,crosswalk_version_id,source_published_at,
                retrieved_at,rights_approval_id,eligibility_reason_code,value_sha256
            ) VALUES (%s,%s,'PRESENT',%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                snapshot_id,item["feature_key"],
                json.dumps(item["feature_value"],sort_keys=True,separators=(",",":"),ensure_ascii=False),
                item["source_observation_id"],item["crosswalk_version_id"],
                parse_time(item["source_published_at"]),parse_time(item["retrieved_at"]),
                item["rights_approval_id"],
                "STRICT_PIT_SOURCE_AND_CROSSWALK_CLOCKS_BEFORE_CUTOFF",
                item["value_sha256"],
            ),
        )
    cur.execute(
        "SELECT count(*),count(*) FILTER (WHERE feature_status='PRESENT') FROM feature_snapshot_links WHERE feature_snapshot_id=%s",
        (snapshot_id,),
    )
    link_count, present_count = cur.fetchone()
    if int(link_count) != len(link_payloads) or int(present_count) != len(link_payloads):
        raise ValueError("FEATURE_SNAPSHOT_LINK_COUNT_MISMATCH")
    cur.execute(
        """
        INSERT INTO feature_snapshot_eligibility_events(
            feature_snapshot_id,eligibility_status,reason_codes,evidence_sha256
        ) VALUES (%s,'ELIGIBLE',%s::jsonb,%s)
        """,
        (
            snapshot_id,
            json.dumps([
                "TARGET_FIXTURE_IDENTITY_RESOLVED",
                "HOME_AND_AWAY_TEAM_CROSSWALKS_RESOLVED",
                "COMPETITION_CROSSWALK_RESOLVED",
                "SOURCE_PUBLICATION_AVAILABILITY_AND_RECORDING_PRECEDE_CUTOFF",
                "SOURCE_MATCH_DATE_STRICTLY_PRECEDES_TARGET_DATE",
                "APPROVED_NONCOMMERCIAL_RIGHTS_VALID_AT_CUTOFF",
            ]),
            evidence_sha,
        ),
    )
    return {
        "fixture_id": target["fixture_id"],
        "provider_fixture_id": target["provider_fixture_id"],
        "home_team": target["home_team"],
        "away_team": target["away_team"],
        "competition": target["competition"],
        "kickoff_at": target["kickoff_at"].isoformat(),
        "prediction_cutoff_at": snapshot_cutoff.isoformat(),
        "feature_snapshot_id": snapshot_id,
        "feature_count": len(link_payloads),
        "home_match_rows": sum(1 for key, _ in selected_rows if key.startswith("home.")),
        "away_match_rows": sum(1 for key, _ in selected_rows if key.startswith("away.")),
        "feature_set_sha256": feature_set_sha,
        "eligibility_evidence_sha256": evidence_sha,
        "reused_existing_snapshot": False,
    }


def persist(database_url: str, manifest_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    parsed = urlparse(database_url)
    if (parsed.hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("FEATURE_SNAPSHOT_STAGING_HOST_MISMATCH")
    if parse_qs(parsed.query).get("sslmode", [""])[0].casefold() not in {"require","verify-ca","verify-full"}:
        raise RuntimeError("FEATURE_SNAPSHOT_STAGING_TLS_REQUIRED")

    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    features = list(iter_openplay_feature_bundle(manifest_path))
    cutoff_at = datetime.now(timezone.utc)
    import psycopg

    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(),current_user")
                database, role = cur.fetchone()
                if database != EXPECTED_DATABASE or role != "neondb_owner":
                    raise RuntimeError("FEATURE_SNAPSHOT_STAGING_TARGET_MISMATCH")
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('veltrix-openplay-feature-snapshot-admission-v1'))")
                cur.execute(
                    """
                    SELECT status,rights_basis,evidence_sha256,valid_from,valid_until,
                           permitted_uses,commercial_use_allowed,attribution_required,
                           attribution_text,attribution_url,raw_redistribution_allowed
                    FROM source_approvals WHERE approval_id=%s
                    """,
                    (APPROVAL_ID,),
                )
                approval = cur.fetchone()
                if (
                    approval is None or approval[0] != "APPROVED" or approval[1] != "WRITTEN_PERMISSION"
                    or str(approval[2]).strip() != manifest.get("approval_evidence_sha256")
                    or approval[3] > cutoff_at or (approval[4] is not None and approval[4] <= cutoff_at)
                    or not {"collection","storage","historical_import","internal_analysis","model_training","model_validation","derived_research","cache"} <= set(approval[5])
                    or approval[6] is not False or approval[7] is not True
                    or approval[8] != "openplay (Noah Bair)"
                    or approval[9] != "https://github.com/nlbair/openplay"
                    or approval[10] is not False
                ):
                    raise RuntimeError("OPENPLAY_FEATURE_APPROVAL_NOT_ACTIVE_OR_SCOPE_MISMATCH")
                cur.execute(
                    """
                    SELECT status,effective_at,recorded_at,evidence_sha256
                    FROM source_approval_status_events
                    WHERE approval_id=%s
                    ORDER BY effective_at DESC,recorded_at DESC,event_id DESC LIMIT 1
                    """,
                    (APPROVAL_ID,),
                )
                latest_approval_event = cur.fetchone()
                if (
                    latest_approval_event is None
                    or latest_approval_event[0] != "APPROVED"
                    or latest_approval_event[1] > cutoff_at
                    or latest_approval_event[2] > cutoff_at
                    or str(latest_approval_event[3]).strip() != manifest.get("approval_evidence_sha256")
                ):
                    raise RuntimeError("OPENPLAY_FEATURE_APPROVAL_STATUS_EVENT_INVALID")
                targets = _load_targets(cur, cutoff_at)
                snapshots = []
                skipped = []
                for target in targets:
                    target_date = target["kickoff_at"].date()
                    home_rows = _select_team_rows(
                        features,team_id=target["home_team_id"],
                        competition_id=target["competition_id"],
                        cutoff_at=cutoff_at,target_date=target_date,
                    )
                    away_rows = _select_team_rows(
                        features,team_id=target["away_team_id"],
                        competition_id=target["competition_id"],
                        cutoff_at=cutoff_at,target_date=target_date,
                    )
                    if not home_rows or not away_rows:
                        skipped.append({
                            "fixture_id":target["fixture_id"],
                            "reason":"OPENPLAY_TEAM_HISTORY_NOT_AVAILABLE_FOR_BOTH_TEAMS",
                            "home_rows":len(home_rows),"away_rows":len(away_rows),
                        })
                        continue
                    selected = []
                    for side, rows in (("home",home_rows),("away",away_rows)):
                        for index,row in enumerate(rows,1):
                            selected.append((f"{side}.match.{index}",row))
                    _verify_source_rows(cur,[row for _,row in selected],cutoff_at)
                    snapshots.append(_insert_snapshot(cur,target,cutoff_at,selected))
                if not snapshots:
                    raise RuntimeError("NO_ELIGIBLE_OPENPLAY_TARGET_FEATURE_SNAPSHOTS")
                cur.execute(
                    """
                    SELECT count(*) FROM feature_snapshots
                    WHERE feature_snapshot_id = ANY(%s)
                    """,
                    ([item["feature_snapshot_id"] for item in snapshots],),
                )
                if int(cur.fetchone()[0]) != len(snapshots):
                    raise RuntimeError("FEATURE_SNAPSHOT_PRECOMMIT_VERIFICATION_FAILED")

    # Fresh connection verifies committed snapshots, links and eligibility events.
    with psycopg.connect(database_url) as verify:
        with verify.cursor() as cur:
            ids = [item["feature_snapshot_id"] for item in snapshots]
            cur.execute(
                """
                SELECT count(DISTINCT fs.feature_snapshot_id),
                       count(DISTINCT fsl.feature_snapshot_link_id),
                       count(DISTINCT fee.eligibility_event_id)
                FROM feature_snapshots fs
                LEFT JOIN feature_snapshot_links fsl ON fsl.feature_snapshot_id=fs.feature_snapshot_id
                LEFT JOIN feature_snapshot_eligibility_events fee ON fee.feature_snapshot_id=fs.feature_snapshot_id
                  AND fee.eligibility_status='ELIGIBLE'
                WHERE fs.feature_snapshot_id = ANY(%s)
                """,
                (ids,),
            )
            snap_count, link_count, eligible_count = cur.fetchone()
            expected_links = sum(item["feature_count"] for item in snapshots)
            if int(snap_count) != len(snapshots) or int(link_count) != expected_links or int(eligible_count) != len(snapshots):
                raise RuntimeError("FEATURE_SNAPSHOT_POST_COMMIT_VERIFICATION_FAILED")

    summary = {
        "status":"PASS_OPENPLAY_PIT_FEATURE_SNAPSHOT_ADMISSION",
        "provider":OPENPLAY_PROVIDER,
        "cutoff_at":cutoff_at.isoformat(),
        "source_bundle_sha256":manifest["feature_rows_sha256"],
        "source_feature_rows":manifest["feature_count"],
        "targets_considered":len(targets),
        "eligible_target_snapshots":len(snapshots),
        "new_snapshots_created":sum(1 for item in snapshots if not item["reused_existing_snapshot"]),
        "existing_snapshots_reused":sum(1 for item in snapshots if item["reused_existing_snapshot"]),
        "skipped_targets":skipped,
        "feature_links_written":sum(item["feature_count"] for item in snapshots if not item["reused_existing_snapshot"]),
        "feature_links_reused":sum(item["feature_count"] for item in snapshots if item["reused_existing_snapshot"]),
        "snapshots":snapshots,
        "database":"veltrix_football_staging",
        "fresh_connection_post_commit_verified":True,
        "commercial_use_allowed":False,
        "monetisation_prohibited":True,
        "predictions_generated":False,
        "publication":False,
        "telegram_delivery":False,
    }
    out=Path(output_path)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return summary


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",default="openplay-feature-bundle/openplay_feature_bundle_manifest.json")
    parser.add_argument("--output",default="artifacts/openplay-feature-snapshot-admission/summary.json")
    args=parser.parse_args()
    database_url=os.getenv("VELTRIX_STAGING_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not database_url:
        raise RuntimeError("FEATURE_SNAPSHOT_STAGING_DATABASE_URL_REQUIRED")
    summary=persist(database_url,args.manifest,args.output)
    print(json.dumps({
        "status":summary["status"],
        "targets_considered":summary["targets_considered"],
        "eligible_target_snapshots":summary["eligible_target_snapshots"],
        "feature_links_written":summary["feature_links_written"],
        "skipped_targets":len(summary["skipped_targets"]),
        "fresh_connection_post_commit_verified":summary["fresh_connection_post_commit_verified"],
        "predictions_generated":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
