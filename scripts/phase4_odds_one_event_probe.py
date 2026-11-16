"""One-event, one-request live Odds API probe; maximum three credits.

The script performs fresh quota-free sports/events discovery, requires an exact
canonical fixture match, then makes at most one event-odds request in the UK
region for h2h, totals and BTTS. No retry, schedule, publication or Telegram.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.phase4_odds_account_probe import (
    ACCOUNT_REF, EXPECTED_COMPETITIONS, _fetch_sports, _load_approval,
)
from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target
from veltrix_v2.data.contracts import ProviderResponse
from veltrix_v2.data.postgres import PostgresHistoryStore
from veltrix_v2.providers.odds_api_v4.budget import CreditBudget
from veltrix_v2.providers.odds_api_v4.orchestrator import (
    CaptureRequest, FixtureBoundary, RightsEvidence, build_manifest, evaluate_preflight,
)
from veltrix_v2.providers.odds_api_v4.parser import parse_event_odds
from veltrix_v2.providers.odds_api_v4.postgres_store import (
    PostgresOddsQuoteStore, QuoteWriteContext,
)
from veltrix_v2.providers.odds_api_v4.state_machine import advance_state
from veltrix_v2.providers.odds_api_v4.transport_contract import (
    RawTransportResponse, validate_transport_response,
)

PROVIDER = "the_odds_api"
SOURCE_ID = "odds_api_v4"
SPORT = "soccer_epl"
REGION = "uk"
MARKETS = ("h2h", "totals", "btts")
APPROVAL_ID = "approval-the-odds-api-v4-owner-authorized-2026-11-14"
API_BASE = "https://api.the-odds-api.com/v4"
ENDPOINT_PATH = f"/sports/{SPORT}/events"
MAX_CREDITS = 3
MAX_REQUESTS = 1
TIMEOUT_SECONDS = 15
USER_AGENT = "VELTRIX-FOOTBALL-2.0-ONE-EVENT-ODDS-PROBE/1.0"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("PROVIDER_EVENT_TIMESTAMP_NOT_AWARE")
    return parsed.astimezone(timezone.utc)


def _normalize_team(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return " ".join(normalized.casefold().split())


def select_exact_fixture(fixtures: list[dict], events: list[dict], *, tolerance_seconds: int = 60):
    """Require exact home/away labels and near-identical UTC kickoff; never fuzzy-match."""
    matches = []
    for fixture in fixtures:
        for event in events:
            if not isinstance(event, dict) or event.get("sport_key") != SPORT:
                continue
            if not isinstance(event.get("id"), str) or not event["id"].strip():
                continue
            if _normalize_team(str(fixture["home"])) != _normalize_team(str(event.get("home_team", ""))):
                continue
            if _normalize_team(str(fixture["away"])) != _normalize_team(str(event.get("away_team", ""))):
                continue
            try:
                event_kickoff = _utc(str(event["commence_time"]))
            except (KeyError, TypeError, ValueError):
                continue
            delta = abs((event_kickoff - fixture["kickoff_at"]).total_seconds())
            if delta <= tolerance_seconds:
                matches.append((fixture, event, event_kickoff))
    event_ids = {event["id"] for _, event, _ in matches}
    fixture_ids = {fixture["fixture_id"] for fixture, _, _ in matches}
    if len(matches) != 1 or len(event_ids) != 1 or len(fixture_ids) != 1:
        return None
    return matches[0]


def reconcile_quota(preflight, postflight, *, max_credits: int = MAX_CREDITS):
    """Require exact provider counter deltas and the immutable per-run cap."""
    before = preflight.quota_evidence
    after = postflight.quota_evidence
    if not before.complete or not after.complete:
        raise ValueError("ODDS_API_QUOTA_HEADERS_INCOMPLETE")
    if before.requests_last != 0:
        raise ValueError("ODDS_API_PREFLIGHT_NOT_ZERO_CREDIT")
    if postflight.status_code != 200:
        raise ValueError("ODDS_API_ODDS_RESPONSE_NOT_SUCCESSFUL")
    actual = after.requests_last
    used_delta = after.requests_used - before.requests_used
    remaining_delta = before.requests_remaining - after.requests_remaining
    if actual is None or actual < 0 or actual > max_credits:
        raise ValueError("ODDS_API_REQUEST_COST_OUTSIDE_THREE_CREDIT_CAP")
    if used_delta != actual or remaining_delta != actual:
        raise ValueError("ODDS_API_QUOTA_COUNTER_DELTA_MISMATCH")
    return actual


def _fetch_json(url: str, api_key: str, *, timeout: int = TIMEOUT_SECONDS):
    if not api_key.strip():
        raise ValueError("THE_ODDS_API_KEY_MISSING")
    requested_at = datetime.now(timezone.utc)
    request = Request(
        url,
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            body = response.read(5_000_001)
            headers = {
                str(key).casefold(): str(value)
                for key, value in response.headers.items()
                if str(key).casefold() in {
                    "x-requests-used", "x-requests-remaining", "x-requests-last"
                }
            }
            status = int(response.status)
    except HTTPError as exc:
        raise RuntimeError(f"ODDS_API_HTTP_{exc.code}_NO_RETRY") from None
    except URLError:
        raise RuntimeError("ODDS_API_NETWORK_ERROR_NO_RETRY") from None
    retrieved_at = datetime.now(timezone.utc)
    if len(body) > 5_000_000:
        raise ValueError("ODDS_API_RESPONSE_TOO_LARGE")
    envelope_decision = validate_transport_response(RawTransportResponse(
        status_code=status, headers=headers, body=body, retrieved_at=retrieved_at,
    ))
    if not envelope_decision.accepted or envelope_decision.envelope is None:
        raise ValueError(envelope_decision.reason_code or "ODDS_API_TRANSPORT_INVALID")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("ODDS_API_RESPONSE_INVALID_JSON") from None
    return requested_at, retrieved_at, body, headers, envelope_decision.envelope, payload


def _load_epl_fixtures(dsn: str, cutoff: datetime) -> list[dict]:
    import psycopg
    validate_staging_dsn_target(dsn)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            identity = conn.execute("SELECT current_database(),current_user").fetchone()
            if identity != ("veltrix_football_staging", "neondb_owner"):
                raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
            cur.execute(
                """
                SELECT f.id,f.kickoff_at,ht.name,at.name
                FROM fixtures f
                JOIN competitions c ON c.id=f.competition_id
                JOIN teams ht ON ht.id=f.home_team_id
                JOIN teams at ON at.id=f.away_team_id
                WHERE f.provider='5DollarFootballAPI'
                  AND f.status='SCHEDULED'
                  AND f.kickoff_at>%s
                  AND c.name='England Premier League'
                ORDER BY f.kickoff_at,f.id
                """,
                (cutoff,),
            )
            return [
                {
                    "fixture_id": int(row[0]),
                    "kickoff_at": row[1].astimezone(timezone.utc),
                    "home": row[2],
                    "away": row[3],
                }
                for row in cur.fetchall()
            ]


def _load_rights_evidence(dsn: str, approval) -> RightsEvidence:
    import psycopg
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status,effective_at,recorded_at,evidence_sha256
                FROM source_approval_status_events
                WHERE approval_id=%s
                ORDER BY effective_at DESC,recorded_at DESC,event_id DESC LIMIT 1
                """,
                (approval.approval_id,),
            )
            event = cur.fetchone()
    if not event or event[0] != "APPROVED":
        raise PermissionError("ODDS_API_RIGHTS_STATUS_NOT_APPROVED")
    permitted = tuple(sorted(item.value for item in approval.permitted_uses))
    if not {"COLLECTION", "STORAGE", "BENCHMARKING"}.issubset(set(permitted)):
        raise PermissionError("ODDS_API_BENCHMARKING_RIGHTS_NOT_APPROVED")
    competition_scope = tuple(
        sorted(item.strip() for item in approval.competition_scope.split(",") if item.strip())
    )
    if SPORT not in competition_scope:
        raise PermissionError("ODDS_API_EPL_OUTSIDE_APPROVED_SCOPE")
    return RightsEvidence(
        provider=PROVIDER,
        status=event[0],
        accepted_terms_version=approval.terms_version or "",
        terms_evidence_id=approval.evidence_uri or "",
        approval_evidence_id=approval.approval_id,
        effective_at=event[1],
        recorded_at=event[2],
        valid_until=approval.valid_until_utc,
        competitions=competition_scope,
        markets=MARKETS,
        regions=(REGION,),
        permitted_uses=permitted,
    )


