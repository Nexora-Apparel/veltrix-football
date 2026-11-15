"""Generate a new PIT-certified V2 prospective xG forecast series.

Reads only eligible OpenPlay feature snapshots and exact scheduled 5Dollar
fixture targets. Appends predictions to the staging paper ledger only. No
provider calls, odds inputs, publication, Telegram or schedule activation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from veltrix_v2.ledger.paper_predictions import PaperPrediction
from veltrix_v2.ledger.postgres_store import PostgresPaperLedgerStore
from veltrix_v2.models.openplay_xg_poisson import (
    MODEL_VERSION,
    predict_from_recent_features,
)

EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
EXPECTED_DATABASE = "veltrix_football_staging"
LEDGER_ID = "veltrix-v2-prospective-observed"
OPENPLAY_APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"
FEATURE_BUILD_ID = "veltrix-openplay-feature-admission-v1"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,
                      default=str,allow_nan=False).encode("utf-8")


def _valid_sha(value) -> bool:
    return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value.casefold())


def _aware(value, field):
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"OPENPLAY_FORECAST_{field}_NOT_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _load_candidate_rows(cur, now):
    cur.execute(
        """
        WITH latest_eligibility AS (
            SELECT DISTINCT ON (feature_snapshot_id)
                   feature_snapshot_id,eligibility_status,evidence_sha256,recorded_at
            FROM feature_snapshot_eligibility_events
            ORDER BY feature_snapshot_id,recorded_at DESC,eligibility_event_id DESC
        )
        SELECT DISTINCT ON (f.id) fs.feature_snapshot_id,fs.fixture_id,fs.prediction_cutoff_at,
               fs.feature_set_sha256,le.evidence_sha256,
               f.provider_fixture_id,f.competition_id,f.home_team_id,f.away_team_id,
               f.kickoff_at,c.provider_competition_id,c.name,ht.name,at.name,
               f.source_observation_id,f.source_payload_sha256,
               target_obs.provider,target_obs.source_id,target_obs.entity_type,target_obs.provider_entity_id,
               target_obs.payload_sha256,target_obs.payload,target_obs.source_published_at,
               target_obs.available_at,target_obs.recorded_at,
               target_obs.point_in_time_certifiable,target_obs.source_timestamp_basis,
               target_obs.rights_approval_id,target_obs.provider_response_id,
               target_response.provider,target_response.source_id,target_response.response_sha256
        FROM feature_snapshots fs
        JOIN latest_eligibility le ON le.feature_snapshot_id=fs.feature_snapshot_id
        JOIN fixtures f ON f.id=fs.fixture_id
        JOIN competitions c ON c.id=f.competition_id
        JOIN teams ht ON ht.id=f.home_team_id
        JOIN teams at ON at.id=f.away_team_id
        JOIN source_observations target_obs ON target_obs.id=f.source_observation_id
        JOIN provider_responses target_response ON target_response.id=target_obs.provider_response_id
        WHERE fs.model_build_id=%s
          AND le.eligibility_status='ELIGIBLE'
          AND le.recorded_at<=%s
          AND fs.prediction_cutoff_at<=%s
          AND f.provider='5DollarFootballAPI'
          AND f.status='SCHEDULED'
          AND f.kickoff_at>%s
          AND NOT EXISTS (
              SELECT 1 FROM paper_ledger_events existing_prediction
              WHERE existing_prediction.ledger_id=%s
                AND existing_prediction.fixture_id=('5dollarfootballapi:' || f.provider_fixture_id)
                AND existing_prediction.model_version=%s
                AND existing_prediction.event_type IN ('PREDICTION','SHADOW_PREDICTION')
          )
        ORDER BY f.id,fs.prediction_cutoff_at DESC,fs.feature_snapshot_id DESC
        """,
        (FEATURE_BUILD_ID,now,now,now,LEDGER_ID,MODEL_VERSION),
    )
    return cur.fetchall()


def _load_feature_links(cur, snapshot_id, cutoff_at):
    cur.execute(
        """
        SELECT fsl.feature_key,fsl.feature_value,fsl.source_observation_id,
               fsl.crosswalk_version_id,fsl.source_published_at,fsl.retrieved_at,
               fsl.rights_approval_id,fsl.value_sha256,
               so.provider,so.source_id,so.entity_type,so.provider_entity_id,
               so.payload_sha256,so.available_at,so.recorded_at,
               so.point_in_time_certifiable,so.source_timestamp_basis,
               so.rights_approval_id
        FROM feature_snapshot_links fsl
        JOIN source_observations so ON so.id=fsl.source_observation_id
        WHERE fsl.feature_snapshot_id=%s AND fsl.feature_status='PRESENT'
        ORDER BY fsl.feature_key
        """,
        (snapshot_id,),
    )
    links=cur.fetchall()
    if not links:
        raise ValueError("OPENPLAY_FORECAST_FEATURE_LINKS_MISSING")
    home=[];away=[];training={}
    for row in links:
        (key,value,obs_id,crosswalk_id,published,retrieved,link_rights,value_hash,
         provider,source_id,entity_type,provider_id,payload_hash,available,recorded,
         pit,timestamp_basis,obs_rights)=row
        if isinstance(value,str):
            value=json.loads(value)
        if not isinstance(value,dict) or _sha(_canonical(value))!=str(value_hash).strip():
            raise ValueError("OPENPLAY_FORECAST_FEATURE_LINK_HASH_MISMATCH")
        if (provider!="OpenPlay / WhoScored / Opta" or source_id!="openplay-data-v0.1.0"
            or entity_type!="match_result_snapshot" or str(provider_id)!=str(value.get("provider_match_id"))
            or str(payload_hash).strip()!=value.get("source_observation_payload_sha256")
            or pit is not True or timestamp_basis!="documented_guarantee"
            or link_rights!=OPENPLAY_APPROVAL_ID or obs_rights!=OPENPLAY_APPROVAL_ID
            or published is None or available is None or recorded is None
            or published>=cutoff_at or available>=cutoff_at or recorded>=cutoff_at
            or retrieved is None or retrieved!=recorded):
            raise ValueError("OPENPLAY_FORECAST_FEATURE_SOURCE_NOT_PIT_ELIGIBLE")
        if key.startswith("home."):
            home.append(value)
        elif key.startswith("away."):
            away.append(value)
        else:
            raise ValueError("OPENPLAY_FORECAST_FEATURE_KEY_INVALID")
        fixture_key=str(value.get("provider_match_id"))
        evidence={
            "fixture_id":fixture_key,
            "available_at":available.astimezone(timezone.utc).isoformat(),
            "recorded_at":recorded.astimezone(timezone.utc).isoformat(),
            "payload_sha256":str(payload_hash).strip(),
            "availability_basis":"openplay_page_saved_at_utc_v1",
            "evidence_class":"PIT_CERTIFIED",
            "rights_approval_id":OPENPLAY_APPROVAL_ID,
        }
        previous=training.get(fixture_key)
        if previous is not None and previous!=evidence:
            raise ValueError("OPENPLAY_FORECAST_DUPLICATE_TRAINING_IDENTITY_CONFLICT")
        training[fixture_key]=evidence
    if not home or not away:
        raise ValueError("OPENPLAY_FORECAST_BOTH_TEAM_FEATURES_REQUIRED")
    return home,away,[training[key] for key in sorted(training)]


def _verify_target(row, now):
    (snapshot_id,fixture_id,cutoff_at,feature_set_sha,eligibility_sha,
     provider_fixture_id,competition_id,home_id,away_id,kickoff_at,
     provider_competition_id,competition_name,home_name,away_name,
     target_obs_id,target_payload_sha,target_obs_provider,target_obs_source,
     target_entity_type,target_provider_id,target_obs_payload_sha,target_payload,
     target_published,target_available,target_recorded,target_pit,target_timestamp_basis,
     target_rights,target_response_id,target_response_provider,target_response_source,
     target_response_hash)=row
    cutoff_at=_aware(cutoff_at,"CUTOFF")
    kickoff_at=_aware(kickoff_at,"KICKOFF")
    if cutoff_at>now or kickoff_at<=now or kickoff_at<=cutoff_at:
        raise ValueError("OPENPLAY_FORECAST_TARGET_NOT_PROSPECTIVE")
    if (not _valid_sha(str(feature_set_sha).strip()) or not _valid_sha(str(eligibility_sha).strip())
        or target_obs_provider!="5DollarFootballAPI" or target_obs_source!="5dollarfootballapi"
        or target_entity_type!="odds_opening_quote"
        or str(target_provider_id)!=str(provider_fixture_id)
        or target_response_provider!="5DollarFootballAPI" or target_response_source!="5dollarfootballapi"
        or not isinstance(target_payload,dict)
        or str(target_response_hash).strip()!=str(target_payload.get("response_sha256","")).strip()
        or str(target_payload_sha).strip()!=str(target_obs_payload_sha).strip()
        or str(target_payload.get("fixture_id"))!=str(provider_fixture_id)
        or target_payload.get("kickoff_at") is None
        or _aware(datetime.fromisoformat(str(target_payload["kickoff_at"]).replace("Z","+00:00")),"TARGET_PAYLOAD_KICKOFF")!=kickoff_at
        or target_pit is not True or target_timestamp_basis!="provider_timestamp"
        or target_published is None or target_available is None or target_recorded is None
        or target_published>cutoff_at or target_available>cutoff_at or target_recorded>cutoff_at
        or not isinstance(target_rights,str) or not target_rights.strip()
        or not _valid_sha(str(target_obs_payload_sha).strip())
        or not _valid_sha(str(target_payload.get("original_target_manifest_sha256","")))
        or not _valid_sha(str(target_payload.get("original_target_response_sha256","")))):
        raise ValueError("OPENPLAY_FORECAST_TARGET_PROVENANCE_INVALID")
    return {
        "snapshot_id":int(snapshot_id),"fixture_id":f"5dollarfootballapi:{provider_fixture_id}",
        "competition_id":str(competition_id),"home_team_id":str(home_id),"away_team_id":str(away_id),
        "kickoff_at":kickoff_at,"cutoff_at":cutoff_at,"provider_fixture_id":str(provider_fixture_id),
        "provider_competition_id":str(provider_competition_id),
        "competition":competition_name,"home_team":home_name,"away_team":away_name,
        "target_payload_sha256":str(target_obs_payload_sha).strip(),
        "target_response_sha256":str(target_payload["original_target_response_sha256"]),
        "target_manifest_sha256":str(target_payload["original_target_manifest_sha256"]),
        "target_rights_approval_id":str(target_rights),
        "feature_set_sha256":str(feature_set_sha).strip(),
        "eligibility_evidence_sha256":str(eligibility_sha).strip(),
    }


def _build_prediction(target, model, training, model_sha, forecasted_at):
    recorded_at=forecasted_at
    evidence_body={
        "model_version":MODEL_VERSION,"model_artifact_sha256":model_sha,
        "formula_version":model.formula_version,
        "fixture_id":target["fixture_id"],"kickoff_at":target["kickoff_at"].isoformat(),
        "prediction_cutoff_at":target["cutoff_at"].isoformat(),
        "feature_snapshot_id":target["snapshot_id"],
        "feature_set_sha256":target["feature_set_sha256"],
        "eligibility_evidence_sha256":target["eligibility_evidence_sha256"],
        "expected_home_goals":model.expected_home_goals,
        "expected_away_goals":model.expected_away_goals,
        "home_sample_count":model.home_sample_count,
        "away_sample_count":model.away_sample_count,
        "market_probabilities":{
            "1X2":{"home":model.home_win,"draw":model.draw,"away":model.away_win},
            "BTTS":{"yes":model.btts_yes,"no":1.0-model.btts_yes},
            "TOTALS_2_5":{"over":model.over_2_5,"under":1.0-model.over_2_5},
        },
        "training_observations":training,
        "target_response_sha256":target["target_response_sha256"],
        "target_manifest_sha256":target["target_manifest_sha256"],
    }
    evidence_sha=_sha(_canonical(evidence_body))
    prediction=PaperPrediction(
        fixture_id=target["fixture_id"],
        competition_id=target["competition_id"],
        home_team_id=target["home_team_id"],
        away_team_id=target["away_team_id"],
        kickoff_at=target["kickoff_at"],
        prediction_cutoff_at=target["cutoff_at"],
        forecasted_at=forecasted_at,
        recorded_at=recorded_at,
        model_version=MODEL_VERSION,
        home_probability=model.home_win,
        draw_probability=model.draw,
        away_probability=model.away_win,
        evidence_sha256=evidence_sha,
        point_in_time_certifiable=True,
        evidence_class="PIT_CERTIFIED",
        target_provider="5DollarFootballAPI",
        target_source_id="5dollarfootballapi",
        target_source_fixture_id=target["provider_fixture_id"],
        target_provider_competition_id=target["provider_competition_id"],
        target_payload_sha256=target["target_payload_sha256"],
        target_response_sha256=target["target_response_sha256"],
        target_capture_manifest_sha256=target["target_manifest_sha256"],
        market_probabilities=evidence_body["market_probabilities"],
        training_observations=tuple(training),
    )
    detail={
        "fixture_id":target["fixture_id"],"provider_fixture_id":target["provider_fixture_id"],
        "competition":target["competition"],"home_team":target["home_team"],"away_team":target["away_team"],
        "kickoff_at":target["kickoff_at"].isoformat(),"prediction_cutoff_at":target["cutoff_at"].isoformat(),
        "model_version":MODEL_VERSION,"feature_snapshot_id":target["snapshot_id"],
        "feature_set_sha256":target["feature_set_sha256"],
        "expected_home_goals":model.expected_home_goals,"expected_away_goals":model.expected_away_goals,
        "home_sample_count":model.home_sample_count,"away_sample_count":model.away_sample_count,
        "probabilities":evidence_body["market_probabilities"],"evidence_sha256":evidence_sha,
    }
    return prediction,detail



def _verify_target_rights(cur, approval_id: str, now: datetime) -> None:
    cur.execute(
        """
        SELECT status,rights_basis,evidence_sha256,valid_from,valid_until,
               permitted_uses,commercial_use_allowed
        FROM source_approvals WHERE approval_id=%s
        """,
        (approval_id,),
    )
    approval=cur.fetchone()
    permitted={str(value).upper() for value in approval[5]} if approval else set()
    if (approval is None or approval[0]!="APPROVED" or approval[1] not in {"TERMS","WRITTEN_PERMISSION"}
        or approval[3]>now or (approval[4] is not None and approval[4]<=now)
        or not {"COLLECTION","STORAGE","MODEL_TRAINING"} <= permitted
        or approval[6] is not False):
        raise RuntimeError("5DOLLAR_TARGET_RIGHTS_NOT_APPROVED_FOR_MODEL_TRAINING")
    cur.execute(
        """
        SELECT status,effective_at,recorded_at,evidence_sha256
        FROM source_approval_status_events WHERE approval_id=%s
        ORDER BY effective_at DESC,recorded_at DESC,event_id DESC LIMIT 1
        """,
        (approval_id,),
    )
    event=cur.fetchone()
    if (event is None or event[0]!="APPROVED" or event[1]>now or event[2]>now
        or str(event[3]).strip()!=str(approval[2]).strip()):
        raise RuntimeError("5DOLLAR_TARGET_RIGHTS_STATUS_EVENT_INVALID")


def generate(database_url: str, output_path: str | Path) -> dict:
    parsed=urlparse(database_url)
    if (parsed.hostname or "").casefold()!=EXPECTED_HOST:
        raise RuntimeError("OPENPLAY_FORECAST_STAGING_HOST_MISMATCH")
    if parse_qs(parsed.query).get("sslmode",[""])[0].casefold() not in {"require","verify-ca","verify-full"}:
        raise RuntimeError("OPENPLAY_FORECAST_STAGING_TLS_REQUIRED")
    import psycopg

    forecasted_at=datetime.now(timezone.utc)
    model_sha=_sha(Path(__file__).resolve().parents[2].joinpath("veltrix_v2/models/openplay_xg_poisson.py").read_bytes())
    predictions=[];details=[];skipped=[]
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_user")
            if cur.fetchone()!=(EXPECTED_DATABASE,"neondb_owner"):
                raise RuntimeError("OPENPLAY_FORECAST_STAGING_TARGET_MISMATCH")
            cur.execute(
                """
                SELECT status,rights_basis,evidence_sha256,valid_from,valid_until,
                       permitted_uses,commercial_use_allowed,attribution_required,
                       attribution_text,attribution_url,raw_redistribution_allowed
                FROM source_approvals WHERE approval_id=%s
                """,(OPENPLAY_APPROVAL_ID,)
            )
            approval=cur.fetchone()
            if (approval is None or approval[0]!="APPROVED" or approval[1]!="WRITTEN_PERMISSION"
                or approval[3]>forecasted_at or (approval[4] is not None and approval[4]<=forecasted_at)
                or not {"collection","storage","historical_import","internal_analysis","model_training","model_validation","derived_research","cache"}<=set(approval[5])
                or approval[6] is not False or approval[7] is not True
                or approval[8]!="openplay (Noah Bair)" or approval[9]!="https://github.com/nlbair/openplay"
                or approval[10] is not False):
                raise RuntimeError("OPENPLAY_FORECAST_RIGHTS_NOT_ACTIVE")
            cur.execute(
                """
                SELECT status,effective_at,recorded_at,evidence_sha256
                FROM source_approval_status_events WHERE approval_id=%s
                ORDER BY effective_at DESC,recorded_at DESC,event_id DESC LIMIT 1
                """,(OPENPLAY_APPROVAL_ID,)
            )
            event=cur.fetchone()
            if event is None or event[0]!="APPROVED" or event[1]>forecasted_at or event[2]>forecasted_at or str(event[3]).strip()!=str(approval[2]).strip():
                raise RuntimeError("OPENPLAY_FORECAST_RIGHTS_STATUS_EVENT_INVALID")

            cur.execute(
                """
                SELECT count(DISTINCT f.id)
                FROM fixtures f
                WHERE f.provider='5DollarFootballAPI' AND f.status='SCHEDULED'
                  AND f.kickoff_at>%s
                  AND EXISTS (
                    SELECT 1 FROM feature_snapshots fs
                    JOIN feature_snapshot_eligibility_events fee
                      ON fee.feature_snapshot_id=fs.feature_snapshot_id
                    WHERE fs.fixture_id=f.id AND fs.model_build_id=%s
                      AND fee.eligibility_status='ELIGIBLE'
                      AND fs.prediction_cutoff_at<=%s
                  )
                  AND EXISTS (
                    SELECT 1 FROM paper_ledger_events pe
                    WHERE pe.ledger_id=%s
                      AND pe.fixture_id=('5dollarfootballapi:' || f.provider_fixture_id)
                      AND pe.model_version=%s
                      AND pe.event_type IN ('PREDICTION','SHADOW_PREDICTION')
                  )
                """,
                (forecasted_at,FEATURE_BUILD_ID,forecasted_at,LEDGER_ID,MODEL_VERSION),
            )
            already_forecasted=int(cur.fetchone()[0])
            rows=_load_candidate_rows(cur,forecasted_at)
            for row in rows:
                target=_verify_target(row,forecasted_at)
                _verify_target_rights(cur,target["target_rights_approval_id"],forecasted_at)
                home,away,training=_load_feature_links(cur,target["snapshot_id"],target["cutoff_at"])
                model=predict_from_recent_features(home_features=home,away_features=away)
                prediction,detail=_build_prediction(target,model,training,model_sha,forecasted_at)
                predictions.append(prediction);details.append(detail)

    appended=[];duplicates=0
    if predictions:
        with psycopg.connect(database_url) as conn:
            store=PostgresPaperLedgerStore(
                conn,ledger_id=LEDGER_ID,write_enabled=True,environment="staging",
                database_name=EXPECTED_DATABASE,host=parsed.hostname or "",role="neondb_owner",
            )
            appended,duplicates,_=store.append_predictions_idempotent(predictions)

    with psycopg.connect(database_url) as verify:
        store=PostgresPaperLedgerStore(
            verify,ledger_id=LEDGER_ID,write_enabled=False,environment="staging",
            database_name=EXPECTED_DATABASE,host=parsed.hostname or "",role="neondb_owner",
        )
        ledger=store.load()
        by_key={(event.fixture_id,event.model_version):event for event in ledger.events
                if event.event_type in {"PREDICTION","SHADOW_PREDICTION"}}
        verified=[]
        for prediction in predictions:
            event=by_key.get((prediction.fixture_id,prediction.model_version))
            if event is None:
                raise RuntimeError("OPENPLAY_FORECAST_POST_COMMIT_EVENT_MISSING")
            if str(event.payload.get("evidence_sha256","")).strip()!=prediction.evidence_sha256:
                raise RuntimeError("OPENPLAY_FORECAST_EXISTING_EVENT_EVIDENCE_CONFLICT")
            verified.append(event.event_sha256)
        ledger.verify_chain()

    summary={
        "status":("PASS_OPENPLAY_V2_PROSPECTIVE_FORECAST_SERIES" if predictions
                 else "PASS_NO_NEW_OPENPLAY_FORECASTS_ALREADY_RECORDED"),
        "model_version":MODEL_VERSION,"model_artifact_sha256":model_sha,
        "forecast_cutoff_at":forecasted_at.isoformat(),
        "eligible_snapshots_considered":len(rows),
        "forecasts_generated":len(predictions),
        "already_forecasted_fixtures":already_forecasted,
        "ledger_events_appended":len(appended),
        "duplicate_forecasts_skipped":int(duplicates),
        "ledger_chain_verified":True,"fresh_connection_post_commit_verified":True,
        "forecasts":details,"ledger_event_sha256":verified,
        "value_betting":"LOCKED","certification":"NOT_CERTIFIED",
        "publication":False,"telegram_delivery":False,"schedule_activation":False,
        "commercial_use_allowed":False,"monetisation_prohibited":True,
    }
    output=Path(output_path);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    return summary


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="artifacts/openplay-v2-forecasts/summary.json")
    args=parser.parse_args()
    dsn=os.getenv("VELTRIX_STAGING_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not dsn: raise RuntimeError("OPENPLAY_FORECAST_STAGING_DATABASE_URL_REQUIRED")
    result=generate(dsn,args.output)
    print(json.dumps({
        "status":result["status"],"model_version":result["model_version"],
        "forecasts_generated":result["forecasts_generated"],
        "already_forecasted_fixtures":result["already_forecasted_fixtures"],
        "ledger_events_appended":result["ledger_events_appended"],
        "duplicate_forecasts_skipped":result["duplicate_forecasts_skipped"],
        "ledger_chain_verified":result["ledger_chain_verified"],
        "fresh_connection_post_commit_verified":result["fresh_connection_post_commit_verified"],
        "value_betting":result["value_betting"],"publication":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
