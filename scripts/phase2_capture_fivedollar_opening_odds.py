"""Manual-only, non-commercial 5Dollar timestamped opening-odds capture.

Captures only Bet365 1X2 opening quotes from GET /v1/fixtures/{id}. Supports
bounded historical lookback and prospective upcoming-fixture windows. Opening
quotes are not current/closing prices and cannot certify CLV. No paid historical
tick endpoint, automatic retries, production writes, publication, Telegram or
schedule activation.
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


def _validate_quota_preflight(
    raw_body: bytes, headers: dict[str, str], *, planned_requests: int,
    checked_at: datetime,
) -> dict:
    if isinstance(planned_requests, bool) or not 0 <= planned_requests <= MAX_FIXTURES:
        raise ValueError("FIVEDOLLAR_QUOTA_PREFLIGHT_REQUEST_PLAN_INVALID")
    try:
        payload = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("FIVEDOLLAR_QUOTA_PREFLIGHT_RESPONSE_INVALID") from None
    if not isinstance(payload, dict) or payload.get("success") != 1:
        raise RuntimeError("FIVEDOLLAR_QUOTA_PREFLIGHT_RESPONSE_INVALID")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("FIVEDOLLAR_QUOTA_PREFLIGHT_STATUS_SCHEMA_INVALID")
    plan = str(data.get("plan") or "").casefold()
    limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}
    try:
        hourly_limit = int(limits.get("rate_limit"))
        burst_per_minute = int(limits.get("burst_per_minute"))
    except (TypeError, ValueError):
        raise RuntimeError("FIVEDOLLAR_QUOTA_PREFLIGHT_PROFILE_INVALID") from None
    if plan != "community":
        raise RuntimeError("FIVEDOLLAR_QUOTA_PREFLIGHT_PLAN_MISMATCH")
    if hourly_limit != 300 or burst_per_minute != 20:
        raise RuntimeError("FIVEDOLLAR_QUOTA_PREFLIGHT_PROFILE_MISMATCH")
    quota_limit = _header_int(headers, "x-ratelimit-limit")
    quota_remaining = _header_int(headers, "x-ratelimit-remaining")
    quota_reset = _header_int(headers, "x-ratelimit-reset")
    if quota_limit != 300 or quota_remaining is None:
        raise RuntimeError("FIVEDOLLAR_QUOTA_PREFLIGHT_HEADERS_INCOMPLETE")
    if quota_remaining < planned_requests + 1:
        raise RuntimeError("FIVEDOLLAR_QUOTA_PREFLIGHT_INSUFFICIENT_HEADROOM")
    return {
        "checked_at": checked_at.astimezone(timezone.utc).isoformat(),
        "plan": plan,
        "rate_limit_hour": hourly_limit,
        "burst_per_minute": burst_per_minute,
        "quota_limit": quota_limit,
        "quota_remaining": quota_remaining,
        "quota_reset": quota_reset,
        "requests_planned": planned_requests,
        "response_sha256": _sha(raw_body),
    }


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


def _capture_window(*, mode: str, lookback_days: int, future_days: int,
                    now: datetime) -> tuple[datetime, datetime]:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("OPENING_ODDS_CAPTURE_TIMEZONE_REQUIRED")
    if mode == "historical":
        if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or not 1 <= lookback_days <= 90 or future_days != 0:
            raise ValueError("OPENING_ODDS_CAPTURE_BOUNDS_INVALID")
        return now - timedelta(days=lookback_days), now
    if mode == "prospective":
        if isinstance(future_days, bool) or not isinstance(future_days, int) or not 1 <= future_days <= 7:
            raise ValueError("OPENING_ODDS_CAPTURE_BOUNDS_INVALID")
        return now, now + timedelta(days=future_days)
    raise ValueError("OPENING_ODDS_CAPTURE_MODE_INVALID")


def _load_targets(connection, *, mode: str, lookback_days: int, future_days: int,
                  limit: int, now: datetime) -> list[dict]:
    window_start, window_end = _capture_window(
        mode=mode, lookback_days=lookback_days, future_days=future_days, now=now
    )
    approval = _load_approval(connection, now)
    scope = [x.strip() for x in approval.competition_scope.split(",") if x.strip()]
    if not scope or "*" in scope:
        raise PermissionError("OPENING_ODDS_COMPETITION_SCOPE_INVALID")
    with connection.cursor() as cur:
        cur.execute("""
            SELECT f.id,f.provider_fixture_id,f.competition_id,f.kickoff_at,
                   f.season_key,x.crosswalk_version_id,x.valid_from,x.valid_until,
                   x.canonical_entity_key,ht.provider_team_id AS provider_home_team_id,
                   at.provider_team_id AS provider_away_team_id,
                   c.provider_competition_id
            FROM fixtures f
            JOIN teams ht ON ht.id=f.home_team_id AND ht.provider=%s
            JOIN teams at ON at.id=f.away_team_id AND at.provider=%s
            JOIN competitions c ON c.id=f.competition_id AND c.provider=%s
            JOIN entity_crosswalk_versions x
              ON x.entity_type='FIXTURE' AND x.provider=f.provider
             AND x.source_id=%s AND x.provider_entity_id=f.provider_fixture_id
             AND x.canonical_entity_key=f.id::text AND x.mapping_status='RESOLVED'
            WHERE f.provider=%s
              AND f.kickoff_at >= %s AND f.kickoff_at < %s
              AND c.provider_competition_id::text = ANY(%s::text[])
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
            PROVIDER, PROVIDER, PROVIDER, SOURCE_ID, PROVIDER,
            window_start, window_end,
            scope, now, now, PROVIDER, SOURCE_ID, limit,
        ))
        rows = cur.fetchall()
        names = [c.name for c in cur.description]
    return [dict(zip(names, row)) for row in rows]


