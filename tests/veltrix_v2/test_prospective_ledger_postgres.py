from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

import psycopg
from psycopg.types.json import Jsonb
import pytest


UTC = timezone.utc
MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "db" / "migrations" / "free_first"
    / "0001_prospective_evaluation_ledger.sql"
)


@pytest.fixture(scope="module")
def db():
    dsn = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(MIGRATION.read_text(encoding="utf-8"), prepare=False)
        yield conn


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def insert_capture(conn, *, provider="5DollarFootballAPI", source_id="5dollarfootballapi"):
    now = datetime.now(UTC).replace(microsecond=0)
    capture_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO veltrix_eval.capture_runs
        (capture_run_id, provider, source_id, started_at, completed_at,
         request_count, request_budget, provider_scope, attribution, status,
         report_sha256, paid_requests, created_at)
        VALUES (%s,%s,%s,%s,%s,16,24,%s::jsonb,%s::jsonb,'COMPLETED',%s,0,%s)
        """,
        (
            capture_id, provider, source_id, now, now + timedelta(seconds=1),
            json.dumps({"competitions": ["4160026622"]}),
            json.dumps({"text": "5DollarFootballAPI", "url": "https://5dollarfootballapi.com"}),
            digest("capture-report"), now + timedelta(seconds=2),
        ),
    )
    return capture_id, now


def insert_snapshot(conn, capture_id, now, *, status="SCHEDULED",
                    provider="5DollarFootballAPI", source_id="5dollarfootballapi",
                    fixture_id="fixture-1", competition_id="4160026622",
                    home_id="101", away_id="102"):
    snapshot_id = uuid.uuid4()
    kickoff = now + timedelta(hours=3)
    finished = status == "FINISHED"
    retrieved = now + timedelta(seconds=1)
    available = kickoff + timedelta(days=4) if finished else None
    if finished:
        retrieved = available + timedelta(minutes=1)
    conn.execute(
        """
        INSERT INTO veltrix_eval.fixture_snapshots
        (snapshot_id,capture_run_id,provider,source_id,provider_fixture_id,
         provider_competition_id,provider_home_team_id,provider_away_team_id,
         competition_name,home_team_name,away_team_name,kickoff_at,source_status,
         home_goals,away_goals,retrieved_at,available_at,availability_basis,
         point_in_time_certifiable,payload_sha256,rights_approval_id,created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Test League','Home FC','Away FC',%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            snapshot_id, capture_id, provider, source_id, fixture_id,
            competition_id, home_id, away_id, kickoff, status,
            2 if finished else None, 1 if finished else None,
            retrieved, available,
            "provider_finished_status_conservative_4d" if finished else "scheduled_snapshot",
            False, digest(f"payload-{fixture_id}"), "approval-test",
            retrieved + timedelta(seconds=1),
        ),
    )
    return snapshot_id, kickoff, retrieved


def insert_batch(conn, now, *, model_version="poisson-v1", config_sha=None):
    batch_id = uuid.uuid4()
    config_sha = config_sha or digest("model-config")
    cutoff = now + timedelta(seconds=3)
    generated = cutoff + timedelta(seconds=1)
    conn.execute(
        """
        INSERT INTO veltrix_eval.prediction_batches
        (batch_id,cutoff_at,generated_at,model_version,model_config,
         model_config_sha256,source_manifest_sha256,requested_target_count,
         forecast_count,publication_locked,created_at)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,1,1,TRUE,%s)
        """,
        (batch_id, cutoff, generated, model_version, json.dumps({"rho": 0.0}),
         config_sha, digest("source-manifest"), generated + timedelta(seconds=1)),
    )
    return batch_id, cutoff, model_version, config_sha


