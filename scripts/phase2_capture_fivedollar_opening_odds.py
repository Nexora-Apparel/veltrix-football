"""Manual-only, non-commercial 5Dollar timestamped opening-odds capture.

Captures only Bet365 1X2 opening quotes from GET /v1/fixtures/{id}.
No paid historical tick endpoint, no automatic retries, no production writes,
no prediction publication, no Telegram, and no schedule activation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, SourceApproval
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.data.temporal_eligibility import resolve_rights_status
from veltrix_v2.providers.fivedollar_odds_history.fixture_odds_parser import (
    parse_fixture_opening_1x2,
)
from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target

API_BASE = "https://api.5dollarfootballapi.com/v1"
PROVIDER = "5DollarFootballAPI"
SOURCE_ID = "5dollarfootballapi"
APPROVAL_ID = "approval-5dollar-community-odds-quote-noncommercial-2026-11-15"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_ROLE = "neondb_owner"
MAX_FIXTURES = 25
MIN_REQUEST_INTERVAL_SECONDS = 3.1
USER_AGENT = "VELTRIX-FOOTBALL-2.0-OPENING-ODDS-CAPTURE/1.0"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(value: bytes) -> str:
    return sha256(value).hexdigest()


def _header_int(headers: dict[str, str], *names: str) -> int | None:
    lowered = {str(k).lower(): str(v).strip() for k, v in headers.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            try:
                parsed = int(value)
            except ValueError:
                return None
            return parsed if parsed >= 0 else None
    return None


def _load_approval(connection, at: datetime) -> SourceApproval:
    with connection.cursor() as cur:
        cur.execute("""
            SELECT approval_id,provider,source_id,competition_scope,data_type,status,
                   permitted_uses,commercial_use_allowed,terms_url,terms_version,
                   evidence_uri,evidence_sha256,rights_basis,reviewed_at,reviewer_id,
                   valid_from,valid_until,attribution_required,attribution_text,
                   attribution_url,raw_redistribution_allowed
            FROM source_approvals WHERE approval_id=%s
        """, (APPROVAL_ID,))
        rows = cur.fetchall()
        if len(rows) != 1:
            raise PermissionError("OPENING_ODDS_APPROVAL_NOT_UNIQUE")
        names = [c.name for c in cur.description]
        approval_row = dict(zip(names, rows[0]))
        cur.execute("""
            SELECT event_id,approval_id,status,evidence_uri,evidence_sha256,
                   effective_at,recorded_at,reason_code
            FROM source_approval_status_events WHERE approval_id=%s
            ORDER BY effective_at,recorded_at,event_id
        """, (APPROVAL_ID,))
        event_rows = [dict(zip([c.name for c in cur.description], row)) for row in cur.fetchall()]
    resolution = resolve_rights_status(approval_row, event_rows, rights_evaluated_at=at)
    if resolution.status != "APPROVED" or resolution.reason_code:
        raise PermissionError(resolution.reason_code or "OPENING_ODDS_RIGHTS_NOT_APPROVED")
    if approval_row["data_type"] != "odds_quote" or approval_row["commercial_use_allowed"] is not False:
        raise PermissionError("OPENING_ODDS_NONCOMMERCIAL_APPROVAL_REQUIRED")
    permitted = approval_row["permitted_uses"]
    if not isinstance(permitted, (list, tuple)):
        raise PermissionError("OPENING_ODDS_PERMITTED_USES_INVALID")
    approval = SourceApproval(
        approval_id=approval_row["approval_id"], provider=approval_row["provider"],
        source_id=approval_row["source_id"], competition_scope=approval_row["competition_scope"],
        data_type=approval_row["data_type"], status=ApprovalStatus(resolution.status),
        permitted_uses=frozenset(DataUsePurpose(str(x)) for x in permitted),
        commercial_use_allowed=False, terms_url=approval_row["terms_url"],
        terms_version=approval_row["terms_version"], evidence_uri=approval_row["evidence_uri"],
        evidence_sha256=approval_row["evidence_sha256"], rights_basis=approval_row["rights_basis"],
        reviewed_at_utc=approval_row["reviewed_at"], reviewer_id=approval_row["reviewer_id"],
        valid_from_utc=approval_row["valid_from"], valid_until_utc=approval_row["valid_until"],
        attribution_required=approval_row["attribution_required"],
        attribution_text=approval_row["attribution_text"], attribution_url=approval_row["attribution_url"],
        raw_redistribution_allowed=approval_row["raw_redistribution_allowed"],
    )
    for purpose in (DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
                    DataUsePurpose.MODEL_TRAINING, DataUsePurpose.BENCHMARKING):
        decision = evaluate_source_use(approval, purpose, at_utc=at, commercial=False)
        if not decision.allowed:
            raise PermissionError(decision.reason_code)
    return approval


def _load_targets(connection, *, lookback_days: int, limit: int, now: datetime) -> list[dict]:
    approval = _load_approval(connection, now)
    scope = [x.strip() for x in approval.competition_scope.split(",") if x.strip()]
    if not scope or "*" in scope:
        raise PermissionError("OPENING_ODDS_COMPETITION_SCOPE_INVALID")
    with connection.cursor() as cur:
        cur.execute("""
            SELECT f.id,f.provider_fixture_id,f.competition_id,f.kickoff_at,
                   f.season_key,x.crosswalk_version_id,x.valid_from,x.valid_until,
                   x.canonical_entity_key
            FROM fixtures f
            JOIN entity_crosswalk_versions x
              ON x.entity_type='FIXTURE' AND x.provider=f.provider
             AND x.source_id=%s AND x.provider_entity_id=f.provider_fixture_id
             AND x.canonical_entity_key=f.id::text AND x.mapping_status='RESOLVED'
            WHERE f.provider=%s
              AND f.kickoff_at >= %s AND f.kickoff_at < %s
              AND f.competition_id::text = ANY(%s::text[])
              AND x.valid_from <= %s AND (x.valid_until IS NULL OR x.valid_until > %s)
              AND NOT EXISTS (
                SELECT 1 FROM source_observations o
                WHERE o.provider=%s AND o.source_id=%s
                  AND o.entity_type='odds_opening_quote'
                  AND o.provider_entity_id=f.provider_fixture_id
              )
            ORDER BY f.kickoff_at ASC,f.provider_fixture_id
            LIMIT %s
        """, (
            SOURCE_ID, PROVIDER, now - timedelta(days=lookback_days), now,
            scope, now, now, PROVIDER, SOURCE_ID, limit,
        ))
        rows = cur.fetchall()
        names = [c.name for c in cur.description]
    return [dict(zip(names, row)) for row in rows]


def _request_fixture(api_key: str, fixture_id: str, *, last_started: float | None):
    if last_started is not None:
        delay = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_started)
        if delay > 0:
            time.sleep(delay)
    requested_at = datetime.now(timezone.utc)
    request = Request(
        f"{API_BASE}/fixtures/{fixture_id}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read()
            headers = {str(k): str(v) for k, v in response.headers.items()}
            status = int(getattr(response, "status", getattr(response, "code", 200)))
    except HTTPError as exc:
        if exc.code == 401:
            raise PermissionError("FIVEDOLLAR_API_KEY_REJECTED") from None
        if exc.code == 403:
            raise PermissionError("FIVEDOLLAR_ODDS_ENDPOINT_NOT_ENTITLED") from None
        if exc.code == 429:
            raise RuntimeError("FIVEDOLLAR_RATE_LIMITED_NO_RETRY") from None
        raise RuntimeError(f"FIVEDOLLAR_HTTP_{exc.code}_NO_RETRY") from None
    except URLError:
        raise RuntimeError("FIVEDOLLAR_NETWORK_ERROR_NO_RETRY") from None
    retrieved_at = datetime.now(timezone.utc)
    if status != 200 or not raw:
        raise RuntimeError("FIVEDOLLAR_FIXTURE_RESPONSE_INVALID")
    return raw, headers, requested_at, retrieved_at, status, time.monotonic()


def _persist_capture(connection, *, manifest_id: int, target: dict, raw: bytes,
                     headers: dict[str, str], request_id: str, requested_at: datetime,
                     retrieved_at: datetime, http_status: int, parsed, approval: SourceApproval):
    response_hash = _sha(raw)
    safe_headers = {
        str(k).lower(): str(v) for k, v in headers.items()
        if str(k).lower() in {
            "content-type","date","x-ratelimit-limit","x-ratelimit-remaining",
            "x-ratelimit-used","retry-after",
        }
    }
    quota_limit = _header_int(headers, "x-ratelimit-limit")
    quota_remaining = _header_int(headers, "x-ratelimit-remaining")
    quota_used = _header_int(headers, "x-ratelimit-used")
    observation = parsed.observation
    opened_at = observation.opened_at
    point_in_time = bool(observation.eligible_pit and opened_at is not None
                         and opened_at < observation.kickoff_at
                         and opened_at <= retrieved_at)
    payload = {
        "fixture_id": observation.fixture_id,
        "canonical_fixture_id": str(target["id"]),
        "bookmaker": observation.bookmaker_slug,
        "market": observation.market,
        "home_price": str(observation.home_price) if observation.home_price is not None else None,
        "draw_price": str(observation.draw_price) if observation.draw_price is not None else None,
        "away_price": str(observation.away_price) if observation.away_price is not None else None,
        "opened_at": opened_at.isoformat() if opened_at else None,
        "source_timestamp_raw": observation.source_timestamp_raw,
        "retrieved_at": retrieved_at.isoformat(),
        "kickoff_at": observation.kickoff_at.isoformat(),
        "response_sha256": response_hash,
        "diagnostics": [d.code for d in parsed.diagnostics],
        "commercial_use_allowed": False,
        "monetisation_prohibited": True,
    }
    params = {"fixture_id": observation.fixture_id, "endpoint": "/v1/fixtures/{id}",
              "market": "1x2", "bookmaker": "bet365"}
    fingerprint = _sha(_json({
        "provider": PROVIDER, "source_id": SOURCE_ID,
        "endpoint": f"/fixtures/{observation.fixture_id}", "request_id": request_id,
        "request_params": params,
    }).encode())
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO provider_responses(
              provider,source_id,endpoint,request_id,request_params,http_status,
              response_sha256,raw_body,response_headers,quota_limit,quota_remaining,fetched_at
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,%s)
            ON CONFLICT (provider,source_id,request_id,response_sha256) DO NOTHING
            RETURNING id
        """, (PROVIDER,SOURCE_ID,f"/fixtures/{observation.fixture_id}",request_id,
              _json(params),http_status,response_hash,raw,_json(safe_headers),
              quota_limit,quota_remaining,retrieved_at))
        row = cur.fetchone()
        if row:
            response_id = row[0]
        else:
            cur.execute("""
                SELECT id FROM provider_responses
                WHERE provider=%s AND source_id=%s AND request_id=%s AND response_sha256=%s
            """, (PROVIDER,SOURCE_ID,request_id,response_hash))
            response_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO provider_capture_requests(
              capture_manifest_id,provider,source_id,endpoint,request_key,
              request_fingerprint,attempt_number,requested_at,response_id,outcome
            ) VALUES (%s,%s,%s,%s,%s,%s,1,%s,%s,'RESPONSE')
            ON CONFLICT (capture_manifest_id,request_key,attempt_number) DO NOTHING
            RETURNING capture_request_id
        """, (manifest_id,PROVIDER,SOURCE_ID,f"/fixtures/{observation.fixture_id}",
              request_id,fingerprint,requested_at,response_id))
        cur.execute("""
            INSERT INTO source_observations(
              provider,endpoint,entity_type,provider_entity_id,payload_sha256,
              retrieved_at,payload,source_id,data_type,season_key,source_event_time,
              available_at,availability_basis,rights_approval_id,schema_version,
              provider_response_id,point_in_time_certifiable,source_published_at,
              source_effective_at,recorded_at,source_timestamp_raw,source_timestamp_basis
            ) VALUES (
              %s,%s,'odds_opening_quote',%s,%s,%s,%s::jsonb,%s,'odds_quote',%s,%s,
              %s,%s,%s,'5dollar-opening-1x2-v1',%s,%s,%s,NULL,%s,%s,%s
            ) ON CONFLICT (
              provider,endpoint,entity_type,provider_entity_id,payload_sha256
            ) DO NOTHING
            RETURNING id
        """, (
            PROVIDER,f"/fixtures/{observation.fixture_id}",observation.fixture_id,
            response_hash,retrieved_at,_json(payload),SOURCE_ID,target.get("season_key"),
            observation.kickoff_at,opened_at,
            "provider_opening_timestamp" if point_in_time else "unknown",
            approval.approval_id,response_id,point_in_time,opened_at,
            retrieved_at,observation.source_timestamp_raw,
            "provider_timestamp" if opened_at else "unknown",
        ))
        inserted = cur.fetchone() is not None
    return {
        "response_id": response_id, "response_sha256": response_hash,
        "point_in_time_certifiable": point_in_time, "observation_inserted": inserted,
        "quota_remaining": quota_remaining, "quota_used": quota_used,
        "diagnostics": [d.code for d in parsed.diagnostics],
    }


def capture(*, dsn: str, api_key: str, lookback_days: int, max_fixtures: int,
            output_dir: str | Path) -> dict:
    if not api_key:
        raise RuntimeError("FIVEDOLLAR_API_KEY_REQUIRED")
    if not 1 <= lookback_days <= 90 or not 1 <= max_fixtures <= MAX_FIXTURES:
        raise ValueError("OPENING_ODDS_CAPTURE_BOUNDS_INVALID")
    validate_staging_dsn_target(dsn)
    import psycopg

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    with psycopg.connect(dsn) as connection:
        identity = connection.execute("SELECT current_database(),current_user").fetchone()
        if identity != (EXPECTED_DATABASE,EXPECTED_ROLE):
            raise PermissionError("OPENING_ODDS_STAGING_TARGET_MISMATCH")
        approval = _load_approval(connection, now)
        targets = _load_targets(connection, lookback_days=lookback_days, limit=max_fixtures, now=now)
        target_manifest = [
            {"provider_fixture_id":str(t["provider_fixture_id"]),
             "canonical_fixture_id":str(t["id"]),
             "kickoff_at":t["kickoff_at"].isoformat(),
             "crosswalk_version_id":t["crosswalk_version_id"]}
            for t in targets
        ]
        manifest_body = {
            "provider":PROVIDER,"source_id":SOURCE_ID,"endpoint":"/v1/fixtures/{id}",
            "market":"1x2","bookmaker":"bet365","lookback_days":lookback_days,
            "max_fixtures":max_fixtures,"requested_at":now.isoformat(),
            "commercial_use_allowed":False,"targets":target_manifest,
        }
        manifest_sha = _sha(_json(manifest_body).encode())
        manifest_key = f"5dollar-opening-odds:{os.getenv('GITHUB_RUN_ID','manual')}:{manifest_sha}"
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO capture_manifests(manifest_key,manifest_sha256,capture_scope,requests_planned)
                VALUES (%s,%s,%s::jsonb,%s)
                ON CONFLICT (manifest_key) DO NOTHING RETURNING capture_manifest_id
            """, (manifest_key,manifest_sha,_json(manifest_body),len(targets)))
            row = cur.fetchone()
            if row:
                manifest_id = row[0]
            else:
                cur.execute("SELECT capture_manifest_id FROM capture_manifests WHERE manifest_key=%s",(manifest_key,))
                manifest_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO capture_manifest_events(
                  capture_manifest_id,status,event_at,reason_code,evidence_sha256,coverage_summary
                ) VALUES (%s,'RUNNING',%s,'OPENING_ODDS_CAPTURE_STARTED',%s,%s::jsonb)
            """, (manifest_id,now,manifest_sha,_json({"targets_planned":len(targets)})))
        connection.commit()

        results = []
        last_started = None
        for index,target in enumerate(targets):
            with connection.cursor() as cur:
                current_approval = _load_approval(connection, datetime.now(timezone.utc))
            current_approval_decision = evaluate_source_use(
                current_approval,DataUsePurpose.COLLECTION,
                at_utc=datetime.now(timezone.utc),commercial=False,
            )
            if not current_approval_decision.allowed:
                raise PermissionError(current_approval_decision.reason_code)
            fixture_id = str(target["provider_fixture_id"])
            request_id = f"{os.getenv('GITHUB_RUN_ID','manual')}-{fixture_id}-opening-1"
            raw,headers,requested_at,retrieved_at,status,last_started = _request_fixture(
                api_key,fixture_id,last_started=last_started
            )
            parsed = parse_fixture_opening_1x2(
                raw,expected_fixture_id=fixture_id,retrieved_at=retrieved_at,
                kickoff_at=target["kickoff_at"],
            )
            result = _persist_capture(
                connection,manifest_id=manifest_id,target=target,raw=raw,headers=headers,
                request_id=request_id,requested_at=requested_at,retrieved_at=retrieved_at,
                http_status=status,parsed=parsed,approval=current_approval,
            )
            connection.commit()
            results.append(result)
            remaining = len(targets) - index - 1
            if result["quota_remaining"] is not None and result["quota_remaining"] < remaining:
                raise RuntimeError("FIVEDOLLAR_QUOTA_BELOW_REMAINING_CAPTURE_PLAN")
            if result["quota_remaining"] is None and index == 0 and remaining > 0:
                raise RuntimeError("FIVEDOLLAR_QUOTA_HEADERS_MISSING_STOP_AFTER_FIRST_CAPTURE")

        summary = {
            "status":"OPENING_ODDS_CAPTURE_COMPLETE",
            "provider":PROVIDER,"source_id":SOURCE_ID,
            "requests_used":len(results),"request_cap":max_fixtures,
            "quotes_pit_eligible":sum(r["point_in_time_certifiable"] for r in results),
            "quotes_ineligible":sum(not r["point_in_time_certifiable"] for r in results),
            "observations_inserted":sum(r["observation_inserted"] for r in results),
            "duplicate_responses":sum(not r["observation_inserted"] for r in results),
            "quota_remaining_after_last":results[-1]["quota_remaining"] if results else None,
            "commercial_use_allowed":False,"monetisation_prohibited":True,
            "publication":False,"telegram":False,"schedule_activation":False,
        }
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO capture_manifest_events(
                  capture_manifest_id,status,event_at,reason_code,evidence_sha256,coverage_summary
                ) VALUES (%s,'COMPLETED',%s,'OPENING_ODDS_CAPTURE_COMPLETED',%s,%s::jsonb)
            """, (manifest_id,datetime.now(timezone.utc),manifest_sha,_json(summary)))
        connection.commit()
    (output/"summary.json").write_text(_json(summary)+"\n",encoding="utf-8")
    return summary


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--lookback-days",type=int,default=90)
    parser.add_argument("--max-fixtures",type=int,default=25)
    parser.add_argument("--out",default="artifacts/5dollar-opening-odds")
    args=parser.parse_args()
    if not args.execute:
        print(_json({
            "status":"DRY_RUN_NO_NETWORK_NO_DATABASE",
            "provider":PROVIDER,"endpoint":"/v1/fixtures/{id}",
            "market":"bet365 1x2 opening only","lookback_days":args.lookback_days,
            "max_fixtures":args.max_fixtures,"request_spacing_seconds":MIN_REQUEST_INTERVAL_SECONDS,
            "automatic_retries":False,"paid_historical_tick_endpoint":False,
            "commercial_use_allowed":False,
        }))
        return 0
    result=capture(
        dsn=os.getenv("VELTRIX_STAGING_DATABASE_URL",""),
        api_key=os.getenv("FIVEDOLLARFOOTBALL_API_KEY",""),
        lookback_days=args.lookback_days,max_fixtures=args.max_fixtures,output_dir=args.out,
    )
    print(_json(result))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