def _append_state_chain(store, capture_request_id: int, request_id: str,
                        transitions: list[tuple[str, datetime, str, str]]):
    previous = None
    current = "PLANNED"
    for sequence, (target, occurred_at, reason, evidence_hash) in enumerate(transitions, 1):
        decision = advance_state(
            request_id=request_id,
            current_state=current,
            target_state=target,
            sequence=sequence,
            occurred_at=occurred_at,
            actor="VELTRIX_ONE_EVENT_ODDS_PROBE",
            reason_code=reason,
            evidence_sha256=evidence_hash,
            previous_event=previous,
        )
        if not decision.allowed or decision.event is None:
            raise RuntimeError(decision.reason_code)
        store.append_capture_state_event(capture_request_id, decision.event)
        previous = decision.event
        current = target


def _persist_event_crosswalk(dsn: str, *, response_id: int, response_hash: str,
                             endpoint: str, event: dict, fixture: dict,
                             retrieved_at: datetime, approval_id: str) -> int:
    import psycopg
    from psycopg.types.json import Jsonb

    identity_payload = {
        "event_id": event["id"],
        "sport_key": SPORT,
        "home_team": event["home_team"],
        "away_team": event["away_team"],
        "commence_time": event["commence_time"],
        "canonical_fixture_id": fixture["fixture_id"],
        "provider_response_sha256": response_hash,
    }
    canonical = json.dumps(
        identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    payload_hash = hashlib.sha256(canonical).hexdigest()
    with psycopg.connect(dsn) as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO source_observations(
                    provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                    retrieved_at,payload,source_id,data_type,source_event_time,
                    available_at,availability_basis,rights_approval_id,schema_version,
                    provider_response_id,point_in_time_certifiable,source_timestamp_basis
                ) VALUES (
                    'the_odds_api',%s,'odds_event',%s,%s,%s,%s::jsonb,
                    'odds_api_v4','odds_quote',%s,%s,'provider_response_retrieved',
                    %s,'1',%s,FALSE,'unknown'
                )
                ON CONFLICT(provider,endpoint,entity_type,provider_entity_id,payload_sha256)
                DO NOTHING
                RETURNING id
                """,
                (
                    endpoint,event["id"],payload_hash,retrieved_at,
                    json.dumps(identity_payload,sort_keys=True,separators=(",",":")),
                    fixture["kickoff_at"],retrieved_at,approval_id,response_id,
                ),
            )
            row = cur.fetchone()
            if row:
                observation_id = int(row[0])
            else:
                cur.execute(
                    """
                    SELECT id,provider_response_id,rights_approval_id
                    FROM source_observations
                    WHERE provider='the_odds_api' AND endpoint=%s AND entity_type='odds_event'
                      AND provider_entity_id=%s AND payload_sha256=%s
                    """,
                    (endpoint,event["id"],payload_hash),
                )
                existing = cur.fetchone()
                if not existing or int(existing[1]) != response_id or existing[2] != approval_id:
                    raise RuntimeError("ODDS_EVENT_OBSERVATION_IDEMPOTENCY_CONFLICT")
                observation_id = int(existing[0])

            cur.execute(
                """
                SELECT crosswalk_version_id,canonical_entity_key,mapping_status
                FROM entity_crosswalk_versions
                WHERE provider='the_odds_api' AND source_id='odds_api_v4'
                  AND entity_type='FIXTURE' AND provider_entity_id=%s
                ORDER BY mapping_version DESC LIMIT 1
                """,
                (event["id"],),
            )
            existing_map = cur.fetchone()
            if existing_map:
                if existing_map[1] != str(fixture["fixture_id"]) or existing_map[2] != "RESOLVED":
                    raise RuntimeError("ODDS_EVENT_CROSSWALK_CONFLICT")
                return int(existing_map[0])

            cur.execute(
                """
                INSERT INTO entity_crosswalk_versions(
                    entity_type,provider,source_id,provider_entity_id,
                    canonical_entity_key,mapping_version,mapping_status,mapping_method,
                    confidence,reviewer_id,valid_from,evidence_observation_id,
                    decision_reason,recorded_at
                ) VALUES (
                    'FIXTURE','the_odds_api','odds_api_v4',%s,%s,1,'RESOLVED',
                    'EXACT_NAME_AND_KICKOFF',1.0,'VELTRIX_STRICT_AUTOMATED_MATCHER',
                    %s,%s,
                    'Exact home/away labels and kickoff matched one canonical upcoming fixture',
                    %s
                ) RETURNING crosswalk_version_id
                """,
                (event["id"],str(fixture["fixture_id"]),retrieved_at,observation_id,
                 datetime.now(timezone.utc)),
            )
            return int(cur.fetchone()[0])


def run_probe(*, api_key: str, staging_dsn: str, run_id: str) -> dict[str, object]:
    if not api_key.strip():
        raise ValueError("THE_ODDS_API_KEY_MISSING")
    if not staging_dsn.strip():
        raise ValueError("VELTRIX_STAGING_DATABASE_URL_MISSING")
    validate_staging_dsn_target(staging_dsn)

    # Rights are checked before any provider request.
    approval = _load_approval(staging_dsn)
    rights = _load_rights_evidence(staging_dsn, approval)
    if approval.approval_id != APPROVAL_ID:
        raise PermissionError("ODDS_API_APPROVAL_ID_MISMATCH")

    # Fresh quota-free sports catalogue probe; persisted as account evidence.
    account = __import__("scripts.phase4_odds_account_probe", fromlist=["run_probe"]).run_probe(
        api_key=api_key, staging_dsn=staging_dsn, persist=True
    )
    if (
        account["status"] != "ACCOUNT_SCOPE_AND_ZERO_CREDIT_VERIFIED"
        or account["quota_headers_complete"] is not True
        or account["quota_requests_last"] != 0
        or account["expected_competitions_missing"]
        or not isinstance(account["quota_requests_remaining"], int)
    ):
        return {
            "status":"BLOCKED_FRESH_QUOTA_PREFLIGHT",
            "odds_request_dispatched":False,
            "account_probe":account,
        }

    cutoff = datetime.now(timezone.utc)
    fixtures = _load_epl_fixtures(staging_dsn, cutoff)
    if not fixtures:
        return {"status":"BLOCKED_NO_UPCOMING_EPL_FIXTURES","odds_request_dispatched":False}

    events_url = f"{API_BASE}{ENDPOINT_PATH}?dateFormat=iso"
    _, events_retrieved, events_body, _, events_envelope, events_payload = _fetch_json(events_url, api_key)
    if (
        not isinstance(events_payload, list)
        or not events_envelope.quota_evidence.complete
        or events_envelope.quota_evidence.requests_last != 0
        or events_envelope.quota_evidence.requests_used != account["quota_requests_used"]
        or events_envelope.quota_evidence.requests_remaining != account["quota_requests_remaining"]
    ):
        return {
            "status":"BLOCKED_EVENT_DISCOVERY_QUOTA_MISMATCH",
            "odds_request_dispatched":False,
            "events_response_sha256":hashlib.sha256(events_body).hexdigest(),
        }

    selected = select_exact_fixture(fixtures, events_payload)
    if selected is None:
        return {
            "status":"BLOCKED_NO_UNAMBIGUOUS_EXACT_EVENT_MATCH",
            "odds_request_dispatched":False,
            "sport_key":SPORT,
            "canonical_epl_fixtures_considered":len(fixtures),
            "provider_events_returned":len(events_payload),
            "events_response_sha256":hashlib.sha256(events_body).hexdigest(),
            "matching_policy":"exact normalized home/away labels and kickoff within 60 seconds; no aliases or fuzzy matching",
        }
    fixture, event, provider_event_kickoff = selected
    kickoff = fixture["kickoff_at"]

    rights_at = datetime.now(timezone.utc)
    created_at = datetime.now(timezone.utc)
    request_id = f"{run_id}-epl-one-event-odds"
    request = CaptureRequest(
        request_id=request_id,
        run_id=str(run_id),
        provider=PROVIDER,
        api_version="v4",
        endpoint_class="event_odds",
        sport_key=SPORT,
        competition_keys=(SPORT,),
        fixture_boundaries=(FixtureBoundary(
            fixture_id=str(fixture["fixture_id"]),
            provider_event_id=event["id"],
            prediction_cutoff_at=created_at,
            kickoff_at=kickoff,
        ),),
        markets=MARKETS,
        regions=(REGION,),
        prediction_use="BENCHMARKING",
        expected_terms_version=approval.terms_version,
        rights_evaluated_at=rights_at,
        created_at=created_at,
        max_attempts=1,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    manifest = build_manifest(request)
    decision = evaluate_preflight(
        manifest,
        rights,
        CreditBudget(
            monthly_allowance=None,
            provider_remaining=int(account["quota_requests_remaining"]),
            monthly_hard_cap=None,
            per_run_hard_cap=MAX_CREDITS,
            month_committed=0,
            run_committed=0,
        ),
        {str(fixture["fixture_id"]):event["id"]},
    )
    if not decision.allowed or decision.estimated_credits != MAX_CREDITS:
        return {
            "status":"BLOCKED_PREFLIGHT",
            "odds_request_dispatched":False,
            "reason_codes":list(decision.reason_codes),
            "estimated_credits":decision.estimated_credits,
        }

    store = PostgresHistoryStore(
        lambda: __import__("psycopg").connect(staging_dsn),
        allow_writes=True,
        expected_database="veltrix_football_staging",
    )
    manifest_id = store.persist_capture_manifest(manifest)
    endpoint = f"{API_BASE}{ENDPOINT_PATH}/{event['id']}/odds"
    request_url = endpoint + "?regions=uk&markets=h2h%2Ctotals%2Cbtts&dateFormat=iso&oddsFormat=decimal"
    requested_at, retrieved_at, raw_body, quota_headers, envelope, payload = _fetch_json(request_url, api_key)

    response = ProviderResponse(
        provider=PROVIDER,
        source_id=SOURCE_ID,
        endpoint=f"{ENDPOINT_PATH}/{event['id']}/odds",
        request_id=request_id,
        request_params={
            "regions":REGION,
            "markets":",".join(MARKETS),
            "dateFormat":"iso",
            "oddsFormat":"decimal",
            "event_id":event["id"],
        },
        http_status=200,
        raw_body=raw_body,
        response_headers=quota_headers,
        fetched_at_utc=retrieved_at,
    )
    response_id = store.persist_provider_response(response)
    capture_request_id = store.persist_capture_request(
        capture_manifest_id=manifest_id,
        manifest=manifest,
        endpoint=endpoint,
        attempt_number=1,
        requested_at=requested_at,
        outcome="RESPONSE",
        response_id=response_id,
    )

    # Reconcile the single provider request before parsing or quote admission.
    actual_credits = reconcile_quota(
        _sports_envelope_from_account(account, envelope),
        envelope,
        max_credits=MAX_CREDITS,
    )

    # Validate response identity before any normalized quote persistence.
    event_payload = payload if isinstance(payload, dict) else None
    try:
        response_kickoff = _utc(str(event_payload.get("commence_time"))) if event_payload else None
    except ValueError:
        response_kickoff = None
    identity_valid = bool(
        event_payload
        and event_payload.get("id") == event["id"]
        and _normalize_team(str(event_payload.get("home_team",""))) == _normalize_team(fixture["home"])
        and _normalize_team(str(event_payload.get("away_team",""))) == _normalize_team(fixture["away"])
        and response_kickoff is not None
        and abs((response_kickoff - provider_event_kickoff).total_seconds()) <= 1
    )
    if not identity_valid:
        now = datetime.now(timezone.utc)
        _append_state_chain(store,capture_request_id,request_id,[
            ("PREFLIGHT_APPROVED",created_at,"RIGHTS_QUOTA_AND_EXACT_EVENT_PREFLIGHT",manifest.manifest_sha256),
            ("CREDIT_RESERVED",requested_at,"THREE_CREDIT_ONE_REQUEST_LOCAL_GUARD",manifest.manifest_sha256),
            ("REQUEST_STARTED",requested_at,"SINGLE_EVENT_ODDS_REQUEST_DISPATCHED",manifest.request_fingerprint),
            ("RESPONSE_RECEIVED",retrieved_at,"HTTP_200_RAW_RESPONSE_PERSISTED",response.response_sha256),
            ("PARSE_REJECTED",retrieved_at,"ODDS_RESPONSE_EVENT_IDENTITY_MISMATCH",response.response_sha256),
            ("QUOTA_RECONCILED",retrieved_at,"PROVIDER_QUOTA_COUNTERS_MATCHED_EXACTLY",response.response_sha256),
            ("COMMITTED",now,"INVALID_EVENT_RESPONSE_RETAINED_WITHOUT_QUOTES",response.response_sha256),
        ])
        return {
            "status":"PARSE_REJECTED_EVENT_IDENTITY_MISMATCH",
            "odds_request_dispatched":True,
            "actual_credits":actual_credits,
            "quota_remaining":envelope.quota_evidence.requests_remaining,
            "response_sha256":response.response_sha256,
            "provider_response_id":response_id,
            "capture_request_id":capture_request_id,
            "quotes_persisted":0,
        }

    parsed = parse_event_odds(raw_body,sport_key=SPORT,event_id=event["id"],retrieved_at=retrieved_at)
    timestamped = tuple(
        quote for quote in parsed.observations
        if quote.eligible_timestamp and quote.source_published_at is not None
        and quote.source_published_at <= quote.retrieved_at
        and quote.retrieved_at < kickoff
        and quote.source_published_at < kickoff
    )
    missing_timestamps = len(parsed.observations) - len(timestamped)
    from dataclasses import replace
    parsed_eligible = replace(parsed,observations=timestamped)

    crosswalk_id = None
    write_result = None
    if timestamped:
        crosswalk_id = _persist_event_crosswalk(
            staging_dsn,
            response_id=response_id,
            response_hash=response.response_sha256,
            endpoint=response.endpoint,
            event=event_payload,
            fixture=fixture,
            retrieved_at=retrieved_at,
            approval_id=approval.approval_id,
        )
        write_result = PostgresOddsQuoteStore(
            lambda: __import__("psycopg").connect(staging_dsn)
        ).write_capture(
            parsed_eligible,
            QuoteWriteContext(
                fixture_id=fixture["fixture_id"],
                crosswalk_version_id=crosswalk_id,
                response_id=response_id,
                capture_request_id=capture_request_id,
                rights_approval_id=approval.approval_id,
                raw_response=raw_body,
                prediction_cutoff_at=None,
                kickoff_at=kickoff,
            ),
        )
        if write_result.rejected:
            now = datetime.now(timezone.utc)
            _append_state_chain(store,capture_request_id,request_id,[
                ("PREFLIGHT_APPROVED",created_at,"RIGHTS_QUOTA_AND_EXACT_EVENT_PREFLIGHT",manifest.manifest_sha256),
                ("CREDIT_RESERVED",requested_at,"THREE_CREDIT_ONE_REQUEST_LOCAL_GUARD",manifest.manifest_sha256),
                ("REQUEST_STARTED",requested_at,"SINGLE_EVENT_ODDS_REQUEST_DISPATCHED",manifest.request_fingerprint),
                ("RESPONSE_RECEIVED",retrieved_at,"HTTP_200_RAW_RESPONSE_PERSISTED",response.response_sha256),
                ("PARSE_REJECTED",now,"QUOTE_ADMISSION_REJECTED_CAPTURE_AS_A_UNIT",response.response_sha256),
                ("QUOTA_RECONCILED",now,"PROVIDER_QUOTA_COUNTERS_MATCHED_EXACTLY",response.response_sha256),
                ("COMMITTED",now,"REJECTED_QUOTES_NOT_PERSISTED_RAW_EVIDENCE_RETAINED",response.response_sha256),
            ])
            return {
                "status":"PARSE_REJECTED_QUOTE_ADMISSION",
                "odds_request_dispatched":True,
                "actual_credits":actual_credits,
                "response_sha256":response.response_sha256,
                "provider_response_id":response_id,
                "capture_request_id":capture_request_id,
                "quotes_persisted":0,
                "quotes_rejected":write_result.rejected,
            }

    # Verify the exact response/request linkage and committed quote count.
    import psycopg
    with psycopg.connect(staging_dsn) as conn:
        identity = conn.execute("SELECT current_database(),current_user").fetchone()
        if identity != ("veltrix_football_staging","neondb_owner"):
            raise PermissionError("STAGING_POST_COMMIT_TARGET_MISMATCH")
        persisted_quotes = conn.execute(
            "SELECT count(*) FROM odds_quote_observations WHERE response_id=%s AND capture_request_id=%s",
            (response_id,capture_request_id),
        ).fetchone()[0]
    expected_quotes = write_result.inserted + write_result.duplicates if write_result else 0
    if int(persisted_quotes) != expected_quotes:
        raise RuntimeError("ODDS_QUOTE_POST_COMMIT_VERIFICATION_FAILED")

    now = datetime.now(timezone.utc)
    _append_state_chain(store,capture_request_id,request_id,[
        ("PREFLIGHT_APPROVED",created_at,"RIGHTS_QUOTA_AND_EXACT_EVENT_PREFLIGHT",manifest.manifest_sha256),
        ("CREDIT_RESERVED",requested_at,"THREE_CREDIT_ONE_REQUEST_LOCAL_GUARD",manifest.manifest_sha256),
        ("REQUEST_STARTED",requested_at,"SINGLE_EVENT_ODDS_REQUEST_DISPATCHED",manifest.request_fingerprint),
        ("RESPONSE_RECEIVED",retrieved_at,"HTTP_200_RAW_RESPONSE_PERSISTED",response.response_sha256),
        ("PARSED",now,"EVENT_IDENTITY_AND_TIMESTAMPED_MARKETS_PARSED",response.response_sha256),
        ("QUOTA_RECONCILED",now,"PROVIDER_QUOTA_COUNTERS_MATCHED_EXACTLY",hashlib.sha256(
            f"{account['quota_requests_used']}:{account['quota_requests_remaining']}:{actual_credits}:"
            f"{envelope.quota_evidence.requests_used}:{envelope.quota_evidence.requests_remaining}".encode()
        ).hexdigest()),
        ("COMMITTED",now,"STAGING_QUOTES_POST_COMMIT_VERIFIED",response.response_sha256),
    ])
    return {
        "status":"PASS_ONE_EVENT_ODDS_CAPTURE" if expected_quotes else "PASS_CAPTURE_NO_TIMESTAMPED_QUOTES",
        "provider":"the_odds_api",
        "sport_key":SPORT,
        "fixture_id":fixture["fixture_id"],
        "provider_event_id":event["id"],
        "home_team":fixture["home"],
        "away_team":fixture["away"],
        "kickoff_at":kickoff.isoformat(),
        "markets_returned":sorted({quote.market_key for quote in parsed.observations}),
        "bookmaker_count":len({quote.bookmaker_key for quote in parsed.observations}),
        "parsed_quote_count":len(parsed.observations),
        "timestamped_quote_count":len(timestamped),
        "missing_or_invalid_timestamp_count":missing_timestamps,
        "quotes_inserted":write_result.inserted if write_result else 0,
        "quotes_duplicate":write_result.duplicates if write_result else 0,
        "quotes_rejected":write_result.rejected if write_result else 0,
        "actual_credits":actual_credits,
        "quota_remaining":envelope.quota_evidence.requests_remaining,
        "quota_requests_used":envelope.quota_evidence.requests_used,
        "response_sha256":response.response_sha256,
        "provider_response_id":response_id,
        "capture_manifest_id":manifest_id,
        "capture_request_id":capture_request_id,
        "crosswalk_version_id":crosswalk_id,
        "fresh_connection_post_commit_verified":True,
        "publication":False,
        "telegram_delivery":False,
        "schedule_activation":False,
        "value_betting":"LOCKED",
    }


def _sports_envelope_from_account(account, postflight):
    # Reconstruct only the quota fields needed for exact delta reconciliation.
    from types import SimpleNamespace
    quota = SimpleNamespace(
        complete=account["quota_headers_complete"],
        requests_used=account["quota_requests_used"],
        requests_remaining=account["quota_requests_remaining"],
        requests_last=account["quota_requests_last"],
    )
    return SimpleNamespace(quota_evidence=quota)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "mode":"DRY_RUN",
            "provider":PROVIDER,
            "sport_key":SPORT,
            "markets":list(MARKETS),
            "region":REGION,
            "max_credits":MAX_CREDITS,
            "max_credit_requests":MAX_REQUESTS,
            "would_call_odds_endpoint":False,
            "would_write_database":False,
        },indent=2))
        return 0
    result=run_probe(
        api_key=os.environ.get("THE_ODDS_API_KEY",""),
        staging_dsn=os.environ.get("VELTRIX_STAGING_DATABASE_URL",""),
        run_id=os.getenv("GITHUB_RUN_ID","manual"),
    )
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
