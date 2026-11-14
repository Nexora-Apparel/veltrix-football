from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
import os
import uuid

import psycopg
import pytest

from veltrix_v2.ledger.paper_predictions import PaperPrediction
from veltrix_v2.ledger.postgres_store import PostgresPaperLedgerStore

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def dsn():
    return os.environ["DATABASE_URL"]


@pytest.fixture(scope="session", autouse=True)
def create_paper_ledger_schema(dsn):
    migration = Path("db/migrations/0008_prospective_paper_ledger.sql").read_text()
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(migration)


def make_prediction(fixture_id, *, offset_seconds=1):
    return PaperPrediction(
        fixture_id=fixture_id,
        competition_id="competition-1",
        home_team_id="team-home",
        away_team_id="team-away",
        kickoff_at=NOW + timedelta(days=2),
        prediction_cutoff_at=NOW,
        forecasted_at=NOW + timedelta(seconds=offset_seconds),
        recorded_at=NOW + timedelta(seconds=offset_seconds + 1),
        model_version="poisson-results-v2",
        home_probability=0.48,
        draw_probability=0.27,
        away_probability=0.25,
        evidence_sha256="a" * 64,
        point_in_time_certifiable=False,
        evidence_class="PROSPECTIVE_OBSERVED_ONLY",
    )


def make_store(connection, ledger_id, *, write_enabled=True):
    return PostgresPaperLedgerStore(
        connection,
        ledger_id=ledger_id,
        write_enabled=write_enabled,
        environment="test",
        database_name="veltrix_reservation_test",
        host="localhost",
        role="postgres",
        test_mode=True,
    )


