"""Guarded PostgreSQL adapter for the append-only paper ledger.

Reads are limited to allowlisted staging/test targets. Writes require an
explicit write_enabled=True. PostgreSQL independently enforces append-only
storage, sequence continuity and settlement-to-prediction linkage; the
application verifies the full event hash chain before every append.
"""
from __future__ import annotations

import json
from typing import Any

from veltrix_v2.ledger.paper_predictions import (
    PaperLedgerEvent,
    PaperPrediction,
    ProspectivePaperLedger,
)


STAGING_TARGET = {
    "environment": "staging",
    "database_name": "veltrix_football_staging",
    "host": "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech",
    "role": "neondb_owner",
}
TEST_TARGET = {
    "environment": "test",
    "database_name": "veltrix_reservation_test",
    "host": "localhost",
    "role": "postgres",
}


class PostgresPaperLedgerStore:
    def __init__(
        self,
        connection: Any,
        *,
        ledger_id: str,
        write_enabled: bool = False,
        environment: str = "",
        database_name: str = "",
        host: str = "",
        role: str = "",
        test_mode: bool = False,
    ) -> None:
        if not isinstance(ledger_id, str) or not ledger_id.strip():
            raise ValueError("PAPER_LEDGER_ID_INVALID")
        self.connection = connection
        self.ledger_id = ledger_id
        self.write_enabled = write_enabled
        self.environment = environment
        self.database_name = database_name
        self.host = host
        self.role = role
        self.test_mode = test_mode

    def _assert_target(self, *, write: bool) -> None:
        if write and self.write_enabled is not True:
            raise PermissionError("PAPER_LEDGER_WRITE_DISABLED")
        if self.environment == "staging":
            expected = STAGING_TARGET
        elif self.environment == "test" and self.test_mode is True:
            expected = TEST_TARGET
        else:
            raise PermissionError("PAPER_LEDGER_TARGET_NOT_ALLOWLISTED")
        actual = {
            "environment": self.environment,
            "database_name": self.database_name,
            "host": self.host,
            "role": self.role,
        }
        if actual != expected:
            raise PermissionError("PAPER_LEDGER_TARGET_NOT_ALLOWLISTED")
        identity = self.connection.execute(
            "SELECT current_database(), current_user"
        ).fetchone()
        if identity != (self.database_name, self.role):
            raise PermissionError("PAPER_LEDGER_CONNECTION_IDENTITY_MISMATCH")

    def _load_events(self) -> list[PaperLedgerEvent]:
        rows = self.connection.execute(
            """
            SELECT sequence, event_type, fixture_id, model_version, recorded_at,
                   payload, previous_event_sha256, event_sha256
            FROM paper_ledger_events
            WHERE ledger_id = %s
            ORDER BY sequence
            """,
            (self.ledger_id,),
        ).fetchall()
        events = []
        for row in rows:
            payload = row[5]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict):
                raise ValueError("PAPER_LEDGER_STORED_PAYLOAD_INVALID")
            events.append(PaperLedgerEvent(
                sequence=int(row[0]),
                event_type=str(row[1]),
                fixture_id=str(row[2]),
                model_version=str(row[3]),
                recorded_at=str(row[4]),
                payload=payload,
                previous_event_sha256=str(row[6]).strip(),
                event_sha256=str(row[7]).strip(),
            ))
        return events

    def load(self) -> ProspectivePaperLedger:
        self._assert_target(write=False)
        return ProspectivePaperLedger(self._load_events())

    def _begin_append(self) -> ProspectivePaperLedger:
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (self.ledger_id,),
        )
        return ProspectivePaperLedger(self._load_events())

    def _insert_event(self, event: PaperLedgerEvent) -> None:
        self.connection.execute(
            """
            INSERT INTO paper_ledger_events (
                ledger_id, sequence, event_type, fixture_id, model_version,
                recorded_at, payload, previous_event_sha256, event_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
            """,
            (
                self.ledger_id,
                event.sequence,
                event.event_type,
                event.fixture_id,
                event.model_version,
                event.recorded_at,
                json.dumps(
                    event.payload, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False,
                ),
                event.previous_event_sha256,
                event.event_sha256,
            ),
        )

    def append_prediction(self, prediction: PaperPrediction) -> PaperLedgerEvent:
        self._assert_target(write=True)
        with self.connection.transaction():
            ledger = self._begin_append()
            event = ledger.append_prediction(prediction)
            self._insert_event(event)
            return event

    def append_predictions(
        self, predictions: list[PaperPrediction]
    ) -> list[PaperLedgerEvent]:
        """Append a batch atomically; any invalid or duplicate row rolls back all."""
        if not isinstance(predictions, list) or not predictions:
            raise ValueError("PAPER_LEDGER_PREDICTION_BATCH_INVALID")
        self._assert_target(write=True)
        with self.connection.transaction():
            ledger = self._begin_append()
            events = []
            for prediction in predictions:
                event = ledger.append_prediction(prediction)
                self._insert_event(event)
                events.append(event)
            return events

    def append_settlement(self, **kwargs: Any) -> PaperLedgerEvent:
        self._assert_target(write=True)
        with self.connection.transaction():
            ledger = self._begin_append()
            event = ledger.append_settlement(**kwargs)
            self._insert_event(event)
            return event