def insert_prediction(conn, batch_id, snapshot_id, kickoff, retrieved, cutoff,
                      model_version, config_sha, *, publishable=False,
                      fixture_id="5dollarfootballapi:fixture-1"):
    prediction_id = uuid.uuid4()
    conn.execute(
        """
        INSERT INTO veltrix_eval.prediction_records
        (prediction_id,batch_id,target_snapshot_id,fixture_id,competition_id,
         home_team_id,away_team_id,kickoff_at,target_retrieved_at,cutoff_at,
         expected_home_goals,expected_away_goals,home_win,draw,away_win,
         btts_yes,over_2_5,evidence_match_count,home_team_match_count,
         away_team_match_count,sample_floor_met,publishable,publication_reason,
         model_version,model_config_sha256,created_at)
        VALUES (%s,%s,%s,%s,'5dollarfootballapi:4160026622',
                '5dollarfootballapi:101','5dollarfootballapi:102',%s,%s,%s,
                1.25,1.05,0.45,0.28,0.27,0.52,0.48,100,12,11,TRUE,%s,
                'MODEL_NOT_CERTIFIED',%s,%s,%s)
        """,
        (
            prediction_id, batch_id, snapshot_id, fixture_id, kickoff,
            retrieved, cutoff, publishable, model_version, config_sha,
            cutoff + timedelta(seconds=2),
        ),
    )
    return prediction_id


def test_migration_is_idempotent_and_creates_isolated_schema(db):
    db.execute(MIGRATION.read_text(encoding="utf-8"), prepare=False)
    schemas = db.execute(
        "SELECT schema_name FROM information_schema.schemata WHERE schema_name='veltrix_eval'"
    ).fetchall()
    assert schemas == [("veltrix_eval",)]
    tables = db.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='veltrix_eval'"
    ).fetchall()
    assert {row[0] for row in tables} == {
        "schema_migrations", "capture_runs", "fixture_snapshots",
        "prediction_batches", "prediction_records", "result_settlements",
        "evaluation_runs",
    }


def test_append_only_capture_prediction_settlement_and_evaluation_records(db):
    capture_id, now = insert_capture(db)
    snapshot_id, kickoff, retrieved = insert_snapshot(db, capture_id, now)
    batch_id, cutoff, model_version, config_sha = insert_batch(db, now)
    prediction_id = insert_prediction(
        db, batch_id, snapshot_id, kickoff, retrieved, cutoff, model_version, config_sha
    )

    recorded = datetime.now(UTC).replace(microsecond=0) + timedelta(days=5)
    db.execute(
        """
        INSERT INTO veltrix_eval.result_settlements
        (settlement_id,prediction_id,settlement_revision,result_provider,
         result_source_id,provider_fixture_id,home_goals,away_goals,
         result_available_at,recorded_at,settled_at,payload_sha256,created_at)
        VALUES (%s,%s,1,'5DollarFootballAPI','5dollarfootballapi','fixture-1',
                2,1,%s,%s,%s,%s,%s)
        """,
        (
            uuid.uuid4(), prediction_id, recorded - timedelta(minutes=2),
            recorded, recorded - timedelta(minutes=1), digest("settlement"),
            recorded + timedelta(seconds=1),
        ),
    )
    evaluated_at = recorded + timedelta(minutes=1)
    db.execute(
        """
        INSERT INTO veltrix_eval.evaluation_runs
        (evaluation_id,model_version,model_config_sha256,evaluation_as_of,
         dataset_manifest_sha256,eligible_fixture_count,scored_fixture_count,
         brier_score,log_loss,baseline_brier_score,baseline_log_loss,
         metrics,publication_locked,created_at)
        VALUES (%s,%s,%s,%s,%s,1,1,0.20,0.61,0.22,0.65,%s::jsonb,TRUE,%s)
        """,
        (
            uuid.uuid4(), model_version, config_sha, evaluated_at,
            digest("evaluation-dataset"), json.dumps({"dates": 1}),
            evaluated_at + timedelta(seconds=1),
        ),
    )

    assert db.execute("SELECT count(*) FROM veltrix_eval.capture_runs").fetchone()[0] >= 1
    assert db.execute("SELECT count(*) FROM veltrix_eval.prediction_records").fetchone()[0] >= 1
    assert db.execute("SELECT count(*) FROM veltrix_eval.result_settlements").fetchone()[0] >= 1
    assert db.execute("SELECT count(*) FROM veltrix_eval.evaluation_runs").fetchone()[0] >= 1

    for statement in (
        "UPDATE veltrix_eval.capture_runs SET status='FAILED'",
        "DELETE FROM veltrix_eval.fixture_snapshots",
        "UPDATE veltrix_eval.prediction_records SET publishable=TRUE",
        "DELETE FROM veltrix_eval.result_settlements",
        "UPDATE veltrix_eval.evaluation_runs SET publication_locked=FALSE",
    ):
        with pytest.raises(psycopg.Error) as exc:
            db.execute(statement)
        assert exc.value.sqlstate == "55000"


