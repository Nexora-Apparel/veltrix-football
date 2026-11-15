"""Manual-only V2 prospective 5Dollar result settlement.

Default mode is dry-run and performs no network or database access. --execute
is required for bounded provider reads and staging-only append-only settlement.
No production, publication, schedule, Telegram or value-bet action is possible.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

from veltrix_v2.data.fivedollar import parse_fixture_page
from veltrix_v2.data.contracts import DataUsePurpose
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.ledger.postgres_store import PostgresPaperLedgerStore
from veltrix_v2.ledger.settlement_reconciliation import reconcile_finished_fixtures

from scripts.phase5_collect_5dollar_shadow import (
    MAX_REQUESTS,
    _refresh_approval,
    _request_page,
    _persist_fixture_snapshot_to_staging,
)
from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target

LEDGER_ID = "veltrix-v2-prospective-observed"
MAX_PAGES = 14
MAX_PAGE_SIZE = 100
MIN_INTERVAL_SECONDS = 3.1


def _targets(ledger):
    rows = []
    for event in ledger.events:
        if event.event_type != "SHADOW_PREDICTION":
            continue
        payload = event.payload
        if payload.get("evidence_class") != "PROSPECTIVE_OBSERVED_ONLY":
            continue
        if payload.get("target_provider") != "5DollarFootballAPI":
            continue
        required = ("target_source_id", "target_source_fixture_id",
                    "target_provider_competition_id", "kickoff_at")
        if not all(isinstance(payload.get(key), str) and payload[key].strip()
                   for key in required):
            raise ValueError("SETTLEMENT_TARGET_PROVENANCE_INCOMPLETE")
        rows.append(event)
    return rows


def run(*, api_key: str, staging_dsn: str, out_dir: Path) -> dict:
    if not api_key.strip():
        raise ValueError("FIVEDOLLAR_API_KEY_REQUIRED")
    validate_staging_dsn_target(staging_dsn)
    import psycopg

    approval, _ = _refresh_approval(staging_dsn)
    host = urlparse(staging_dsn).hostname or ""
    with psycopg.connect(staging_dsn, autocommit=False) as connection:
        identity = connection.execute("SELECT current_database(), current_user").fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
        store = PostgresPaperLedgerStore(
            connection, ledger_id=LEDGER_ID, write_enabled=True,
            environment="staging", database_name=identity[0], host=host,
            role=identity[1],
        )
        ledger = store.load()
        targets = _targets(ledger)
        now = datetime.now(timezone.utc)
        eligible = [event for event in targets
                    if datetime.fromisoformat(event.payload["kickoff_at"]) <= now
                    and not any(e.event_type == "SETTLEMENT"
                                and e.fixture_id == event.fixture_id
                                and e.model_version == event.model_version
                                for e in ledger.events)]
        if not eligible:
            return {
                "status": "NO_ELIGIBLE_FINISHED_TARGETS",
                "shadow_targets": len(targets),
                "eligible_unsettled_targets": 0,
                "provider_requests": 0,
                "settlements_appended": 0,
                "publication": False,
                "telegram": False,
                "schedule": False,
            }

        by_competition: dict[str, list] = {}
        for event in eligible:
            comp = event.payload["target_provider_competition_id"]
            by_competition.setdefault(comp, []).append(event)
        if len(by_competition) > MAX_PAGES:
            raise RuntimeError("SETTLEMENT_COMPETITION_REQUEST_BUDGET_EXCEEDED")

        all_fixtures = []
        snapshots = []
        request_count = 0
        pacing = {"last_started": None}
        out_dir.mkdir(parents=True, exist_ok=True)
        for competition_id, events in sorted(by_competition.items(), key=lambda item: int(item[0])):
            starts = [datetime.fromisoformat(e.payload["kickoff_at"]) for e in events]
            start_at = min(starts) - timedelta(hours=1)
            end_at = datetime.now(timezone.utc)
            page = 1
            while True:
                if request_count >= MAX_PAGES:
                    raise RuntimeError("SETTLEMENT_REQUEST_CAP_REACHED")
                page_approval, rights_checked_at = _refresh_approval(staging_dsn)
                approved_scope = {
                    value.strip() for value in page_approval.competition_scope.split(",")
                    if value.strip()
                }
                if not approved_scope or "*" in approved_scope or competition_id not in approved_scope:
                    raise PermissionError("SETTLEMENT_COMPETITION_OUTSIDE_APPROVAL_SCOPE")
                collection_right = evaluate_source_use(
                    page_approval, DataUsePurpose.COLLECTION,
                    at_utc=rights_checked_at, commercial=False,
                )
                if not collection_right.allowed:
                    raise PermissionError(collection_right.reason_code)
                raw, headers, params, requested, retrieved, status = _request_page(
                    api_key, competition_id=competition_id, status="finished",
                    start_at=start_at, end_at=end_at, page=page,
                    pacing_state=pacing,
                    before_request=lambda: None,
                )
                request_count += 1
                parsed = parse_fixture_page(
                    raw, headers=headers, retrieved_at_utc=retrieved,
                    rights_approval_id=page_approval.approval_id,
                )
                recorded = datetime.now(timezone.utc)
                snapshot_approval, storage_checked_at = _refresh_approval(staging_dsn)
                if snapshot_approval.approval_id != page_approval.approval_id:
                    raise PermissionError("SETTLEMENT_RIGHTS_APPROVAL_CHANGED_DURING_CAPTURE")
                storage_right = evaluate_source_use(
                    snapshot_approval, DataUsePurpose.STORAGE,
                    at_utc=storage_checked_at, commercial=False,
                )
                if not storage_right.allowed:
                    raise PermissionError(storage_right.reason_code)
                # Retain every exact provider page before settlement. This is
                # a staging snapshot, not a claim of provider publication time.
                snapshot = _persist_fixture_snapshot_to_staging(
                    staging_dsn, request_id=f"settlement-{competition_id}-{page}-{retrieved.timestamp()}",
                    endpoint=f"/leagues/{competition_id}/fixtures",
                    request_params=params, requested_at=requested,
                    retrieved_at=retrieved, recorded_at=recorded,
                    raw_response=raw, response_headers=headers,
                    http_status=status, competition_id=competition_id,
                    fixture_count=len(parsed.fixtures), approval=snapshot_approval,
                    status_filter="finished",
                )
                snapshots.append(snapshot)
                (out_dir / f"{competition_id}_finished_page_{page}.json").write_bytes(raw)
                if not all(
                    isinstance(snapshot.get(key), str) and len(snapshot[key]) == 64
                    for key in ("response_sha256", "manifest_sha256")
                ):
                    raise RuntimeError("SETTLEMENT_CAPTURE_MANIFEST_EVIDENCE_MISSING")
                all_fixtures.extend(
                    replace(
                        fixture,
                        response_sha256=snapshot["response_sha256"],
                        capture_manifest_sha256=snapshot["manifest_sha256"],
                    )
                    for fixture in parsed.fixtures
                )
                if not parsed.has_more:
                    break
                page += 1

        # Re-resolve append-only rights status immediately before settlement.
        approval, _ = _refresh_approval(staging_dsn)
        recorded_at = datetime.now(timezone.utc)
        # Reconciliation appends to a verified in-memory copy first. Only then
        # are its exact settlement payloads appended under the DB advisory lock.
        current = store.load()
        preview, quarantined = reconcile_finished_fixtures(
            current, all_fixtures, approval, recorded_at=recorded_at,
        )
        persisted = []
        with connection.transaction():
            for event in preview:
                payload = event.payload
                persisted_event = store.append_settlement(
                    fixture_id=event.fixture_id, model_version=event.model_version,
                    home_goals=payload["home_goals"], away_goals=payload["away_goals"],
                    result_available_at=datetime.fromisoformat(payload["result_available_at"]),
                    result_retrieved_at=datetime.fromisoformat(payload["result_retrieved_at"]),
                    recorded_at=datetime.fromisoformat(payload["recorded_at"]),
                    source_provider=payload["source_provider"], source_id=payload["source_id"],
                    source_fixture_id=payload["source_fixture_id"],
                    result_payload_sha256=payload["result_payload_sha256"],
                    rights_approval_id=payload["rights_approval_id"],
                    rights_evidence_sha256=payload["rights_evidence_sha256"],
                    result_availability_basis=payload["result_availability_basis"],
                    settlement_delay_basis=payload["settlement_delay_basis"],
                    result_response_sha256=payload.get("result_response_sha256"),
                    result_capture_manifest_sha256=payload.get("result_capture_manifest_sha256"),
                )
                if persisted_event.event_sha256 != event.event_sha256:
                    raise RuntimeError("PAPER_LEDGER_SETTLEMENT_HASH_MISMATCH")
                persisted.append(persisted_event)
        verified = store.load()
        if not verified.verify_chain():
            raise RuntimeError("PAPER_LEDGER_CHAIN_VERIFICATION_FAILED")

    result = {
        "status": "SETTLEMENT_RECONCILIATION_COMPLETE",
        "shadow_targets": len(targets),
        "eligible_unsettled_targets": len(eligible),
        "provider_requests": request_count,
        "provider_pages_persisted": len(snapshots),
        "finished_rows_observed": len(all_fixtures),
        "settlements_appended": len(persisted),
        "quarantined_rows": [{"fixture_id": fid, "reason": reason}
                             for fid, reason in quarantined],
        "ledger_events": len(verified.events),
        "ledger_chain_verified": True,
        "publication": False,
        "telegram": False,
        "schedule": False,
        "value_betting": "LOCKED",
    }
    (out_dir / "settlement_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="V2 prospective 5Dollar settlement collector")
    parser.add_argument("--execute", action="store_true",
                        help="perform bounded reads and staging-only settlement")
    parser.add_argument("--out", default="artifacts/v2-settlement")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "mode": "DRY_RUN", "provider": "5DollarFootballAPI",
            "ledger": LEDGER_ID, "max_provider_requests": MAX_PAGES,
            "would_connect_to_database": False, "would_call_provider": False,
            "would_write_database": False, "settlement": False,
            "publication": False, "telegram": False, "schedule": False,
        }, indent=2))
        return 0
    result = run(
        api_key=os.environ.get("FIVEDOLLARFOOTBALL_API_KEY", ""),
        staging_dsn=os.environ.get("VELTRIX_STAGING_DATABASE_URL", ""),
        out_dir=Path(args.out),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
