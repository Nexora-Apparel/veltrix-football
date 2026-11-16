"""Link immutable V2 forecast events to their exact PIT feature snapshots.

Default mode is read-only. --apply appends links to the staging-only sidecar
table after validating both original workflow artifacts and every database row.
No paper-ledger event, feature snapshot, or prediction is updated.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target

EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_ROLE = "neondb_owner"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
EXPECTED_MODEL = "veltrix-openplay-xg-poisson-v1"
EXPECTED_OPENPLAY_RIGHTS_APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"
EXPECTED_OPENPLAY_PROVIDER = "OpenPlay / WhoScored / Opta"
EXPECTED_OPENPLAY_SOURCE_ID = "openplay-data-v0.1.0"
EXPECTED_ARTIFACT_RUN_ID = 43775129579
EXPECTED_MODEL_ARTIFACT_SHA256 = "0332c6537e44c189653b4ff74b816beed3c5ab484ee9b205e261c149fef51eda"
EXPECTED_FORECAST_SUMMARY_SHA256 = "dc9ad20a8fac7bfb6bf480131f0bad3044be83215c5350ef72b789073884aeb6"
EXPECTED_FEATURE_ADMISSION_SUMMARY_SHA256 = "221cc91126182d35cda147c40517258d2199fce0a1353aed495c7054c0834ac7"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _aware(value: str) -> datetime:
    parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("FORECAST_EVIDENCE_TIMESTAMP_NOT_AWARE")
    return parsed.astimezone(timezone.utc)


def _load_artifacts(forecast_path: str | Path, admission_path: str | Path) -> tuple[dict,dict,str,str]:
    forecast_raw=Path(forecast_path).read_bytes()
    admission_raw=Path(admission_path).read_bytes()
    forecast_sha=_sha256(forecast_raw)
    admission_sha=_sha256(admission_raw)
    if forecast_sha != EXPECTED_FORECAST_SUMMARY_SHA256:
        raise ValueError("V2_FORECAST_SUMMARY_SHA256_MISMATCH")
    if admission_sha != EXPECTED_FEATURE_ADMISSION_SUMMARY_SHA256:
        raise ValueError("V2_FEATURE_ADMISSION_SUMMARY_SHA256_MISMATCH")
    forecast=json.loads(forecast_raw)
    admission=json.loads(admission_raw)
    if (
        forecast.get("status") != "PASS_OPENPLAY_V2_PROSPECTIVE_FORECAST_SERIES"
        or forecast.get("model_version") != EXPECTED_MODEL
        or forecast.get("model_artifact_sha256") != EXPECTED_MODEL_ARTIFACT_SHA256
        or forecast.get("forecasts_generated") != 7
        or forecast.get("ledger_events_appended") != 7
        or forecast.get("ledger_chain_verified") is not True
        or forecast.get("fresh_connection_post_commit_verified") is not True
        or forecast.get("certification") != "NOT_CERTIFIED"
        or forecast.get("commercial_use_allowed") is not False
        or forecast.get("monetisation_prohibited") is not True
        or forecast.get("publication") is not False
        or forecast.get("telegram_delivery") is not False
        or forecast.get("schedule_activation") is not False
        or forecast.get("value_betting") != "LOCKED"
    ):
        raise ValueError("V2_FORECAST_ARTIFACT_CONTRACT_INVALID")
    if (
        admission.get("status") != "PASS_OPENPLAY_PIT_FEATURE_SNAPSHOT_ADMISSION"
        or admission.get("eligible_target_snapshots") != 7
        or admission.get("provider") != "OpenPlay / WhoScored / Opta"
        or admission.get("fresh_connection_post_commit_verified") is not True
        or admission.get("predictions_generated") is not False
        or admission.get("commercial_use_allowed") is not False
        or admission.get("monetisation_prohibited") is not True
        or admission.get("publication") is not False
        or admission.get("telegram_delivery") is not False
        or len(admission.get("skipped_targets",[])) != 18
    ):
        raise ValueError("V2_FEATURE_ADMISSION_ARTIFACT_CONTRACT_INVALID")
    if len(forecast.get("forecasts",[])) != 7 or len(admission.get("snapshots",[])) != 7:
        raise ValueError("V2_ARTIFACT_FORECAST_OR_SNAPSHOT_COUNT_INVALID")
    if len(forecast.get("ledger_event_sha256",[])) != 7:
        raise ValueError("V2_LEDGER_EVENT_HASH_COUNT_INVALID")
    return forecast,admission,forecast_sha,admission_sha


def _prepare_links(forecast: dict, admission: dict, forecast_sha: str, admission_sha: str) -> list[dict]:
    snapshots={str(item["provider_fixture_id"]):item for item in admission["snapshots"]}
    forecast_cutoff=_aware(forecast["forecast_cutoff_at"])
    prepared=[]
    for index,item in enumerate(forecast["forecasts"]):
        provider_fixture_id=str(item["provider_fixture_id"])
        snapshot=snapshots.get(provider_fixture_id)
        if snapshot is None:
            raise ValueError("V2_FORECAST_FEATURE_SNAPSHOT_NOT_FOUND_IN_ARTIFACT")
        if (
            item["model_version"] != EXPECTED_MODEL
            or int(item["feature_snapshot_id"]) != int(snapshot["feature_snapshot_id"])
            or item["feature_set_sha256"] != snapshot["feature_set_sha256"]
            or item["fixture_id"] != f"5dollarfootballapi:{provider_fixture_id}"
        ):
            raise ValueError("V2_FORECAST_AND_FEATURE_SNAPSHOT_ARTIFACTS_DISAGREE")
        snapshot_cutoff=_aware(item["prediction_cutoff_at"])
        if snapshot_cutoff > forecast_cutoff:
            raise ValueError("V2_FEATURE_SNAPSHOT_AFTER_FORECAST_CUTOFF")
        payload={
            "provider_fixture_id":provider_fixture_id,
            "feature_count":int(snapshot["feature_count"]),
            "feature_snapshot_id":int(snapshot["feature_snapshot_id"]),
            "feature_set_sha256":snapshot["feature_set_sha256"],
            "eligibility_evidence_sha256":snapshot["eligibility_evidence_sha256"],
            "forecast_evidence_sha256":item["evidence_sha256"],
            "model_artifact_sha256":forecast["model_artifact_sha256"],
            "forecast_cutoff_at":forecast_cutoff.isoformat(),
            "feature_snapshot_cutoff_at":snapshot_cutoff.isoformat(),
            "artifact_run_id":EXPECTED_ARTIFACT_RUN_ID,
            "forecast_summary_sha256":forecast_sha,
            "feature_admission_summary_sha256":admission_sha,
        }
        payload["expected_prediction_event_sha256"]=forecast["ledger_event_sha256"][index]
        prepared.append(payload)
    return prepared


def _connect(dsn: str, *, readonly: bool):
    import psycopg
    conn=psycopg.connect(dsn,autocommit=False)
    if readonly:
        conn.execute("SET TRANSACTION READ ONLY")
    conn.execute("SET LOCAL statement_timeout='20000ms'")
    identity=conn.execute("SELECT current_database(),current_user").fetchone()
    if identity != (EXPECTED_DATABASE,EXPECTED_ROLE):
        conn.close()
        raise PermissionError("V2_PREDICTION_FEATURE_LINK_TARGET_NOT_ALLOWLISTED")
    return conn


def _resolve_links(conn, prepared: list[dict]) -> list[dict]:
    resolved=[]
    for item in prepared:
        event=conn.execute(
            """
            SELECT ledger_id,sequence,event_sha256,event_type,model_version,
                   fixture_id,payload->>'evidence_sha256',
                   payload->>'competition_id',payload->>'home_team_id',
                   payload->>'away_team_id',created_at
            FROM paper_ledger_events
            WHERE event_type='PREDICTION'
              AND model_version=%s
              AND event_sha256=%s
            """,
            (EXPECTED_MODEL,item["expected_prediction_event_sha256"]),
        ).fetchone()
        if (
            event is None or event[3]!="PREDICTION" or event[4]!=EXPECTED_MODEL
            or str(event[6])!=item["forecast_evidence_sha256"]
            or str(event[5])!=f"5dollarfootballapi:{item['provider_fixture_id']}"
        ):
            raise ValueError("V2_PAPER_LEDGER_EVENT_EVIDENCE_MISMATCH")
        snapshot=conn.execute(
            """
            SELECT fs.fixture_id,fs.feature_set_sha256,fs.prediction_cutoff_at,fs.created_at,
                   f.provider_fixture_id::text,f.competition_id,f.home_team_id,f.away_team_id,
                   c.provider_competition_id,ht.provider_team_id,at.provider_team_id
            FROM feature_snapshots fs
            JOIN fixtures f ON f.id=fs.fixture_id
            JOIN competitions c ON c.id=f.competition_id AND c.provider=f.provider
            JOIN teams ht ON ht.id=f.home_team_id AND ht.provider=f.provider
            JOIN teams at ON at.id=f.away_team_id AND at.provider=f.provider
            WHERE fs.feature_snapshot_id=%s AND f.provider='5DollarFootballAPI'
            """,
            (item["feature_snapshot_id"],),
        ).fetchone()
        if snapshot is None or str(snapshot[4]) != str(item["provider_fixture_id"]):
            raise ValueError("V2_FEATURE_SNAPSHOT_CANONICAL_FIXTURE_MISMATCH")
        if (
            str(snapshot[1]).strip()!=item["feature_set_sha256"]
            or str(event[7])!=str(snapshot[5])
            or str(event[8])!=str(snapshot[6])
            or str(event[9])!=str(snapshot[7])
            or snapshot[2].astimezone(timezone.utc)!=_aware(item["feature_snapshot_cutoff_at"])
            or snapshot[2] > _aware(item["forecast_cutoff_at"])
            or snapshot[3] > _aware(item["forecast_cutoff_at"])
        ):
            raise ValueError("V2_FEATURE_SNAPSHOT_CUTOFF_OR_HASH_MISMATCH")
        link_counts=conn.execute(
            """
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE fsl.feature_status='PRESENT'),
                   COUNT(*) FILTER (
                       WHERE fsl.feature_status <> 'PRESENT'
                          OR fsl.source_published_at IS NULL
                          OR fsl.retrieved_at IS NULL
                          OR fsl.rights_approval_id IS DISTINCT FROM %s
                          OR so.id IS NULL
                          OR so.provider IS DISTINCT FROM %s
                          OR so.source_id IS DISTINCT FROM %s
                          OR so.point_in_time_certifiable IS DISTINCT FROM TRUE
                          OR so.source_timestamp_basis IS DISTINCT FROM 'documented_guarantee'
                          OR so.rights_approval_id IS DISTINCT FROM %s
                          OR so.source_published_at IS NULL
                          OR so.available_at IS NULL
                          OR so.recorded_at IS NULL
                          OR so.source_published_at >= %s
                          OR so.available_at >= %s
                          OR so.recorded_at >= %s
                          OR fsl.source_published_at >= %s
                          OR fsl.retrieved_at >= %s
                          OR fsl.crosswalk_version_id IS NULL
                   )
            FROM feature_snapshot_links fsl
            LEFT JOIN source_observations so ON so.id=fsl.source_observation_id
            WHERE fsl.feature_snapshot_id=%s
            """,
            (
                EXPECTED_OPENPLAY_RIGHTS_APPROVAL_ID,
                EXPECTED_OPENPLAY_PROVIDER,
                EXPECTED_OPENPLAY_SOURCE_ID,
                EXPECTED_OPENPLAY_RIGHTS_APPROVAL_ID,
                _aware(item["forecast_cutoff_at"]),
                _aware(item["forecast_cutoff_at"]),
                _aware(item["forecast_cutoff_at"]),
                _aware(item["forecast_cutoff_at"]),
                _aware(item["forecast_cutoff_at"]),
                item["feature_snapshot_id"],
            ),
        ).fetchone()
        if (
            int(link_counts[0])!=item["feature_count"]
            or int(link_counts[1])!=item["feature_count"]
            or int(link_counts[2])!=0
        ):
            raise ValueError("V2_FEATURE_SNAPSHOT_LINK_ROWS_INCOMPLETE")
        eligibility=conn.execute(
            """
            SELECT eligibility_event_id,eligibility_status,evidence_sha256,recorded_at
            FROM feature_snapshot_eligibility_events
            WHERE feature_snapshot_id=%s AND eligibility_status='ELIGIBLE'
              AND evidence_sha256=%s
            ORDER BY recorded_at DESC,eligibility_event_id DESC LIMIT 1
            """,
            (item["feature_snapshot_id"],item["eligibility_evidence_sha256"]),
        ).fetchone()
        if (
            eligibility is None or eligibility[1]!="ELIGIBLE"
            or eligibility[3] > _aware(item["forecast_cutoff_at"])
        ):
            raise ValueError("V2_FEATURE_ELIGIBILITY_EVENT_INVALID_OR_LATE")
        link={
            "ledger_id":event[0],
            "prediction_sequence":int(event[1]),
            "prediction_event_sha256":str(event[2]).strip(),
            "feature_snapshot_id":item["feature_snapshot_id"],
            "eligibility_event_id":int(eligibility[0]),
            "canonical_competition_id":int(snapshot[5]),
            "canonical_home_team_id":int(snapshot[6]),
            "canonical_away_team_id":int(snapshot[7]),
            "provider_competition_id":str(snapshot[8]),
            "provider_home_team_id":str(snapshot[9]),
            "provider_away_team_id":str(snapshot[10]),
            "feature_set_sha256":item["feature_set_sha256"],
            "eligibility_evidence_sha256":item["eligibility_evidence_sha256"],
            "forecast_evidence_sha256":item["forecast_evidence_sha256"],
            "model_artifact_sha256":item["model_artifact_sha256"],
            "forecast_cutoff_at":_aware(item["forecast_cutoff_at"]),
            "feature_snapshot_cutoff_at":_aware(item["feature_snapshot_cutoff_at"]),
            "artifact_run_id":item["artifact_run_id"],
            "forecast_summary_sha256":item["forecast_summary_sha256"],
            "feature_admission_summary_sha256":item["feature_admission_summary_sha256"],
        }
        if link["forecast_cutoff_at"] > event[10].astimezone(timezone.utc):
            raise ValueError("V2_FORECAST_CUTOFF_AFTER_LEDGER_EVENT")
        link["link_sha256"]=_sha256(_canonical({
            key:(value.isoformat() if isinstance(value,datetime) else value)
            for key,value in link.items()
        }))
        resolved.append(link)
    return resolved


def _existing_match(existing, link: dict) -> bool:
    columns=(
        "ledger_id","prediction_sequence","prediction_event_sha256","feature_snapshot_id",
        "eligibility_event_id","canonical_competition_id","canonical_home_team_id",
        "canonical_away_team_id","provider_competition_id","provider_home_team_id",
        "provider_away_team_id","feature_set_sha256","eligibility_evidence_sha256",
        "forecast_evidence_sha256","model_artifact_sha256","forecast_cutoff_at",
        "feature_snapshot_cutoff_at","artifact_run_id","forecast_summary_sha256",
        "feature_admission_summary_sha256","link_sha256",
    )
    return all(
        (str(existing[i]).strip()==str(link[key]).strip()
         if key.endswith("sha256") or key in {"ledger_id","prediction_event_sha256"}
         else existing[i]==link[key])
        for i,key in enumerate(columns)
    )


def link(*, forecast_path: str | Path, admission_path: str | Path, apply: bool=False) -> dict[str, object]:
    dsn=os.environ.get("DATABASE_URL","")
    validate_staging_dsn_target(dsn)
    if urlsplit(dsn).hostname != EXPECTED_HOST:
        raise PermissionError("V2_PREDICTION_FEATURE_LINK_HOST_NOT_ALLOWLISTED")
    if parse_qs(urlsplit(dsn).query).get("sslmode",[""])[0].casefold() not in {"require","verify-ca","verify-full"}:
        raise PermissionError("V2_PREDICTION_FEATURE_LINK_TLS_REQUIRED")
    forecast,admission,forecast_sha,admission_sha=_load_artifacts(forecast_path,admission_path)
    prepared=_prepare_links(forecast,admission,forecast_sha,admission_sha)
    with _connect(dsn,readonly=not apply) as conn:
        table_exists=conn.execute(
            "SELECT to_regclass('public.prediction_feature_snapshot_links') IS NOT NULL"
        ).fetchone()[0]
        if not table_exists:
            raise RuntimeError("V2_PREDICTION_FEATURE_LINK_MIGRATION_NOT_APPLIED")
        resolved=_resolve_links(conn,prepared)
        existing_rows=[]
        for item in resolved:
            existing=conn.execute(
                """
                SELECT ledger_id,prediction_sequence,prediction_event_sha256,
                       feature_snapshot_id,eligibility_event_id,canonical_competition_id,
                       canonical_home_team_id,canonical_away_team_id,provider_competition_id,
                       provider_home_team_id,provider_away_team_id,feature_set_sha256,
                       eligibility_evidence_sha256,forecast_evidence_sha256,
                       model_artifact_sha256,forecast_cutoff_at,feature_snapshot_cutoff_at,
                       artifact_run_id,forecast_summary_sha256,feature_admission_summary_sha256,
                       link_sha256
                FROM prediction_feature_snapshot_links
                WHERE ledger_id=%s AND prediction_sequence=%s
                """,
                (item["ledger_id"],item["prediction_sequence"]),
            ).fetchone()
            existing_rows.append(existing)
            if existing is not None and not _existing_match(existing,item):
                raise RuntimeError("V2_PREDICTION_FEATURE_LINK_IDEMPOTENCY_CONFLICT")
        if not apply:
            return {
                "status":"DRY_RUN_READY",
                "forecasts":len(resolved),
                "already_linked":sum(row is not None for row in existing_rows),
                "new_links":sum(row is None for row in existing_rows),
                "forecast_summary_sha256":forecast_sha,
                "feature_admission_summary_sha256":admission_sha,
                "database":EXPECTED_DATABASE,
                "writes_performed":False,
            }
        if os.environ.get("VELTRIX_ENABLE_PHASE5_V2_PREDICTION_FEATURE_LINKS")!="YES":
            raise PermissionError("V2_PREDICTION_FEATURE_LINK_EXPLICIT_GUARD_REQUIRED")
        for item,row in zip(resolved,existing_rows):
            if row is not None:
                continue
            conn.execute(
                """
                INSERT INTO prediction_feature_snapshot_links(
                    ledger_id,prediction_sequence,prediction_event_sha256,
                    feature_snapshot_id,eligibility_event_id,canonical_competition_id,
                    canonical_home_team_id,canonical_away_team_id,provider_competition_id,
                    provider_home_team_id,provider_away_team_id,feature_set_sha256,
                    eligibility_evidence_sha256,forecast_evidence_sha256,
                    model_artifact_sha256,forecast_cutoff_at,feature_snapshot_cutoff_at,
                    artifact_run_id,forecast_summary_sha256,
                    feature_admission_summary_sha256,link_sha256
                ) VALUES (
                    %(ledger_id)s,%(prediction_sequence)s,%(prediction_event_sha256)s,
                    %(feature_snapshot_id)s,%(eligibility_event_id)s,%(canonical_competition_id)s,
                    %(canonical_home_team_id)s,%(canonical_away_team_id)s,%(provider_competition_id)s,
                    %(provider_home_team_id)s,%(provider_away_team_id)s,%(feature_set_sha256)s,
                    %(eligibility_evidence_sha256)s,%(forecast_evidence_sha256)s,
                    %(model_artifact_sha256)s,%(forecast_cutoff_at)s,%(feature_snapshot_cutoff_at)s,
                    %(artifact_run_id)s,%(forecast_summary_sha256)s,
                    %(feature_admission_summary_sha256)s,%(link_sha256)s
                )
                ON CONFLICT (ledger_id,prediction_sequence) DO NOTHING
                """,
                item,
            )
        conn.commit()

    # Fresh-connection post-commit verification.
    with _connect(dsn,readonly=True) as verify:
        verified=0
        for item in resolved:
            row=verify.execute(
                """
                SELECT link_sha256,feature_snapshot_id,eligibility_event_id,
                       canonical_competition_id,canonical_home_team_id,canonical_away_team_id,
                       provider_competition_id,provider_home_team_id,provider_away_team_id,
                       prediction_event_sha256,feature_set_sha256
                FROM prediction_feature_snapshot_links
                WHERE ledger_id=%s AND prediction_sequence=%s
                """,
                (item["ledger_id"],item["prediction_sequence"]),
            ).fetchone()
            if (
                row is None or str(row[0]).strip()!=item["link_sha256"]
                or int(row[1])!=item["feature_snapshot_id"]
                or int(row[2])!=item["eligibility_event_id"]
                or int(row[3])!=item["canonical_competition_id"]
                or int(row[4])!=item["canonical_home_team_id"]
                or int(row[5])!=item["canonical_away_team_id"]
                or str(row[6])!=item["provider_competition_id"]
                or str(row[7])!=item["provider_home_team_id"]
                or str(row[8])!=item["provider_away_team_id"]
                or str(row[9]).strip()!=item["prediction_event_sha256"]
                or str(row[10]).strip()!=item["feature_set_sha256"]
            ):
                raise RuntimeError("V2_PREDICTION_FEATURE_LINK_POST_COMMIT_VERIFICATION_FAILED")
            verified+=1
    return {
        "status":"PASS_V2_PREDICTION_FEATURE_EVIDENCE_LINKS",
        "forecasts":len(resolved),
        "links_verified":verified,
        "new_links":sum(row is None for row in existing_rows),
        "forecast_summary_sha256":forecast_sha,
        "feature_admission_summary_sha256":admission_sha,
        "artifact_run_id":EXPECTED_ARTIFACT_RUN_ID,
        "fresh_connection_post_commit_verified":True,
        "paper_ledger_events_updated":False,
        "feature_snapshots_updated":False,
        "publication":False,
        "telegram_delivery":False,
        "value_betting":"LOCKED",
    }


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--forecast-summary",required=True)
    parser.add_argument("--feature-admission-summary",required=True)
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    print(json.dumps(link(
        forecast_path=args.forecast_summary,
        admission_path=args.feature_admission_summary,
        apply=args.apply,
    ),sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
