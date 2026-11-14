"""Read-only inspection of uncertain Telegram delivery claims and evidence.

This adapter has no insert/update/delete operations and no Telegram transport.
Production use is intentionally excluded; the CLI wrapper allowlists staging.
"""
from __future__ import annotations

import re
from typing import Any, Callable


_HASH = re.compile(r"^[0-9a-f]{64}$")


class PostgresTelegramReconciliationReader:
    """Read one claim and its append-only reconciliation history."""

    def __init__(self, connect: Callable):
        if not callable(connect):
            raise ValueError("RECONCILIATION_READ_CONNECT_FACTORY_REQUIRED")
        self._connect = connect

    def inspect(self, idempotency_key: str) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not _HASH.fullmatch(idempotency_key):
            raise ValueError("DELIVERY_IDEMPOTENCY_KEY_INVALID")
        with self._connect() as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            identity = connection.execute(
                "SELECT current_database(), current_user"
            ).fetchone()
            if identity != ("veltrix_football_staging", "neondb_owner"):
                raise PermissionError("RECONCILIATION_READER_TARGET_NOT_ALLOWLISTED")
            claim_row = connection.execute(
                """
                SELECT idempotency_key, report_id, report_sha256,
                       destination_sha256, state, reason_code,
                       claimed_at, updated_at, telegram_message_ids
                FROM telegram_delivery_claims
                WHERE idempotency_key=%s
                """,
                (idempotency_key,),
            ).fetchone()
            if claim_row is None:
                raise ValueError("TELEGRAM_DELIVERY_CLAIM_NOT_FOUND")
            claim = dict(zip(
                (
                    "idempotency_key", "report_id", "report_sha256",
                    "destination_sha256", "state", "reason_code",
                    "claimed_at", "updated_at", "telegram_message_ids",
                ),
                claim_row,
            ))
            rows = connection.execute(
                """
                SELECT reconciliation_id::text, outcome, telegram_message_ids,
                       evidence_uri, evidence_sha256, evidence_kind, operator_id,
                       reviewer_id, observed_at, recorded_at, reason_code,
                       supersedes_reconciliation_id::text
                FROM telegram_delivery_reconciliations
                WHERE idempotency_key=%s
                ORDER BY recorded_at, reconciliation_id
                """,
                (idempotency_key,),
            ).fetchall()
            events = [
                dict(zip(
                    (
                        "reconciliation_id", "outcome", "telegram_message_ids",
                        "evidence_uri", "evidence_sha256", "evidence_kind",
                        "operator_id", "reviewer_id", "observed_at", "recorded_at",
                        "reason_code", "supersedes_reconciliation_id",
                    ),
                    row,
                ))
                for row in rows
            ]
        return {
            "status": "READ_ONLY_RECONCILIATION_INSPECTION",
            "claim": claim,
            "reconciliation_events": events,
            "side_effects": {
                "database_writes": 0,
                "telegram_requests": 0,
                "retry_authorizations": 0,
            },
        }
