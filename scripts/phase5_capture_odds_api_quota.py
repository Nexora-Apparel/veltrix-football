"""Bounded, no-odds-credit The Odds API account/quota evidence capture.

This command calls only GET /v4/sports (discovery endpoint), preserves exact
response bytes and safe quota headers, and writes append-only evidence to the
allowlisted VELTRIX staging database. It never requests bookmaker odds.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, date
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target


API_URL = "https://api.the-odds-api.com/v4/sports"
PROVIDER = "the_odds_api"
SOURCE_ID = "odds_api_v4"
ACCOUNT_REF = "veltrix-primary-the-odds-api"
APPROVAL_ID = "approval-the-odds-api-v4-owner-authorized-2026-11-14"
TERMS_VERSION = "2026-08-31"
TERMS_EVIDENCE_URI = (
    "https://github.com/Nexora-Apparel/veltrix-football/blob/"
    "0385ae567ee03cd5825e12d9ab2cf8741172d0f1/"
    "docs/legal/the-odds-api-authorization-scope-2026-11-14.md"
)
TERMS_EVIDENCE_SHA256 = "17064a94ce6e4e87de4fb2acce44475d96624aa3f8b27748de9bf7124457adfb"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
SAFE_HEADERS = (
    "date", "content-type", "x-requests-used",
    "x-requests-remaining", "x-requests-last",
)


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_headers(headers) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in SAFE_HEADERS:
        value = headers.get(name)
        if value is not None:
            result[name] = str(value).strip()
    return result


def _quota_integer(headers: dict[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None or not value.isdigit():
        return None
    return int(value)


def _next_month_start(observed_at: datetime) -> date:
    if observed_at.month == 12:
        return date(observed_at.year + 1, 1, 1)
    return date(observed_at.year, observed_at.month + 1, 1)


def _fetch() -> tuple[int, bytes, dict[str, str], datetime]:
    key = os.getenv("THE_ODDS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("THE_ODDS_API_KEY_MISSING")
    request = Request(
        API_URL,
        headers={
            "x-api-key": key,
            "Accept": "application/json",
            "User-Agent": "VELTRIX-FOOTBALL-2.0-ODDS-QUOTA-CAPTURE/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            status = int(response.status)
            headers = _safe_headers(response.headers)
    except HTTPError as exc:
        body = exc.read(MAX_RESPONSE_BYTES + 1)
        status = int(exc.code)
        headers = _safe_headers(exc.headers)
    except (URLError, TimeoutError) as exc:
        raise RuntimeError("ODDS_API_QUOTA_PROBE_TRANSPORT_FAILED") from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise RuntimeError("ODDS_API_QUOTA_PROBE_RESPONSE_TOO_LARGE")
    return status, body, headers, datetime.now(timezone.utc)


def _canonical_hash(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _persist(
    *,
    dsn: str,
    status: int,
    body: bytes,
    headers: dict[str, str],
    fetched_at: datetime,
    response_hash: str,
    summary_path: Path,
) -> dict[str, object]:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PSYCOPG3_REQUIRED") from exc

    used = _quota_integer(headers, "x-requests-used")
    remaining = _quota_integer(headers, "x-requests-remaining")
    last_cost = _quota_integer(headers, "x-requests-last")
    quota_valid = (
        used is not None and remaining is not None and last_cost is not None
        and used >= 0 and remaining >= 0 and last_cost >= 0
    )
    monthly_allowance = used + remaining if quota_valid else None
    month_start = date(fetched_at.year, fetched_at.month, 1)
    month_end = _next_month_start(fetched_at)
    payload_is_json = False
    sports_count = 0
    if status == 200:
        try:
            parsed = json.loads(body)
            payload_is_json = isinstance(parsed, list)
            sports_count = len(parsed) if payload_is_json else 0
        except (TypeError, ValueError):
            payload_is_json = False

    evidence_base = {
        "provider": PROVIDER,
        "source_id": SOURCE_ID,
        "provider_account_ref": ACCOUNT_REF,
        "endpoint": "/v4/sports",
        "http_status": status,
        "response_sha256": response_hash,
        "safe_quota_headers": headers,
        "fetched_at": _iso(fetched_at),
        "terms_version": TERMS_VERSION,
        "terms_acceptance_evidence_sha256": TERMS_EVIDENCE_SHA256,
        "rights_approval_id": APPROVAL_ID,
    }
    quota_hash = _canonical_hash({"schema": "veltrix-odds-quota-probe-v1", **evidence_base})
    budget_hash = _canonical_hash({
        "schema": "veltrix-odds-budget-snapshot-v1",
        **evidence_base,
        "monthly_allowance": monthly_allowance,
        "provider_remaining": remaining,
        "monthly_hard_cap": min(400, monthly_allowance) if monthly_allowance else None,
        "per_run_hard_cap": min(15, remaining) if remaining else 1,
        "request_count_cap": 8,
        "valid_for_seconds": 86400,
    })

    with psycopg.connect(dsn, autocommit=False) as connection:
        connection.execute("SET LOCAL statement_timeout = '20000ms'")
        identity = connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")

        approval = connection.execute(
            """
            SELECT a.status, a.terms_version, a.evidence_sha256, a.permitted_uses,
                   e.status, e.evidence_sha256
            FROM source_approvals a
            JOIN LATERAL (
                SELECT status, evidence_sha256
                FROM source_approval_status_events
                WHERE approval_id = a.approval_id
                ORDER BY effective_at DESC, recorded_at DESC, event_id DESC
                LIMIT 1
            ) e ON TRUE
            WHERE a.approval_id = %s
            """,
            (APPROVAL_ID,),
        ).fetchone()
        if (
            approval is None or approval[0] != "APPROVED"
            or approval[1] != TERMS_VERSION or approval[2] != TERMS_EVIDENCE_SHA256
            or approval[4] != "APPROVED" or approval[5] != TERMS_EVIDENCE_SHA256
            or "COLLECTION" not in approval[3]
        ):
            raise PermissionError("ODDS_API_RIGHTS_APPROVAL_NOT_CURRENT")

        account = connection.execute(
            "SELECT metadata FROM provider_accounts WHERE provider = %s",
            (PROVIDER,),
        ).fetchone()
        if account is None or account[0].get("owner_authorization_status") != "CONFIRMED":
            raise PermissionError("ODDS_API_OWNER_AUTHORIZATION_NOT_RECORDED")

        request_id = f"odds-sports-probe-{fetched_at.strftime('%Y%m%dT%H%M%S%fZ')}"
        response_id = connection.execute(
            """
            INSERT INTO provider_responses(
                provider, source_id, endpoint, request_id, request_params,
                http_status, response_sha256, raw_body, response_headers,
                quota_limit, quota_remaining, quota_reset_at, fetched_at
            )
            VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                PROVIDER, SOURCE_ID, "/v4/sports", request_id,
                json.dumps({"auth": "x-api-key-header", "dateFormat": "iso"}),
                status, response_hash, body, json.dumps(headers),
                monthly_allowance, remaining,
                datetime.combine(month_end, datetime.min.time(), tzinfo=timezone.utc)
                if quota_valid else None,
                fetched_at,
            ),
        ).fetchone()[0]

        quota_snapshot_id = None
        budget_snapshot_id = None
        if quota_valid:
            quota_snapshot_id = connection.execute(
                """
                INSERT INTO provider_quota_snapshots(
                    provider, source_id, provider_account_ref,
                    billing_period_start, billing_period_end, provider_response_id,
                    observed_at, raw_quota_headers, requests_used,
                    requests_remaining, requests_last, evidence_sha256, recorded_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                RETURNING quota_snapshot_id
                """,
                (
                    PROVIDER, SOURCE_ID, ACCOUNT_REF, month_start, month_end,
                    response_id, fetched_at, json.dumps(headers),
                    used, remaining, last_cost, quota_hash, fetched_at,
                ),
            ).fetchone()[0]

            monthly_cap = max(1, min(400, monthly_allowance))
            per_run_cap = max(1, min(15, remaining))
            budget_snapshot_id = connection.execute(
                """
                INSERT INTO provider_credit_budget_snapshots(
                    provider, provider_account_ref, billing_period_start,
                    billing_period_end, monthly_allowance, provider_remaining,
                    monthly_hard_cap, per_run_hard_cap, request_count_cap,
                    provider_used, provider_last_cost, observed_at, valid_until,
                    evidence_uri, evidence_sha256, terms_version,
                    terms_acceptance_evidence_uri, terms_acceptance_evidence_sha256,
                    rights_approval_ids, recorded_at
                )
                VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s
                )
                RETURNING budget_snapshot_id
                """,
                (
                    PROVIDER, ACCOUNT_REF, month_start, month_end,
                    monthly_allowance, remaining, monthly_cap, per_run_cap, 8,
                    used, last_cost, fetched_at,
                    fetched_at.replace(microsecond=0) + __import__("datetime").timedelta(hours=24),
                    f"neon://{connection.info.dbname}/provider_responses/{response_id}",
                    budget_hash, TERMS_VERSION, TERMS_EVIDENCE_URI,
                    TERMS_EVIDENCE_SHA256, json.dumps([APPROVAL_ID]), fetched_at,
                ),
            ).fetchone()[0]

        active = status == 200 and payload_is_json and quota_valid and last_cost == 0
        metadata_patch = {
            "quota_status": "VERIFIED" if active else "UNVERIFIED",
            "quota_probe_response_id": response_id,
            "quota_probe_response_sha256": response_hash,
            "quota_probe_observed_at": _iso(fetched_at),
            "quota_remaining": remaining,
            "quota_monthly_allowance": monthly_allowance,
            "quota_last_cost": last_cost,
            "quota_snapshot_id": quota_snapshot_id,
            "budget_snapshot_id": budget_snapshot_id,
            "sports_catalogue_count": sports_count,
            "quota_probe_reason": (
                "NO_CREDIT_DISCOVERY_VERIFIED" if active
                else "HTTP_JSON_QUOTA_EVIDENCE_INCOMPLETE_OR_UNEXPECTED_COST"
            ),
        }
        connection.execute(
            """
            UPDATE provider_accounts
            SET entitlement_status = %s, checked_at = %s,
                metadata = metadata || %s::jsonb
            WHERE provider = %s
            """,
            (
                "ACTIVE" if active else "UNVERIFIED",
                fetched_at, json.dumps(metadata_patch), PROVIDER,
            ),
        )
        connection.commit()

    summary = {
        "provider": PROVIDER,
        "source_id": SOURCE_ID,
        "endpoint": "/v4/sports",
        "http_status": status,
        "response_sha256": response_hash,
        "fetched_at": _iso(fetched_at),
        "sports_catalogue_count": sports_count,
        "quota_headers_present": quota_valid,
        "requests_used": used,
        "requests_remaining": remaining,
        "requests_last": last_cost,
        "quota_snapshot_id": quota_snapshot_id,
        "budget_snapshot_id": budget_snapshot_id,
        "provider_response_id": response_id,
        "entitlement_status": "ACTIVE" if active else "UNVERIFIED",
        "odds_credit_endpoints_called": 0,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Call only /v4/sports and persist evidence.")
    parser.add_argument("--out", default="artifacts/odds-api-quota/public_summary.json")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "mode": "DRY_RUN",
            "provider": PROVIDER,
            "endpoint": "/v4/sports",
            "credit_cost": 0,
            "database": "veltrix_football_staging",
            "rights_approval_id": APPROVAL_ID,
        }, indent=2))
        return 0

    dsn = os.getenv("VELTRIX_STAGING_DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("VELTRIX_STAGING_DATABASE_URL_MISSING")
    validate_staging_dsn_target(dsn)
    status, body, headers, fetched_at = _fetch()
    response_hash = sha256(body).hexdigest()
    summary = _persist(
        dsn=dsn, status=status, body=body, headers=headers,
        fetched_at=fetched_at, response_hash=response_hash,
        summary_path=Path(args.out),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["entitlement_status"] != "ACTIVE":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
