"""Manual-only V2 prospective 5Dollar result settlement.

Default mode is dry-run and performs no network or database access. --execute
is required for bounded provider reads and staging-only append-only settlement.
No production, publication, schedule, Telegram or value-bet action is possible.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

# Direct script execution places scripts/ rather than the repository root on sys.path.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from veltrix_v2.data.fivedollar import parse_fixture_page
from veltrix_v2.data.contracts import DataUsePurpose
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.ledger.postgres_store import PostgresPaperLedgerStore
from veltrix_v2.evaluation.prospective_settlement_metrics import evaluate_prospective_settlements
from veltrix_v2.ledger.settlement_reconciliation import (
    reconcile_finished_fixtures,
    reconcile_v2_finished_fixtures,
)
from veltrix_v2.ledger.paper_predictions import V2_PIT_MODEL_VERSION

from scripts.phase5_collect_5dollar_shadow import (
    MAX_REQUESTS,
    _refresh_approval,
    _request_page,
    _persist_fixture_snapshot_to_staging,
    _require_quota_headroom,
)
from scripts.phase5_staging_coverage_audit import validate_staging_dsn_target

LEDGER_ID = "veltrix-v2-prospective-observed"
MAX_PAGES = MAX_REQUESTS
MAX_PAGE_SIZE = 100
MIN_INTERVAL_SECONDS = 3.1



def _public_summary(result: dict) -> dict:
    """Aggregate-only settlement summary; never publish fixture IDs or row-level evidence."""
    summary = {
        "status": result.get("status"),
        "shadow_targets": result.get("shadow_targets", 0),
        "v2_pit_targets": result.get("v2_pit_targets", 0),
        "v2_pit_feature_links_available": result.get("v2_pit_feature_links_available", 0),
        "eligible_unsettled_targets": result.get("eligible_unsettled_targets", 0),
        "provider_requests": result.get("provider_requests", 0),
        "provider_pages_persisted": result.get("provider_pages_persisted", 0),
        "finished_rows_observed": result.get("finished_rows_observed", 0),
        "settlements_appended": result.get("settlements_appended", 0),
        "shadow_settlements_appended": result.get("shadow_settlements_appended", 0),
        "v2_pit_settlements_appended": result.get("v2_pit_settlements_appended", 0),
        "quarantined_count": len(result.get("quarantined_rows", ())),
        "ledger_events": result.get("ledger_events", 0),
        "ledger_chain_verified": result.get("ledger_chain_verified", False),
        "publication": False,
        "telegram": False,
        "schedule": False,
        "value_betting": "LOCKED",
    }
    if "ledger_post_commit_verified" in result:
        summary["ledger_post_commit_verified"] = result["ledger_post_commit_verified"]
    if "prospective_scorecard" in result:
        summary["prospective_scorecard"] = result["prospective_scorecard"]
    return summary


def _write_summaries(out_dir: Path, result: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "settlement_summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    (out_dir / "settlement_public_summary.json").write_text(
        json.dumps(_public_summary(result), indent=2, sort_keys=True), encoding="utf-8"
    )

def _targets(ledger):
    rows = []
    for event in ledger.events:
        payload = event.payload
        is_shadow = (
            event.event_type == "SHADOW_PREDICTION"
            and payload.get("evidence_class") == "PROSPECTIVE_OBSERVED_ONLY"
        )
        is_v2_pit = (
            event.event_type == "PREDICTION"
            and event.model_version == V2_PIT_MODEL_VERSION
            and payload.get("evidence_class") == "PIT_CERTIFIED"
            and payload.get("point_in_time_certifiable") is True
        )
        if not (is_shadow or is_v2_pit):
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


def _load_v2_feature_links(connection, targets) -> dict[str, dict[str, object]]:
    """Read immutable V2 PIT feature links; never infer or reconstruct missing links."""
    v2_events = [
        event for event in targets
        if event.event_type == "PREDICTION" and event.model_version == V2_PIT_MODEL_VERSION
    ]
    if not v2_events:
        return {}
    exists = connection.execute(
        "SELECT to_regclass('public.prediction_feature_snapshot_links') IS NOT NULL"
    ).fetchone()[0]
    if not exists:
        raise RuntimeError("V2_SETTLEMENT_FEATURE_LINK_MIGRATION_NOT_APPLIED")
    hashes = [event.event_sha256 for event in v2_events]
    rows = connection.execute(
        """
        SELECT prediction_event_sha256,link_sha256,feature_snapshot_id,
               eligibility_event_id,feature_set_sha256,eligibility_evidence_sha256,
               forecast_evidence_sha256,model_artifact_sha256,
               forecast_cutoff_at,feature_snapshot_cutoff_at,recorded_at,
               canonical_competition_id,canonical_home_team_id,canonical_away_team_id,
               provider_competition_id,provider_home_team_id,provider_away_team_id
        FROM prediction_feature_snapshot_links
        WHERE prediction_event_sha256 = ANY(%s)
        """,
        (hashes,),
    ).fetchall()
    links = {}
    for row in rows:
        event_hash = str(row[0]).strip()
        if event_hash in links:
            raise RuntimeError("V2_SETTLEMENT_FEATURE_LINK_NOT_UNIQUE")
        links[event_hash] = {
            "prediction_event_sha256":event_hash,
            "link_sha256":str(row[1]).strip(),
            "feature_snapshot_id":int(row[2]),
            "eligibility_event_id":int(row[3]),
            "feature_set_sha256":str(row[4]).strip(),
            "eligibility_evidence_sha256":str(row[5]).strip(),
            "forecast_evidence_sha256":str(row[6]).strip(),
            "model_artifact_sha256":str(row[7]).strip(),
            "forecast_cutoff_at":row[8],
            "feature_snapshot_cutoff_at":row[9],
            "recorded_at":row[10],
            "canonical_competition_id":str(row[11]),
            "canonical_home_team_id":str(row[12]),
            "canonical_away_team_id":str(row[13]),
            "provider_competition_id":str(row[14]),
            "provider_home_team_id":str(row[15]),
            "provider_away_team_id":str(row[16]),
        }
    return links


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
        shadow_targets = [e for e in targets if e.event_type == "SHADOW_PREDICTION"]
        v2_pit_targets = [e for e in targets if e.event_type == "PREDICTION"]
        now = datetime.now(timezone.utc)
        eligible = [event for event in targets
                    if datetime.fromisoformat(event.payload["kickoff_at"]) <= now
                    and not any(e.event_type == "SETTLEMENT"
                                and e.fixture_id == event.fixture_id
                                and e.model_version == event.model_version
                                for e in ledger.events)]
        if not eligible:
            scorecard = evaluate_prospective_settlements(ledger)
            result = {
                "status": "NO_ELIGIBLE_FINISHED_TARGETS",
                "shadow_targets": len(shadow_targets),
                "v2_pit_targets": len(v2_pit_targets),
                "v2_pit_feature_links_available": len(v2_feature_links),
                "eligible_unsettled_targets": 0,
                "provider_requests": 0,
                "settlements_appended": 0,
                "publication": False,
                "telegram": False,
                "schedule": False,
                "value_betting": "LOCKED",
                "ledger_chain_verified": ledger.verify_chain(),
                "ledger_post_commit_verified": None,
                "ledger_write_performed": False,
                "prospective_scorecard": asdict(scorecard),
            }
            _write_summaries(out_dir, result)
            return result

        eligible_v2_pit_targets = [e for e in eligible if e.event_type == "PREDICTION"]
        v2_feature_links = _load_v2_feature_links(connection, eligible_v2_pit_targets)

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
                _require_quota_headroom(parsed.quota_remaining, request_count)
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
        shadow_preview, shadow_quarantined = reconcile_finished_fixtures(
            current, all_fixtures, approval, recorded_at=recorded_at,
        )
        v2_preview, v2_quarantined = reconcile_v2_finished_fixtures(
            current, all_fixtures, approval,
            v2_feature_links=v2_feature_links,
            recorded_at=recorded_at,
        )
        preview = tuple(shadow_preview) + tuple(v2_preview)
        quarantined = tuple(shadow_quarantined) + tuple(v2_quarantined)
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
                    prediction_feature_link_sha256=payload.get("prediction_feature_link_sha256"),
                    feature_snapshot_id=payload.get("feature_snapshot_id"),
                    eligibility_event_id=payload.get("eligibility_event_id"),
                    feature_set_sha256=payload.get("feature_set_sha256"),
                    eligibility_evidence_sha256=payload.get("eligibility_evidence_sha256"),
                    forecast_evidence_sha256=payload.get("forecast_evidence_sha256"),
                    model_artifact_sha256=payload.get("model_artifact_sha256"),
                    canonical_competition_id=payload.get("canonical_competition_id"),
                    canonical_home_team_id=payload.get("canonical_home_team_id"),
                    canonical_away_team_id=payload.get("canonical_away_team_id"),
                    provider_competition_id=payload.get("provider_competition_id"),
                    provider_home_team_id=payload.get("provider_home_team_id"),
                    provider_away_team_id=payload.get("provider_away_team_id"),
                )
                if persisted_event.event_sha256 != event.event_sha256:
                    raise RuntimeError("PAPER_LEDGER_SETTLEMENT_HASH_MISMATCH")
                persisted.append(persisted_event)
        verified = store.load()
        if not verified.verify_chain():
            raise RuntimeError("PAPER_LEDGER_CHAIN_VERIFICATION_FAILED")
        expected_event_count = len(verified.events)
        expected_settlement_hashes = {
            (event.fixture_id, event.model_version): event.event_sha256
            for event in persisted
        }

    # The write connection has committed. Re-open staging independently and
    # verify the exact appended settlement hashes and full chain after commit.
    with psycopg.connect(staging_dsn, autocommit=True) as verify_connection:
        identity = verify_connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity != ("veltrix_football_staging", "neondb_owner"):
            raise PermissionError("STAGING_DATABASE_ROLE_NOT_ALLOWLISTED")
        verify_store = PostgresPaperLedgerStore(
            verify_connection, ledger_id=LEDGER_ID, write_enabled=False,
            environment="staging", database_name=identity[0], host=host,
            role=identity[1],
        )
        verified = verify_store.load()
        if not verified.verify_chain():
            raise RuntimeError("PAPER_LEDGER_POST_COMMIT_CHAIN_VERIFICATION_FAILED")
        if len(verified.events) != expected_event_count:
            raise RuntimeError("PAPER_LEDGER_POST_COMMIT_COUNT_MISMATCH")
        actual_settlement_hashes = {
            (event.fixture_id, event.model_version): event.event_sha256
            for event in verified.events if event.event_type == "SETTLEMENT"
        }
        for key, event_hash in expected_settlement_hashes.items():
            if actual_settlement_hashes.get(key) != event_hash:
                raise RuntimeError("PAPER_LEDGER_POST_COMMIT_SETTLEMENT_MISMATCH")

    scorecard = evaluate_prospective_settlements(verified)
    result = {
        "status": "SETTLEMENT_RECONCILIATION_COMPLETE",
        "shadow_targets": len(shadow_targets),
        "v2_pit_targets": len(v2_pit_targets),
        "v2_pit_feature_links_available": len(v2_feature_links),
        "eligible_unsettled_targets": len(eligible),
        "provider_requests": request_count,
        "provider_pages_persisted": len(snapshots),
        "finished_rows_observed": len(all_fixtures),
        "settlements_appended": len(persisted),
        "shadow_settlements_appended": sum(e.model_version != V2_PIT_MODEL_VERSION for e in persisted),
        "v2_pit_settlements_appended": sum(e.model_version == V2_PIT_MODEL_VERSION for e in persisted),
        "quarantined_rows": [{"fixture_id": fid, "reason": reason}
                             for fid, reason in quarantined],
        "ledger_events": len(verified.events),
        "ledger_chain_verified": True,
        "ledger_post_commit_verified": True,
        "ledger_write_performed": bool(persisted),
        "prospective_scorecard": asdict(scorecard),
        "publication": False,
        "telegram": False,
        "schedule": False,
        "value_betting": "LOCKED",
    }
    _write_summaries(out_dir, result)
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
    print(json.dumps(_public_summary(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
