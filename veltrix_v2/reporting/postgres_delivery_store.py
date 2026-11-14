"""PostgreSQL implementation of the durable Telegram delivery claim store."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Callable

from veltrix_v2.reporting.delivery import DeliveryReceipt


_HASH = re.compile(r"^[0-9a-f]{64}$")


class PostgresTelegramDeliveryStore:
    """Atomic idempotency claims; destination identifiers are stored only as hashes."""

    def __init__(self, connect: Callable):
        if not callable(connect):
            raise ValueError("DATABASE_CONNECT_FACTORY_REQUIRED")
        self._connect = connect

    def claim(self, key: str, destination: str) -> bool:
        if not isinstance(key, str) or not _HASH.fullmatch(key):
            raise ValueError("DELIVERY_IDEMPOTENCY_KEY_INVALID")
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("DELIVERY_DESTINATION_REQUIRED")
        destination_hash = hashlib.sha256(destination.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO telegram_delivery_claims (
                    idempotency_key, report_id, report_sha256, destination_sha256
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING idempotency_key
                """,
                (key, "bound-by-idempotency-key", "0" * 64, destination_hash),
            ).fetchone()
        return row is not None

    def claim_report(
        self, key: str, report_id: str, report_sha256: str, destination: str
    ) -> bool:
        """Claim while persisting the full immutable report identity."""
        if not isinstance(key, str) or not _HASH.fullmatch(key):
            raise ValueError("DELIVERY_IDEMPOTENCY_KEY_INVALID")
        if not isinstance(report_id, str) or not report_id.strip():
            raise ValueError("DELIVERY_REPORT_ID_REQUIRED")
        if not isinstance(report_sha256, str) or not _HASH.fullmatch(report_sha256):
            raise ValueError("DELIVERY_REPORT_HASH_INVALID")
        if not isinstance(destination, str) or not destination.strip():
            raise ValueError("DELIVERY_DESTINATION_REQUIRED")
        destination_hash = hashlib.sha256(destination.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO telegram_delivery_claims (
                    idempotency_key, report_id, report_sha256, destination_sha256
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING idempotency_key
                """,
                (key, report_id, report_sha256, destination_hash),
            ).fetchone()
        return row is not None

    def mark_sent(self, key: str, receipt: DeliveryReceipt) -> None:
        if not isinstance(receipt, DeliveryReceipt):
            raise ValueError("DELIVERY_RECEIPT_REQUIRED")
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE telegram_delivery_claims
                SET state='SENT', updated_at=NOW(),
                    telegram_message_ids=%s::jsonb
                WHERE idempotency_key=%s AND state='CLAIMED'
                RETURNING idempotency_key
                """,
                (json.dumps(list(receipt.message_ids)), key),
            ).fetchone()
        if row is None:
            raise ValueError("DELIVERY_CLAIM_NOT_ACTIVE")

    def mark_unknown(self, key: str, reason_code: str) -> None:
        if not isinstance(reason_code, str) or not reason_code.strip():
            reason_code = "DELIVERY_OUTCOME_UNKNOWN"
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE telegram_delivery_claims
                SET state='OUTCOME_UNKNOWN', updated_at=NOW(), reason_code=%s
                WHERE idempotency_key=%s AND state='CLAIMED'
                RETURNING idempotency_key
                """,
                (reason_code[:128], key),
            ).fetchone()
        if row is None:
            raise ValueError("DELIVERY_CLAIM_NOT_ACTIVE")