def test_append_and_reload_verifies_hash_chain(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"
    with psycopg.connect(dsn) as connection:
        store = make_store(connection, ledger_id)
        first = store.append_prediction(make_prediction("fixture-1"))
        second = store.append_prediction(make_prediction("fixture-2", offset_seconds=3))
        loaded = store.load()
        assert [event.sequence for event in loaded.events] == [1, 2]
        assert loaded.events[0] == first
        assert loaded.events[1] == second
        assert second.previous_event_sha256 == first.event_sha256
        assert loaded.verify_chain()


def test_settlement_event_round_trips_and_links_prediction(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"
    with psycopg.connect(dsn) as connection:
        store = make_store(connection, ledger_id)
        prediction = store.append_prediction(make_prediction("fixture-settle"))
        kickoff = NOW + timedelta(days=2)
        available = kickoff + timedelta(minutes=5)
        retrieved = available
        recorded = retrieved + timedelta(seconds=1)
        settlement = store.append_settlement(
            fixture_id="fixture-settle",
            model_version="poisson-results-v2",
            home_goals=2,
            away_goals=1,
            result_available_at=available,
            result_retrieved_at=retrieved,
            recorded_at=recorded,
            source_provider="5DollarFootballAPI",
            source_id="5dollarfootballapi",
            source_fixture_id="provider-fixture-1",
            result_payload_sha256="c" * 64,
            rights_approval_id="approval-test",
            rights_evidence_sha256="d" * 64,
            result_availability_basis="collector_first_observed_v1",
            settlement_delay_basis="collector_first_observed",
        )
        loaded = store.load()
        assert len(loaded.events) == 2
        assert loaded.events[0] == prediction
        assert loaded.events[1] == settlement
        assert settlement.payload["prediction_event_sha256"] == prediction.event_sha256
        assert loaded.verify_chain()


def test_settlement_without_matching_prediction_is_rejected(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"
    with psycopg.connect(dsn) as connection:
        store = make_store(connection, ledger_id)
        kickoff = NOW + timedelta(days=2)
        with pytest.raises(ValueError, match="PAPER_SETTLEMENT_WITHOUT_PREDICTION"):
            store.append_settlement(
                fixture_id="fixture-no-prediction",
                model_version="poisson-results-v2",
                home_goals=0,
                away_goals=0,
                result_available_at=kickoff,
                result_retrieved_at=kickoff + timedelta(minutes=1),
                recorded_at=kickoff + timedelta(minutes=2),
                source_provider="5DollarFootballAPI",
                source_id="5dollarfootballapi",
                source_fixture_id="provider-fixture-2",
                result_payload_sha256="c" * 64,
                rights_approval_id="approval-test",
                rights_evidence_sha256="d" * 64,
            )


def test_database_rejects_broken_sequence_or_previous_hash(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"
    with psycopg.connect(dsn) as connection:
        with pytest.raises(psycopg.Error, match="PAPER_LEDGER_INITIAL_EVENT_INVALID"):
            connection.execute(
                """
                INSERT INTO paper_ledger_events (
                    ledger_id, sequence, event_type, fixture_id, model_version,
                    recorded_at, payload, previous_event_sha256, event_sha256
                ) VALUES (%s, 2, 'SHADOW_PREDICTION', 'fixture-invalid',
                          'poisson-results-v2', %s, '{}'::jsonb, %s, %s)
                """,
                (ledger_id, NOW.isoformat(), "1" * 64, "f" * 64),
            )


def test_duplicate_fixture_model_prediction_is_rejected(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"
    with psycopg.connect(dsn) as connection:
        store = make_store(connection, ledger_id)
        store.append_prediction(make_prediction("fixture-duplicate"))
        with pytest.raises(ValueError, match="PAPER_PREDICTION_DUPLICATE"):
            store.append_prediction(make_prediction("fixture-duplicate", offset_seconds=3))


def test_write_disabled_and_wrong_target_fail_closed(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"
    with psycopg.connect(dsn) as connection:
        read_only = make_store(connection, ledger_id, write_enabled=False)
        with pytest.raises(PermissionError, match="PAPER_LEDGER_WRITE_DISABLED"):
            read_only.append_prediction(make_prediction("fixture-readonly"))
        wrong_target = PostgresPaperLedgerStore(
            connection, ledger_id=ledger_id, write_enabled=True,
            environment="staging", database_name="veltrix_football_production",
            host="localhost", role="postgres",
        )
        with pytest.raises(PermissionError, match="PAPER_LEDGER_TARGET_NOT_ALLOWLISTED"):
            wrong_target.append_prediction(make_prediction("fixture-wrong-target"))


def test_append_only_triggers_block_update_delete_and_truncate(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"
    with psycopg.connect(dsn) as connection:
        store = make_store(connection, ledger_id)
        store.append_prediction(make_prediction("fixture-immutable"))

    statements = [
        ("UPDATE paper_ledger_events SET model_version='changed' WHERE ledger_id=%s", (ledger_id,)),
        ("DELETE FROM paper_ledger_events WHERE ledger_id=%s", (ledger_id,)),
        ("TRUNCATE paper_ledger_events", ()),
    ]
    for sql, params in statements:
        with psycopg.connect(dsn, autocommit=True) as connection:
            with pytest.raises(psycopg.Error, match="PAPER_LEDGER_APPEND_ONLY"):
                connection.execute(sql, params)


def test_concurrent_appends_are_serialized_by_ledger_advisory_lock(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"

    def append(fixture_id, offset):
        with psycopg.connect(dsn) as connection:
            return make_store(connection, ledger_id).append_prediction(
                make_prediction(fixture_id, offset_seconds=offset)
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda args: append(*args),
            [("fixture-concurrent-a", 1), ("fixture-concurrent-b", 3)],
        ))

    with psycopg.connect(dsn) as connection:
        loaded = make_store(connection, ledger_id).load()
        assert [event.sequence for event in loaded.events] == [1, 2]
        assert {event.fixture_id for event in loaded.events} == {
            "fixture-concurrent-a", "fixture-concurrent-b"
        }
        assert loaded.verify_chain()


def test_loader_detects_tampered_event_hash(dsn):
    ledger_id = f"test-ledger-{uuid.uuid4()}"
    with psycopg.connect(dsn) as connection:
        connection.execute(
            """
            INSERT INTO paper_ledger_events (
                ledger_id, sequence, event_type, fixture_id, model_version,
                recorded_at, payload, previous_event_sha256, event_sha256
            ) VALUES (%s, 1, 'SHADOW_PREDICTION', 'fixture-tampered',
                      'poisson-results-v2', %s, '{}'::jsonb, %s, %s)
            """,
            (ledger_id, NOW.isoformat(), "0" * 64, "f" * 64),
        )
    with psycopg.connect(dsn) as connection:
        with pytest.raises(ValueError, match="PAPER_LEDGER_EVENT_HASH_INVALID"):
            make_store(connection, ledger_id).load()
