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
        competition_scope="*",
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

    store = PostgresHistoryStore(lambda: psycopg.connect(database_url))
    first_response = response("phase2-ci-page-1", (2, 1))
    first = store.persist_page(first_response, [fixture], approval)
    repeated = store.persist_page(first_response, [fixture], approval)
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
    conflict = store.persist_page(response("phase2-ci-page-2", (3, 1)), [conflicting_fixture], approval)
    assert conflict["result_versions_inserted"] == 1
    assert conflict["results_inserted"] == 0
    assert conflict["quarantined_or_conflicting"] == 1

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT home_score,away_score FROM fixture_results WHERE fixture_id = (SELECT id FROM fixtures WHERE provider_fixture_id='987654321')")
            canonical_score = cur.fetchone()
            cur.execute("SELECT count(*) FROM fixture_result_versions WHERE fixture_id = (SELECT id FROM fixtures WHERE provider_fixture_id='987654321')")
            versions = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM ingestion_quarantine WHERE provider_entity_id='987654321' AND reason_code='SETTLED_RESULT_CONFLICT'")
            quarantined = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM provider_responses WHERE request_id IN ('phase2-ci-page-1','phase2-ci-page-2')")
            responses = cur.fetchone()[0]
    assert canonical_score == (2, 1), canonical_score
    assert versions == 2, versions
    assert quarantined == 1, quarantined
    assert responses == 2, responses
    return {
        "status": "PASS",
        "idempotent_replay": "PASS",
        "result_conflict_quarantined": "PASS",
        "canonical_result_preserved": list(canonical_score),
        "result_versions": versions,
        "quarantine_records": quarantined,
        "provider_response_records": responses,
    }


if __name__ == "__main__":
    print(main())
