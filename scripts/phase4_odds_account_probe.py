"""Manual no-credit The Odds API account and sport-entitlement probe.

Dry-run is the default and performs no network or database operation.
Execution is limited to GET /v4/sports/?all=true, which the provider documents
as quota-free. Raw response bytes and allowlisted quota headers are persisted
only to the isolated staging database; no raw response artifact is uploaded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, ProviderResponse, SourceApproval,
)
from veltrix_v2.data.postgres import PostgresHistoryStore
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.data.temporal_eligibility import resolve_rights_status
from veltrix_v2.providers.odds_api_v4.transport_contract import (
    RawTransportResponse, validate_transport_response,
)
from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target


PROVIDER = "the_odds_api"
SOURCE_ID = "odds_api_v4"
API_URL = "https://api.the-odds-api.com/v4/sports/"
ACCOUNT_REF = "veltrix-primary-the-odds-api"
APPROVAL_ID = "approval-the-odds-api-v4-owner-authorized-2026-11-14"
EXPECTED_COMPETITIONS = (
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
)
USER_AGENT = "VELTRIX-FOOTBALL-2.0-ACCOUNT-SCOPE-PROBE/1.0"


def _rows_as_dicts(cursor):
    names = [column.name for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _load_approval(dsn: str) -> SourceApproval:
    validate_staging_dsn_target(dsn)
    import psycopg

    with psycopg.connect(dsn, autocommit=False) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        identity = conn.execute("SELECT current_database(),current_user").fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
        rows = _rows_as_dicts(conn.execute(
            """SELECT approval_id,provider,source_id,competition_scope,data_type,status,
                      permitted_uses,commercial_use_allowed,terms_url,terms_version,
                      evidence_uri,evidence_sha256,rights_basis,reviewed_at,reviewer_id,
                      valid_from,valid_until,attribution_required,attribution_text,
                      attribution_url,raw_redistribution_allowed
               FROM source_approvals WHERE approval_id=%s""",
            (APPROVAL_ID,),
        ))
        if len(rows) != 1:
            raise PermissionError("ODDS_API_APPROVAL_NOT_UNIQUE")
        events = _rows_as_dicts(conn.execute(
            """SELECT event_id,approval_id,status,evidence_uri,evidence_sha256,
                      effective_at,recorded_at,reason_code
               FROM source_approval_status_events
               WHERE approval_id=%s ORDER BY effective_at,recorded_at,event_id""",
            (APPROVAL_ID,),
        ))
        if not events:
            raise PermissionError("ODDS_API_APPROVAL_EVENT_MISSING")
        now = datetime.now(timezone.utc)
        row = rows[0]
        resolution = resolve_rights_status(row, events, rights_evaluated_at=now)
        if resolution.reason_code or resolution.status != "APPROVED":
            raise PermissionError(resolution.reason_code or "ODDS_API_RIGHTS_NOT_APPROVED")
        permitted = row["permitted_uses"]
        approval = SourceApproval(
            approval_id=row["approval_id"], provider=row["provider"], source_id=row["source_id"],
            competition_scope=row["competition_scope"], data_type=row["data_type"],
            status=ApprovalStatus(resolution.status),
            permitted_uses=frozenset(DataUsePurpose(value) for value in permitted),
            commercial_use_allowed=bool(row["commercial_use_allowed"]),
            terms_url=row["terms_url"], terms_version=row["terms_version"],
            evidence_uri=row["evidence_uri"], evidence_sha256=row["evidence_sha256"],
            rights_basis=row["rights_basis"], reviewed_at_utc=row["reviewed_at"],
            reviewer_id=row["reviewer_id"], valid_from_utc=row["valid_from"],
            valid_until_utc=row["valid_until"],
            attribution_required=bool(row["attribution_required"]),
            attribution_text=row["attribution_text"], attribution_url=row["attribution_url"],
            raw_redistribution_allowed=bool(row["raw_redistribution_allowed"]),
        )
        for purpose in (DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE):
            decision = evaluate_source_use(approval, purpose, at_utc=now, commercial=True)
            if not decision.allowed:
                raise PermissionError(decision.reason_code)
        return approval


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_sports(api_key: str):
    if not api_key.strip():
        raise ValueError("THE_ODDS_API_KEY_MISSING")
    request = Request(
        API_URL + "?all=true",
        headers={
            "x-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    requested_at = datetime.now(timezone.utc)
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            body = response.read(2_000_001)
            headers_list = list(response.headers.items())
            status = int(response.status)
    except HTTPError as exc:
        raise RuntimeError(f"ODDS_API_HTTP_{exc.code}_NO_RETRY") from None
    except URLError:
        raise RuntimeError("ODDS_API_NETWORK_ERROR_NO_RETRY") from None
    retrieved_at = datetime.now(timezone.utc)
    if len(body) > 2_000_000:
        raise ValueError("ODDS_API_PROBE_RESPONSE_TOO_LARGE")
    if status != 200:
        raise RuntimeError(f"ODDS_API_HTTP_{status}_NO_RETRY")
    selected = {}
    for name, value in headers_list:
        normalized = str(name).strip().lower()
        if normalized in {
            "x-requests-used", "x-requests-remaining", "x-requests-last",
        }:
            if normalized in selected:
                raise ValueError("ODDS_API_DUPLICATE_QUOTA_HEADER")
            selected[normalized] = str(value)
    envelope_decision = validate_transport_response(
        RawTransportResponse(
            status_code=status,
            headers=selected,
            body=body,
            retrieved_at=retrieved_at,
        )
    )
    if not envelope_decision.accepted or envelope_decision.envelope is None:
        raise ValueError(envelope_decision.reason_code)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("ODDS_API_SPORTS_RESPONSE_INVALID_JSON") from None
    if not isinstance(payload, list):
        raise ValueError("ODDS_API_SPORTS_RESPONSE_NOT_LIST")
    keys = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            raise ValueError("ODDS_API_SPORTS_ROW_INVALID")
        key = item["key"].strip()
        if not key or key in keys:
            raise ValueError("ODDS_API_SPORT_KEY_EMPTY_OR_DUPLICATED")
        keys.append(key)
    return requested_at, retrieved_at, body, selected, envelope_decision.envelope, tuple(sorted(keys))


def run_probe(*, api_key: str, staging_dsn: str, persist: bool) -> dict[str, object]:
    if not staging_dsn.strip():
        raise ValueError("VELTRIX_STAGING_DATABASE_URL_MISSING")
    _load_approval(staging_dsn)
    requested_at, retrieved_at, body, quota_headers, envelope, observed = _fetch_sports(api_key)
    response = ProviderResponse(
        provider=PROVIDER,
        source_id=SOURCE_ID,
        endpoint="/v4/sports/",
        request_id=f"{os.getenv('GITHUB_RUN_ID', 'manual')}-sports-all",
        request_params={"all": "true"},
        http_status=200,
        raw_body=body,
        response_headers=quota_headers,
        fetched_at_utc=retrieved_at,
    )
    missing = sorted(set(EXPECTED_COMPETITIONS) - set(observed))
    persisted_response_id = None
    entitlement_observation_id = None
    account_status = "UNVERIFIED"
    if persist:
        validate_staging_dsn_target(staging_dsn)
        import psycopg
        with psycopg.connect(staging_dsn, autocommit=True) as conn:
            identity = conn.execute("SELECT current_database(),current_user").fetchone()
            if identity != ("veltrix_football_staging", "neondb_owner"):
                raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
        store = PostgresHistoryStore(
            lambda: psycopg.connect(staging_dsn),
            allow_writes=True,
            expected_database="veltrix_football_staging",
        )
        persisted_response_id, entitlement_observation_id = store.persist_provider_account_probe(
            response,
            envelope,
            provider_account_ref=ACCOUNT_REF,
            expected_competition_keys=EXPECTED_COMPETITIONS,
            observed_competition_keys=observed,
        )
        account_status = "ACTIVE" if not missing and envelope.quota_evidence.complete else "UNVERIFIED"
    return {
        "status": "ACCOUNT_SCOPE_VERIFIED" if not missing else "ACCOUNT_SCOPE_INCOMPLETE",
        "provider": PROVIDER,
        "source_id": SOURCE_ID,
        "request_cost_credits": 0,
        "requested_at": requested_at.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "response_sha256": response.response_sha256,
        "sports_returned": len(observed),
        "expected_competitions_found": sorted(set(EXPECTED_COMPETITIONS) & set(observed)),
        "expected_competitions_missing": missing,
        "quota_headers_complete": envelope.quota_evidence.complete,
        "quota_requests_used": envelope.quota_evidence.requests_used,
        "quota_requests_remaining": envelope.quota_evidence.requests_remaining,
        "quota_requests_last": envelope.quota_evidence.requests_last,
        "account_status": account_status,
        "plan_code": "UNDISCLOSED",
        "monthly_allowance": None,
        "billing_period": "NOT_ESTABLISHED",
        "persisted": persist,
        "provider_response_id": persisted_response_id,
        "entitlement_observation_id": entitlement_observation_id,
        "markets_and_regions": "NOT_VERIFIED_BY_SPORTS_ENDPOINT",
        "credit_budget_activation": "BLOCKED_PENDING_ACCOUNT_BILLING_EVIDENCE",
        "prediction_publication": False,
        "telegram_delivery": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--persist-staging", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "mode": "DRY_RUN",
            "provider": PROVIDER,
            "endpoint": "/v4/sports/?all=true",
            "documented_cost_credits": 0,
            "would_call_provider": False,
            "would_write_database": False,
            "publication": False,
            "telegram": False,
        }, indent=2))
        return 0
    result = run_probe(
        api_key=os.environ.get("THE_ODDS_API_KEY", ""),
        staging_dsn=os.environ.get("VELTRIX_STAGING_DATABASE_URL", ""),
        persist=args.persist_staging,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