def test_snapshot_must_match_capture_source_identity(db):
    capture_id, now = insert_capture(db)
    with pytest.raises(psycopg.Error) as exc:
        insert_snapshot(db, capture_id, now, source_id="different-source")
    assert exc.value.sqlstate == "23514"


def test_prediction_must_reference_scheduled_target_and_matching_batch_config(db):
    capture_id, now = insert_capture(db)
    finished_id, kickoff, retrieved = insert_snapshot(
        db, capture_id, now, status="FINISHED"
    )
    batch_id, cutoff, model_version, config_sha = insert_batch(db, now)
    with pytest.raises(psycopg.Error) as exc:
        insert_prediction(
            db, batch_id, finished_id, kickoff, retrieved, cutoff,
            model_version, config_sha, fixture_id="5dollarfootballapi:fixture-1"
        )
    assert exc.value.sqlstate == "23514"

    scheduled_id, kickoff, retrieved = insert_snapshot(
        db, capture_id, now, fixture_id="fixture-2"
    )
    with pytest.raises(psycopg.Error) as exc:
        insert_prediction(
            db, batch_id, scheduled_id, kickoff, retrieved, cutoff,
            "wrong-model-version", config_sha, fixture_id="5dollarfootballapi:fixture-2"
        )
    assert exc.value.sqlstate == "23514"


def test_database_rejects_publishable_rows_and_bad_probability_sum(db):
    capture_id, now = insert_capture(db)
    snapshot_id, kickoff, retrieved = insert_snapshot(
        db, capture_id, now, fixture_id="fixture-3"
    )
    batch_id, cutoff, model_version, config_sha = insert_batch(db, now)

    with pytest.raises(psycopg.Error) as exc:
        insert_prediction(
            db, batch_id, snapshot_id, kickoff, retrieved, cutoff,
            model_version, config_sha, publishable=True,
            fixture_id="5dollarfootballapi:fixture-3"
        )
    assert exc.value.sqlstate == "23514"

    with pytest.raises(psycopg.Error) as exc:
        db.execute(
            """
            INSERT INTO veltrix_eval.prediction_records
            (prediction_id,batch_id,target_snapshot_id,fixture_id,competition_id,
             home_team_id,away_team_id,kickoff_at,target_retrieved_at,cutoff_at,
             expected_home_goals,expected_away_goals,home_win,draw,away_win,
             btts_yes,over_2_5,evidence_match_count,home_team_match_count,
             away_team_match_count,sample_floor_met,publishable,publication_reason,
             model_version,model_config_sha256,created_at)
            VALUES (%s,%s,%s,'5dollarfootballapi:fixture-3','5dollarfootballapi:4160026622',
                    '5dollarfootballapi:101','5dollarfootballapi:102',%s,%s,%s,
                    1.2,1.1,0.6,0.3,0.2,0.5,0.5,10,5,5,FALSE,FALSE,
                    'MODEL_NOT_CERTIFIED',%s,%s,%s)
            """,
            (
                uuid.uuid4(), batch_id, snapshot_id, kickoff, retrieved, cutoff,
                model_version, config_sha, cutoff + timedelta(seconds=3),
            ),
        )
    assert exc.value.sqlstate == "23514"
