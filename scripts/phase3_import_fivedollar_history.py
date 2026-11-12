#!/usr/bin/env python3
"""Bounded 5Dollar historical fixture/result import into the isolated staging database."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import phase2_fivedollar_history_dry_run as provider
from veltrix_v2.data.contracts import ProviderResponse
from veltrix_v2.data.fivedollar import FixturePageError, parse_fixture_page
from veltrix_v2.data.postgres import PostgresHistoryStore
from veltrix_v2.data.rights import evaluate_fixture_import

REQUEST_BUDGET = 40
PER_PAGE = 100
PACE_SECONDS = 4.0
EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_DATABASE_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
MIGRATION_CHECKSUMS = {
    "0001_persistent_foundation": "b5f6f1b5dbe6d7587c4876578f50d8327711f7fd26d03410f31a04db659d267c",
    "0002_historical_provenance": "619c556674e409ad5cd3a9ddc9ae578455207545d3435b9ece4e91a953fef49a",
    "0003_source_approval_status_events": "8c70a8a1a060949a4fca924b1b0854d94e125b2cbf6f677049e7e70b4a836a19",
}


def _preflight(database_url: str, expected_database: str) -> None:
    if os.getenv("VELTRIX_ENABLE_STAGING_IMPORT") != "YES":
        raise RuntimeError("STAGING_IMPORT_EXPLICIT_ENABLE_REQUIRED")
    if expected_database != EXPECTED_DATABASE:
        raise RuntimeError("STAGING_IMPORT_DATABASE_ALLOWLIST_MISMATCH")
    if not database_url:
        raise RuntimeError("STAGING_DATABASE_URL_REQUIRED")
    expected_host = os.getenv("VELTRIX_EXPECTED_DATABASE_HOST", "").strip().casefold()
    actual_host = (urlparse(database_url).hostname or "").casefold()
    if expected_host != EXPECTED_DATABASE_HOST:
        raise RuntimeError("STAGING_EXPECTED_HOST_CONFIGURATION_MISMATCH")
    if actual_host != EXPECTED_DATABASE_HOST:
        raise RuntimeError("STAGING_DATABASE_HOST_ALLOWLIST_MISMATCH")
    import psycopg

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(),current_user")
            actual, role = cur.fetchone()
            if actual != EXPECTED_DATABASE:
                raise RuntimeError("STAGING_DATABASE_TARGET_MISMATCH")
            if role != "neondb_owner":
                raise RuntimeError("STAGING_DATABASE_ROLE_MISMATCH")
            cur.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")
            observed = {version: checksum.strip() for version, checksum in cur.fetchall()}
            if observed != MIGRATION_CHECKSUMS:
                raise RuntimeError("STAGING_MIGRATION_MANIFEST_MISMATCH")


def _provider_response(endpoint: str, request_id: str, params: dict, raw: bytes,
                       headers: dict, fetched_at: datetime) -> ProviderResponse:
    return ProviderResponse(
        provider=provider.PROVIDER,
        source_id=provider.SOURCE_ID,
        endpoint=endpoint,
        request_id=request_id,
        request_params=params,
        http_status=200,
        raw_body=raw,
        response_headers=provider._safe_headers(headers),
        fetched_at_utc=fetched_at,
    )


def run_import(database_url: str, api_key: str, *, days: int = 365,
               request_fn=provider._request, sleep=time.sleep) -> dict:
    if not api_key.strip():
        raise RuntimeError("FIVEDOLLAR_API_KEY_REQUIRED")
    if days < 1 or days > 365:
        raise ValueError("HISTORY_WINDOW_MUST_BE_1_TO_365_DAYS")

    _preflight(database_url, os.getenv("VELTRIX_EXPECTED_DATABASE", ""))
    import psycopg

    store = PostgresHistoryStore(
        lambda: psycopg.connect(database_url),
        allow_writes=True,
        expected_database=EXPECTED_DATABASE,
    )
    checked_at = datetime.now(timezone.utc)
    window_start = checked_at - timedelta(days=days)
    approval = provider._source_approval(checked_at)
    request_count = 0
    last_headers = {}
    response_hashes = []
    manifest_parts = []
    total_seen = total_inserted = total_rejected = total_quarantined = 0
    page_count = 0
    fixture_count_by_competition = Counter()
    duplicate_ids_seen: set[str] = set()
    run_id = None
    status = "FAILED"
    failure_reason = None
    watermark_advanced = False
    watermark_error = None

    def call(path: str):
        nonlocal request_count, last_headers
        if request_count >= REQUEST_BUDGET:
            raise RuntimeError("REQUEST_BUDGET_EXHAUSTED")
        if request_count:
            sleep(PACE_SECONDS)
        http_status, raw, headers = request_fn(path, api_key)
        request_count += 1
        last_headers = provider._safe_headers(headers)
        payload = provider._parse_json(raw, http_status)
        response_hashes.append(hashlib.sha256(raw).hexdigest())
        return payload, raw, headers, datetime.now(timezone.utc)

    # Provider account status and competition catalogue are themselves archived as raw responses.
    status_payload, status_raw, status_headers, status_fetched = call("/status")
    status_data = status_payload.get("data")
    if not isinstance(status_data, dict):
        raise RuntimeError("PROVIDER_STATUS_SCHEMA_INVALID")
    limits = status_data.get("limits") if isinstance(status_data.get("limits"), dict) else {}
    if str(status_data.get("plan") or "").casefold() != "community":
        raise RuntimeError("PROVIDER_PLAN_CHANGED")
    if provider._integer(limits.get("rate_limit")) != 300 or provider._integer(limits.get("burst_per_minute")) != 20:
        raise RuntimeError("PROVIDER_QUOTA_PROFILE_CHANGED")
    remaining = provider._integer(last_headers.get("x-ratelimit-remaining"))
    if remaining is None or remaining < REQUEST_BUDGET + 2:
        raise RuntimeError("INSUFFICIENT_PROVIDER_QUOTA_FOR_BOUNDED_IMPORT")

    status_response = _provider_response(
        "/status", "phase3-status-" + hashlib.sha256(status_raw).hexdigest()[:20],
        {"operation": "account_status"}, status_raw, status_headers, status_fetched,
    )
    status_record = store.persist_page(status_response, [], approval)

    leagues_payload, leagues_raw, leagues_headers, leagues_fetched = call("/leagues")
    league_rows = leagues_payload.get("data")
    if isinstance(league_rows, dict):
        league_rows = league_rows.get("leagues")
    if not isinstance(league_rows, list):
        raise RuntimeError("PROVIDER_LEAGUE_CATALOGUE_INVALID")
    if not isinstance(leagues_payload.get("pagination"), dict) or leagues_payload["pagination"].get("has_more") is not False:
        raise RuntimeError("PROVIDER_LEAGUE_CATALOGUE_PAGINATION_INCOMPLETE")
    observed = {}
    for row in league_rows:
        if isinstance(row, dict) and row.get("id") is not None:
            observed[str(row["id"])] = str(row.get("name") or "unknown")
    if observed != provider.EXPECTED_COMPETITIONS:
        raise RuntimeError("PROVIDER_COMPETITION_ALLOWLIST_CHANGED")
    leagues_response = _provider_response(
        "/leagues", "phase3-leagues-" + hashlib.sha256(leagues_raw).hexdigest()[:20],
        {"operation": "competition_catalogue"}, leagues_raw, leagues_headers, leagues_fetched,
    )
    leagues_record = store.persist_page(leagues_response, [], approval)
    store.record_entitlement_observation(
        provider=provider.PROVIDER,
        source_id=provider.SOURCE_ID,
        plan_code="community",
        entitlement_status="ACTIVE",
        country_pack_code=provider._country_pack(status_data),
        competition_ids=sorted(observed),
        rate_limit_hour=300,
        rate_limit_minute=20,
        quota_remaining=remaining,
        provider_response_id=leagues_record["provider_response_id"],
        evidence_sha256=hashlib.sha256(status_raw + b"\0" + leagues_raw).hexdigest(),
        checked_at_utc=max(status_fetched, leagues_fetched),
    )

    run_id = store.start_import_run(
        provider=provider.PROVIDER,
        import_type="historical_fixture_results",
        boundary_start=window_start,
        boundary_end=checked_at,
        request_budget=REQUEST_BUDGET,
        importer_version="phase3.1",
        rights_approval_id=approval.approval_id,
        started_at_utc=checked_at,
    )

    try:
        start_epoch, end_epoch = int(window_start.timestamp()), int(checked_at.timestamp())
        for competition_id, competition_name in sorted(provider.EXPECTED_COMPETITIONS.items()):
            page = 1
            comp_seen = comp_inserted = comp_rejected = comp_quarantined = 0
            while True:
                params = {
                    "status": "finished",
                    "start_time": start_epoch,
                    "end_time": end_epoch,
                    "per_page": PER_PAGE,
                    "page": page,
                }
                endpoint = f"/leagues/{competition_id}/fixtures"
                path = endpoint + "?" + urlencode(params)
                payload, raw, headers, fetched_at = call(path)
                parsed = parse_fixture_page(
                    raw, headers=headers, retrieved_at_utc=fetched_at,
                    rights_approval_id=approval.approval_id,
                )
                if parsed.page != page or parsed.per_page != PER_PAGE:
                    raise RuntimeError("FIXTURE_PAGINATION_RESPONSE_MISMATCH")
                if any(row.provider_competition_id != competition_id for row in parsed.fixtures):
                    raise RuntimeError("FIXTURE_COMPETITION_SCOPE_MISMATCH")
                if any(row.kickoff_at_utc < window_start or row.kickoff_at_utc > checked_at for row in parsed.fixtures):
                    raise RuntimeError("FIXTURE_OUTSIDE_REQUESTED_WINDOW")

                duplicates = frozenset(
                    row.provider_fixture_id for row in parsed.fixtures
                    if row.provider_fixture_id in duplicate_ids_seen
                )
                duplicate_ids_seen.update(row.provider_fixture_id for row in parsed.fixtures)
                response = _provider_response(
                    endpoint,
                    f"phase3-{run_id}-{competition_id}-{page}-{parsed.response_sha256[:16]}",
                    params, raw, headers, fetched_at,
                )
                outcome = store.persist_page(
                    response, parsed.fixtures, approval,
                    import_run_id=run_id,
                    duplicate_fixture_ids=duplicates,
                )
                decisions = [
                    evaluate_fixture_import(row, approval, evaluated_at_utc=fetched_at)
                    for row in parsed.fixtures
                ]
                page_rejected = sum(item.status.value == "REJECTED" for item in decisions)
                page_conflicts = outcome["quarantined_or_conflicting"]
                if page_conflicts < page_rejected:
                    raise RuntimeError("INGESTION_OUTCOME_ACCOUNTING_MISMATCH")
                page_quarantined = page_conflicts - page_rejected
                page_inserted = len(parsed.fixtures) - page_conflicts

                comp_seen += len(parsed.fixtures)
                comp_inserted += page_inserted
                comp_rejected += page_rejected
                comp_quarantined += page_quarantined
                total_seen += len(parsed.fixtures)
                total_inserted += page_inserted
                total_rejected += page_rejected
                total_quarantined += page_quarantined
                page_count += 1
                fixture_count_by_competition[competition_id] += len(parsed.fixtures)
                manifest_parts.extend(
                    f"{row.provider}|{row.source_id}|{row.provider_fixture_id}|{row.provider_competition_id}|{row.payload_sha256}"
                    for row in parsed.fixtures
                )
                store.upsert_checkpoint(
                    import_run_id=run_id,
                    window_start=window_start,
                    window_end=checked_at,
                    cursor_value=f"competition={competition_id};page={page}",
                    status="RUNNING",
                    records_seen=total_seen,
                    records_inserted=total_inserted,
                    records_rejected=total_rejected,
                    records_quarantined=total_quarantined,
                    requests_used=request_count,
                    response_sha256=parsed.response_sha256,
                )
                if not parsed.has_more:
                    break
                if not parsed.fixtures:
                    raise RuntimeError("EMPTY_PAGE_WITH_MORE_RESULTS")
                page += 1
            if fixture_count_by_competition[competition_id] == 0:
                raise RuntimeError(f"NO_HISTORICAL_FIXTURES:{competition_id}")

        manifest_material = "\n".join(sorted(response_hashes + manifest_parts)).encode("utf-8")
        manifest_sha256 = hashlib.sha256(manifest_material).hexdigest()
        store.upsert_checkpoint(
            import_run_id=run_id,
            window_start=window_start,
            window_end=checked_at,
            cursor_value="complete",
            status="COMPLETED",
            records_seen=total_seen,
            records_inserted=total_inserted,
            records_rejected=total_rejected,
            records_quarantined=total_quarantined,
            requests_used=request_count,
            response_sha256=response_hashes[-1] if response_hashes else None,
        )
        store.finish_import_run(
            import_run_id=run_id,
            status="COMPLETED",
            finished_at_utc=datetime.now(timezone.utc),
            requests_used=request_count,
            records_seen=total_seen,
            records_inserted=total_inserted,
            records_rejected=total_rejected,
            records_quarantined=total_quarantined,
            manifest_sha256=manifest_sha256,
        )
        try:
            watermark = store.get_sync_watermark(
                provider=provider.PROVIDER,
                data_class="fixture_result",
                scope="community-seven-competitions",
            )
            expected_version = int(watermark[1]) if watermark else 0
            store.advance_sync_watermark(
                provider=provider.PROVIDER,
                data_class="fixture_result",
                scope="community-seven-competitions",
                cursor_value=checked_at.isoformat(),
                expected_version=expected_version,
                updated_at_utc=datetime.now(timezone.utc),
            )
            watermark_advanced = True
        except Exception as exc:
            watermark_error = type(exc).__name__ + ":" + str(exc)[:120]
        status = "COMPLETED"
        failure_reason = None
    except Exception as exc:
        failure_reason = type(exc).__name__ + ":" + str(exc)[:180]
        try:
            store.upsert_checkpoint(
                import_run_id=run_id,
                window_start=window_start,
                window_end=checked_at,
                cursor_value="failed",
                status="FAILED",
                records_seen=total_seen,
                records_inserted=total_inserted,
                records_rejected=total_rejected,
                records_quarantined=total_quarantined,
                requests_used=request_count,
                response_sha256=response_hashes[-1] if response_hashes else None,
                last_error_code=type(exc).__name__,
            )
            store.finish_import_run(
                import_run_id=run_id,
                status="FAILED",
                finished_at_utc=datetime.now(timezone.utc),
                requests_used=request_count,
                records_seen=total_seen,
                records_inserted=total_inserted,
                records_rejected=total_rejected,
                records_quarantined=total_quarantined,
                manifest_sha256=None,
                reason_code=type(exc).__name__,
            )
        except Exception:
            pass
        raise

    return {
        "schema_version": 1,
        "status": status,
        "provider": provider.PROVIDER,
        "database": EXPECTED_DATABASE,
        "import_run_id": run_id,
        "window_start_utc": window_start.isoformat(),
        "window_end_utc": checked_at.isoformat(),
        "fixtures_seen": total_seen,
        "fixtures_accepted": total_inserted,
        "fixtures_rejected": total_rejected,
        "fixtures_quarantined": total_quarantined,
        "pages": page_count,
        "requests_used": request_count,
        "request_budget": REQUEST_BUDGET,
        "competition_fixture_counts": dict(fixture_count_by_competition),
        "manifest_sha256": manifest_sha256,
        "watermark_advanced": watermark_advanced,
        "watermark_error": watermark_error,
        "raw_provider_responses_archived": len(response_hashes),
        "availability_basis": "provider_finished_status_conservative_4d",
        "point_in_time_certifiable": False,
        "side_effects": {
            "staging_database_writes": True,
            "production_database_writes": False,
            "prediction_changes": 0,
            "telegram_messages": 0,
            "deployments": 0,
        },
        "failure_reason": failure_reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--output", default="reports/phase3/staging-import.json")
    args = parser.parse_args()
    report = run_import(
        os.getenv("DATABASE_URL", ""),
        os.getenv("FIVEDOLLARFOOTBALL_API_KEY", ""),
        days=args.days,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
