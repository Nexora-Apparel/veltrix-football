"""Exercise the Phase 2 Postgres writer against the ephemeral CI database only."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg

from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, FixtureStatus, HistoricalFixture, ProviderResponse, SourceApproval,
)
from veltrix_v2.data.fivedollar import AVAILABILITY_BASIS
from veltrix_v2.data.postgres import PostgresHistoryStore


def main() -> dict:
    database_url = os.environ["DATABASE_URL"]
    expected_db = os.environ["VELTRIX_EXPECTED_DATABASE"]
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            actual_db = cur.fetchone()[0]
    if actual_db != expected_db or expected_db != "veltrix_football_test":
        raise RuntimeError("PHASE2_WRITER_ACCEPTANCE_REFUSES_NON_EPHEMERAL_DATABASE")

    now = datetime.now(timezone.utc)
    kickoff = now - timedelta(days=30)
    evidence_path = Path(__file__).resolve().parents[1] / "docs/legal/5dollar-terms-review-2026-11-12.md"
    evidence_hash = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    approval = SourceApproval(
        approval_id="phase2-ci-5dollar-approval",
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        competition_scope="3118717965,522514093,4160026622,3614399544,686337048,3405541143,4212821298",
        data_type="fixture_result",
        status=ApprovalStatus.APPROVED,
        permitted_uses=frozenset({
            DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
            DataUsePurpose.HISTORICAL_IMPORT, DataUsePurpose.MODEL_TRAINING,
            DataUsePurpose.CACHE, DataUsePurpose.PUBLIC_DISPLAY,
        }),
        commercial_use_allowed=True,
        terms_url="https://5dollarfootballapi.com/terms",
        terms_version="October 2026",
        evidence_uri="https://github.com/Nexora-Apparel/veltrix-football/blob/main/docs/legal/5dollar-terms-review-2026-11-12.md",
        evidence_sha256=evidence_hash,
        rights_basis="TERMS",
        reviewed_at_utc=now,
        reviewer_id="PHASE2_CI_ACCEPTANCE",
        valid_from_utc=now - timedelta(days=1),
        attribution_required=True,
        attribution_text="Football data by 5DollarFootballAPI",
        attribution_url="https://5dollarfootballapi.com",
        raw_redistribution_allowed=False,
    )
    payload = {
        "id": 987654321,
        "league": {"id": 4160026622, "name": "England Premier League", "season": "2025/2026"},
        "teams": {
            "home": {"id": 990001, "name": "CI Home"},
            "away": {"id": 990002, "name": "CI Away"},
        },
        "kickoff_utc": kickoff.isoformat(),
        "status": "finished",
        "goals": {"home": 2, "away": 1},
    }
    raw_fixture = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    fixture = HistoricalFixture(
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        provider_fixture_id="987654321",
        provider_competition_id="4160026622",
        provider_home_team_id="990001",
        provider_away_team_id="990002",
        competition_name="England Premier League",
        home_team_name="CI Home",
        away_team_name="CI Away",
        kickoff_at_utc=kickoff,
        season_key="2025/2026",
        status=FixtureStatus.FINISHED,
        home_score=2,
        away_score=1,
        payload=payload,
        payload_sha256=hashlib.sha256(raw_fixture).hexdigest(),
        retrieved_at_utc=now,
        source_event_time_utc=kickoff,
        available_at_utc=kickoff + timedelta(days=4),
        availability_basis=AVAILABILITY_BASIS,
        point_in_time_certifiable=False,
        rights_approval_id=approval.approval_id,
    )

    def response(request_id: str, score: tuple[int, int]) -> ProviderResponse:
        row = dict(payload)
        row["goals"] = {"home": score[0], "away": score[1]}
        body = json.dumps({"success": 1, "data": [row], "pagination": {
            "page": 1, "per_page": 100, "has_more": False
        }}, sort_keys=True, separators=(",", ":")).encode()
        return ProviderResponse(
            provider="5DollarFootballAPI",
            source_id="5dollarfootballapi",
            endpoint="/leagues/4160026622/fixtures",
            request_id=request_id,
            request_params={"league_id": 4160026622, "status": "finished", "page": 1, "per_page": 100},
            http_status=200,
            raw_body=body,
            response_headers={"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "250"},
            fetched_at_utc=now,
        )

    store = PostgresHistoryStore(
        lambda: psycopg.connect(database_url),
        allow_writes=True,
        expected_database=expected_db,
    )
    store.persist_source_approval(approval)
    approval_conflict_rejected = False
    try:
        store.persist_source_approval(replace(approval, commercial_use_allowed=False))
    except ValueError as exc:
        approval_conflict_rejected = str(exc) == "SOURCE_APPROVAL_IDEMPOTENCY_CONFLICT"
    assert approval_conflict_rejected, "approval ID replay accepted altered rights fields"
    run_id = store.start_import_run(
        provider="5DollarFootballAPI", import_type="historical_fixture_results",
        boundary_start=kickoff, boundary_end=now, request_budget=5,
        importer_version="phase2.1", rights_approval_id=approval.approval_id,
        started_at_utc=now,
    )
    status_response = replace(
        response("phase2-ci-status", (2, 1)),
        endpoint="/status",
        request_params={"operation": "account_status"},
    )
    status_record = store.persist_page(status_response, [], approval)
    store.record_entitlement_observation(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        plan_code="community", entitlement_status="ACTIVE",
        country_pack_code=None,
        competition_ids=sorted(["3118717965","522514093","4160026622","3614399544","686337048","3405541143","4212821298"]),
        rate_limit_hour=300, rate_limit_minute=20, quota_remaining=250,
        provider_response_id=status_record["provider_response_id"],
        evidence_sha256=hashlib.sha256(b"phase2-ci-entitlement-evidence").hexdigest(),
        checked_at_utc=now,
    )
    first_response = response("phase2-ci-page-1", (2, 1))
    first = store.persist_page(first_response, [fixture], approval, import_run_id=run_id)
    repeated = store.persist_page(first_response, [fixture], approval, import_run_id=run_id)
    assert first["source_observations"] == 1 and first["fixtures_inserted"] == 1
    assert first["result_versions_inserted"] == 1 and first["results_inserted"] == 1
    assert repeated["source_observations"] == 0 and repeated["fixtures_inserted"] == 0
    assert repeated["result_versions_inserted"] == 0 and repeated["results_inserted"] == 0

    changed_payload = dict(payload)
    changed_payload["goals"] = {"home": 3, "away": 1}
    changed_raw = json.dumps(changed_payload, sort_keys=True, separators=(",", ":")).encode()
    conflicting_fixture = replace(
        fixture,
        home_score=3,
        away_score=1,
        payload=changed_payload,
        payload_sha256=hashlib.sha256(changed_raw).hexdigest(),
    )
    second_response = response("phase2-ci-page-2", (3, 1))
    conflict = store.persist_page(second_response, [conflicting_fixture], approval, import_run_id=run_id)
    assert conflict["result_versions_inserted"] == 1
    assert conflict["results_inserted"] == 0
    assert conflict["quarantined_or_conflicting"] == 1

    unauthorized_payload = dict(payload)
    unauthorized_payload["id"] = 987654322
    unauthorized_payload["league"] = {
        "id": 999999, "name": "Unentitled Competition", "season": "2025/2026"
    }
    unauthorized_payload["teams"] = {
        "home": {"id": 990003, "name": "Unauthorized Home"},
        "away": {"id": 990004, "name": "Unauthorized Away"},
    }
    unauthorized_raw = json.dumps(
        unauthorized_payload, sort_keys=True, separators=(",", ":")
    ).encode()
    unauthorized_fixture = replace(
        fixture,
        provider_fixture_id="987654322",
        provider_competition_id="999999",
        provider_home_team_id="990003",
        provider_away_team_id="990004",
        competition_name="Unentitled Competition",
        home_team_name="Unauthorized Home",
        away_team_name="Unauthorized Away",
        payload=unauthorized_payload,
        payload_sha256=hashlib.sha256(unauthorized_raw).hexdigest(),
    )
    unauthorized = store.persist_page(
        response("phase2-ci-not-entitled", (2, 1)),
        [unauthorized_fixture], approval,
    )
    assert unauthorized["quarantined_or_conflicting"] == 1

    revoked_status_response = replace(
        response("phase2-ci-status-revoked", (2, 1)),
        endpoint="/status",
        request_params={"operation": "account_status"},
        fetched_at_utc=now + timedelta(seconds=1),
    )
    revoked_status_record = store.persist_page(revoked_status_response, [], approval)
    store.record_entitlement_observation(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        plan_code="community", entitlement_status="SUSPENDED",
        country_pack_code=None,
        competition_ids=sorted(["3118717965","522514093","4160026622","3614399544","686337048","3405541143","4212821298"]),
        rate_limit_hour=300, rate_limit_minute=20, quota_remaining=0,
        provider_response_id=revoked_status_record["provider_response_id"],
        evidence_sha256=hashlib.sha256(b"phase2-ci-suspended-entitlement").hexdigest(),
        checked_at_utc=now + timedelta(seconds=1),
    )
    suspended = store.persist_page(
        replace(
            response("phase2-ci-page-after-suspension", (2, 1)),
            fetched_at_utc=now + timedelta(seconds=2),
        ),
        [fixture], approval,
    )
    assert suspended["quarantined_or_conflicting"] == 1

    store.revoke_source_approval(
        approval_id=approval.approval_id,
        evidence_uri="https://example.invalid/revocation-evidence",
        evidence_sha256=hashlib.sha256(b"rights-withdrawal-evidence").hexdigest(),
        effective_at_utc=now + timedelta(seconds=3),
        reason_code="RIGHTS_WITHDRAWN",
    )
    revoked_result = store.persist_page(
        replace(response("phase2-ci-page-after-rights-revocation", (2, 1)),
                fetched_at_utc=now + timedelta(seconds=4)),
        [fixture], approval,
    )
    assert revoked_result["quarantined_or_conflicting"] == 1
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM ingestion_quarantine WHERE provider_entity_id='987654321' AND reason_code='SOURCE_APPROVAL_REVOKED_OR_UNVERIFIED'"
            )
            revoked_quarantined = cur.fetchone()[0]
    assert revoked_quarantined == 1

    manifest = hashlib.sha256(
        "\n".join(sorted([fixture.payload_sha256, conflicting_fixture.payload_sha256])).encode()
    ).hexdigest()
    store.upsert_checkpoint(
        import_run_id=run_id, window_start=kickoff, window_end=now,
        cursor_value="page=2", status="COMPLETED", records_seen=2,
        records_inserted=1, records_rejected=0, records_quarantined=1,
        requests_used=2, response_sha256=second_response.response_sha256,
    )
    checkpoint_terminal_rewrite_rejected = False
    try:
        store.upsert_checkpoint(
            import_run_id=run_id, window_start=kickoff, window_end=now,
            cursor_value="page=rewind", status="RUNNING", records_seen=2,
            records_inserted=1, records_rejected=0, records_quarantined=1,
            requests_used=2, response_sha256=second_response.response_sha256,
        )
    except ValueError as exc:
        checkpoint_terminal_rewrite_rejected = str(exc) == "IMPORT_CHECKPOINT_TERMINAL_OR_REGRESSION"
    assert checkpoint_terminal_rewrite_rejected, "terminal checkpoint accepted a rewrite"
    store.finish_import_run(
        import_run_id=run_id, status="COMPLETED", finished_at_utc=now,
        requests_used=2, records_seen=2, records_inserted=1,
        records_rejected=0, records_quarantined=1, manifest_sha256=manifest,
    )
    watermark_v1 = store.advance_sync_watermark(
        provider="5DollarFootballAPI", data_class="fixture_result",
        scope="community-seven-competitions", cursor_value="page=1",
        expected_version=0, updated_at_utc=now,
    )
    watermark_v2 = store.advance_sync_watermark(
        provider="5DollarFootballAPI", data_class="fixture_result",
        scope="community-seven-competitions", cursor_value="page=2",
        expected_version=1, updated_at_utc=now,
    )
    stale_watermark_rejected = False
    try:
        store.advance_sync_watermark(
            provider="5DollarFootballAPI", data_class="fixture_result",
            scope="community-seven-competitions", cursor_value="page=stale",
            expected_version=1, updated_at_utc=now,
        )
    except ValueError as exc:
        stale_watermark_rejected = str(exc) == "SYNC_WATERMARK_VERSION_CONFLICT"
    watermark = store.get_sync_watermark(
        provider="5DollarFootballAPI", data_class="fixture_result",
        scope="community-seven-competitions",
    )

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT home_score,away_score FROM fixture_results WHERE fixture_id = (SELECT id FROM fixtures WHERE provider_fixture_id='987654321')")
            canonical_score = cur.fetchone()
            cur.execute("SELECT count(*) FROM fixture_result_versions WHERE fixture_id = (SELECT id FROM fixtures WHERE provider_fixture_id='987654321')")
            versions = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM ingestion_quarantine WHERE provider_entity_id='987654321' AND reason_code='SETTLED_RESULT_CONFLICT'")
            quarantined = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM ingestion_quarantine WHERE provider_entity_id='987654322' AND reason_code='PROVIDER_COMPETITION_NOT_ENTITLED'")
            entitlement_quarantined = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM ingestion_quarantine WHERE provider_entity_id='987654321' AND reason_code='PROVIDER_ENTITLEMENT_NOT_VERIFIED'")
            suspended_quarantined = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM provider_responses WHERE request_id IN ('phase2-ci-status','phase2-ci-page-1','phase2-ci-page-2','phase2-ci-not-entitled','phase2-ci-status-revoked','phase2-ci-page-after-suspension')")
            responses = cur.fetchone()[0]
            cur.execute("SELECT status,requests_used,records_seen,records_inserted,records_quarantined FROM import_runs WHERE id=%s", (run_id,))
            run_state = cur.fetchone()
            cur.execute("SELECT status,records_seen,records_inserted,records_quarantined,requests_used FROM import_checkpoints WHERE import_run_id=%s", (run_id,))
            checkpoint_state = cur.fetchone()
            cur.execute("SELECT id FROM source_observations WHERE provider_entity_id='987654321' ORDER BY id")
            observation_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM provider_responses WHERE request_id='phase2-ci-page-1'")
            response_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM provider_entitlement_observations WHERE provider='5DollarFootballAPI' AND source_id='5dollarfootballapi' ORDER BY id")
            entitlement_ids = [row[0] for row in cur.fetchall()]
            entitlement_id = entitlement_ids[0]
            entitlement_count = len(entitlement_ids)
            cur.execute("SELECT id FROM fixture_result_versions WHERE fixture_id=(SELECT id FROM fixtures WHERE provider_fixture_id='987654321') ORDER BY id LIMIT 1")
            version_id = cur.fetchone()[0]
    assert canonical_score == (2, 1), canonical_score
    assert versions == 2, versions
    assert quarantined == 1, quarantined
    assert responses == 6, responses
    assert entitlement_quarantined == 1, entitlement_quarantined
    assert suspended_quarantined == 1, suspended_quarantined
    assert entitlement_count == 2, entitlement_count
    assert run_state == ("COMPLETED", 2, 2, 1, 1), run_state
    assert checkpoint_state == ("COMPLETED", 2, 1, 1, 2), checkpoint_state
    assert watermark_v1 == 1 and watermark_v2 == 2
    assert stale_watermark_rejected
    assert watermark[0] == "page=2" and watermark[1] == 2

    # Each raw evidence store must reject mutation at the database layer.
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            mutation_targets = [
                ("provider_responses", "endpoint", response_id),
                ("source_observations", "availability_basis", observation_id),
                ("provider_entitlement_observations", "plan_code", entitlement_id),
                ("fixture_result_versions", "home_score", version_id),
            ]
            for table, column, row_id in mutation_targets:
                cur.execute("SAVEPOINT append_only_probe")
                rejected = False
                try:
                    cur.execute(f"UPDATE {table} SET {column}={column} WHERE id=%s", (row_id,))
                except psycopg.errors.RaiseException:
                    rejected = True
                    cur.execute("ROLLBACK TO SAVEPOINT append_only_probe")
                assert rejected, f"{table} accepted an UPDATE"
                cur.execute("RELEASE SAVEPOINT append_only_probe")

    return {
        "status": "PASS",
        "idempotent_replay": "PASS",
        "result_conflict_quarantined": "PASS",
        "canonical_result_preserved": list(canonical_score),
        "result_versions": versions,
        "quarantine_records": quarantined,
        "provider_response_records": responses,
        "import_run": list(run_state),
        "import_checkpoint": list(checkpoint_state),
        "entitlement_snapshots": entitlement_count,
        "unentitled_competition_quarantined": entitlement_quarantined,
        "suspended_provider_quarantined": suspended_quarantined,
        "sync_watermark_version": watermark[1],
        "stale_sync_writer_rejected": stale_watermark_rejected,
        "altered_approval_replay_rejected": approval_conflict_rejected,
        "terminal_checkpoint_rewrite_rejected": checkpoint_terminal_rewrite_rejected,
        "revoked_source_quarantined": revoked_quarantined,
    }


if __name__ == "__main__":
    print(main())