def _validate_fixture_identity(raw_body: bytes, target: dict) -> None:
    try:
        envelope = json.loads(raw_body)
        data = envelope["data"]
        home_id = data["teams"]["home"]["id"]
        away_id = data["teams"]["away"]["id"]
        competition_id = data["league"]["id"]
        kickoff_raw = data["kickoff_utc"]
        kickoff = datetime.fromisoformat(str(kickoff_raw).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("FIVEDOLLAR_ODDS_FIXTURE_IDENTITY_FIELDS_MISSING") from exc
    if not isinstance(data, dict) or str(data.get("id")) != str(target["provider_fixture_id"]):
        raise ValueError("FIVEDOLLAR_ODDS_FIXTURE_ID_MISMATCH")
    if str(home_id) != str(target["provider_home_team_id"]):
        raise ValueError("FIVEDOLLAR_ODDS_HOME_TEAM_ID_MISMATCH")
    if str(away_id) != str(target["provider_away_team_id"]):
        raise ValueError("FIVEDOLLAR_ODDS_AWAY_TEAM_ID_MISMATCH")
    if str(competition_id) != str(target["provider_competition_id"]):
        raise ValueError("FIVEDOLLAR_ODDS_COMPETITION_ID_MISMATCH")
    if kickoff.tzinfo is None or kickoff.utcoffset() is None:
        raise ValueError("FIVEDOLLAR_ODDS_KICKOFF_TIMEZONE_UNTRUSTED")
    if abs((kickoff.astimezone(timezone.utc) - target["kickoff_at"].astimezone(timezone.utc)).total_seconds()) > 60:
        raise ValueError("FIVEDOLLAR_ODDS_KICKOFF_MISMATCH")


def _request_status(api_key: str):
    requested_at = datetime.now(timezone.utc)
    request = Request(
        f"{API_BASE}/status",
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
            raise PermissionError("FIVEDOLLAR_STATUS_ENDPOINT_NOT_ENTITLED") from None
        if exc.code == 429:
            raise RuntimeError("FIVEDOLLAR_STATUS_PREFLIGHT_RATE_LIMITED_NO_RETRY") from None
        raise RuntimeError(f"FIVEDOLLAR_STATUS_PREFLIGHT_HTTP_{exc.code}_NO_RETRY") from None
    except URLError:
        raise RuntimeError("FIVEDOLLAR_STATUS_PREFLIGHT_NETWORK_ERROR_NO_RETRY") from None
    retrieved_at = datetime.now(timezone.utc)
    if status != 200 or not raw:
        raise RuntimeError("FIVEDOLLAR_STATUS_PREFLIGHT_RESPONSE_INVALID")
    return raw, headers, requested_at, retrieved_at, status, time.monotonic()


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
    recorded_at = datetime.now(timezone.utc)
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
            recorded_at,observation.source_timestamp_raw,
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
            output_dir: str | Path, mode: str = "historical",
            future_days: int = 0) -> dict:
    if not 1 <= max_fixtures <= MAX_FIXTURES:
        raise ValueError("OPENING_ODDS_CAPTURE_BOUNDS_INVALID")
    now = datetime.now(timezone.utc)
    window_start, window_end = _capture_window(
        mode=mode, lookback_days=lookback_days, future_days=future_days, now=now
    )
    if not api_key:
        raise RuntimeError("FIVEDOLLAR_API_KEY_REQUIRED")
    validate_staging_dsn_target(dsn)
    import psycopg

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(dsn) as connection:
        identity = connection.execute("SELECT current_database(),current_user").fetchone()
        if identity != (EXPECTED_DATABASE,EXPECTED_ROLE):
            raise PermissionError("OPENING_ODDS_STAGING_TARGET_MISMATCH")
        approval = _load_approval(connection, now)
        targets = _load_targets(
            connection, mode=mode, lookback_days=lookback_days, future_days=future_days,
            limit=max_fixtures, now=now,
        )
        quota_preflight = None
        last_started = None
        if targets:
            preflight_raw, preflight_headers, _, preflight_at, _, last_started = _request_status(api_key)
            quota_preflight = _validate_quota_preflight(
                preflight_raw, preflight_headers,
                planned_requests=len(targets), checked_at=preflight_at,
            )
        target_manifest = [
            {"provider_fixture_id":str(t["provider_fixture_id"]),
             "canonical_fixture_id":str(t["id"]),
             "kickoff_at":t["kickoff_at"].isoformat(),
             "crosswalk_version_id":t["crosswalk_version_id"]}
            for t in targets
        ]
        manifest_body = {
            "provider":PROVIDER,"source_id":SOURCE_ID,"endpoint":"/v1/fixtures/{id}",
            "market":"1x2","bookmaker":"bet365","capture_mode":mode,
            "lookback_days":lookback_days if mode == "historical" else 0,
            "future_days":future_days if mode == "prospective" else 0,
            "window_start_utc":window_start.isoformat(),"window_end_utc":window_end.isoformat(),
            "max_fixtures":max_fixtures,"requested_at":now.isoformat(),
            "commercial_use_allowed":False,"targets":target_manifest,
            "quota_preflight":quota_preflight,
            "fixture_requests_planned":len(targets),
            "provider_requests_planned":len(targets) + int(quota_preflight is not None),
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
            _validate_fixture_identity(raw,target)
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
            "provider":PROVIDER,"source_id":SOURCE_ID,"capture_mode":mode,
            "quote_type":"BET365_1X2_OPENING_ONLY",
            "window_start_utc":window_start.isoformat(),"window_end_utc":window_end.isoformat(),
            "closing_odds_qualified":False,"clv_certified":False,
            "requests_used":len(results),"request_cap":max_fixtures,
            "provider_requests_total":len(results) + int(quota_preflight is not None),
            "quota_preflight":quota_preflight,
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
    parser.add_argument("--mode",choices=("historical","prospective"),default="historical")
    parser.add_argument("--lookback-days",type=int,default=90)
    parser.add_argument("--future-days",type=int,default=0)
    parser.add_argument("--max-fixtures",type=int,default=25)
    parser.add_argument("--out",default="artifacts/5dollar-opening-odds")
    args=parser.parse_args()
    if not args.execute:
        print(_json({
            "status":"DRY_RUN_NO_NETWORK_NO_DATABASE",
            "provider":PROVIDER,"endpoint":"/v1/fixtures/{id}",
            "capture_mode":args.mode,"market":"bet365 1x2 opening only",
            "lookback_days":args.lookback_days if args.mode == "historical" else 0,
            "future_days":args.future_days if args.mode == "prospective" else 0,
            "max_fixtures":args.max_fixtures,"request_spacing_seconds":MIN_REQUEST_INTERVAL_SECONDS,
            "closing_odds_qualified":False,"clv_certified":False,
            "automatic_retries":False,"paid_historical_tick_endpoint":False,
            "commercial_use_allowed":False,
        }))
        return 0
    result=capture(
        dsn=os.getenv("VELTRIX_STAGING_DATABASE_URL",""),
        api_key=os.getenv("FIVEDOLLARFOOTBALL_API_KEY",""),
        lookback_days=args.lookback_days,max_fixtures=args.max_fixtures,output_dir=args.out,
        mode=args.mode,future_days=args.future_days,
    )
    print(_json(result))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
