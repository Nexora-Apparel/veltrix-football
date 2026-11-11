"""Audit contract for Telegram's actual 06:00 WAT delivery receipts.

The receipt timestamp must come from Telegram's returned Message.date (server
time), not the worker's local clock. This validator does not send messages.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
import re
from typing import Iterable
from zoneinfo import ZoneInfo

WAT = ZoneInfo("Africa/Lagos")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class TelegramDeliveryReceipt:
    report_date_wat: str
    message_id: int
    destination_fingerprint: str
    delivered_at_utc: datetime
    report_sha256: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.report_date_wat, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.report_date_wat):
            raise ValueError("DELIVERY_REPORT_DATE_INVALID")
        if isinstance(self.message_id, bool) or not isinstance(self.message_id, int) or self.message_id <= 0:
            raise ValueError("DELIVERY_MESSAGE_ID_INVALID")
        if not isinstance(self.destination_fingerprint, str) or not self.destination_fingerprint.strip():
            raise ValueError("DELIVERY_DESTINATION_FINGERPRINT_REQUIRED")
        if not isinstance(self.delivered_at_utc, datetime) or self.delivered_at_utc.tzinfo is None or self.delivered_at_utc.utcoffset() is None:
            raise ValueError("DELIVERY_TIMESTAMP_MUST_BE_AWARE")
        object.__setattr__(self, "delivered_at_utc", self.delivered_at_utc.astimezone(timezone.utc))
        if not isinstance(self.report_sha256, str) or not _SHA256.fullmatch(self.report_sha256):
            raise ValueError("DELIVERY_REPORT_HASH_INVALID")
        if not isinstance(self.idempotency_key, str) or not self.idempotency_key.strip():
            raise ValueError("DELIVERY_IDEMPOTENCY_KEY_REQUIRED")


@dataclass(frozen=True, slots=True)
class DeliveryAuditResult:
    passed: bool
    report_date_wat: str
    expected_chunks: int
    received_chunks: int
    first_delivery_wat: str | None
    last_delivery_wat: str | None
    failures: tuple[str, ...]


def verify_telegram_delivery(
    receipts: Iterable[TelegramDeliveryReceipt],
    *,
    report_date_wat: str,
    expected_chunks: int,
    expected_report_sha256: str,
    expected_destination_fingerprint: str,
) -> DeliveryAuditResult:
    if isinstance(expected_chunks, bool) or not isinstance(expected_chunks, int) or expected_chunks < 1:
        raise ValueError("DELIVERY_EXPECTED_CHUNKS_INVALID")
    if not _SHA256.fullmatch(expected_report_sha256):
        raise ValueError("DELIVERY_EXPECTED_REPORT_HASH_INVALID")
    rows = tuple(receipts)
    failures: list[str] = []
    if len(rows) != expected_chunks:
        failures.append("CHUNK_COUNT_MISMATCH")
    if not rows:
        return DeliveryAuditResult(
            passed=False,
            report_date_wat=report_date_wat,
            expected_chunks=expected_chunks,
            received_chunks=0,
            first_delivery_wat=None,
            last_delivery_wat=None,
            failures=tuple(failures + ["NO_TELEGRAM_RECEIPTS"]),
        )
    ids = [row.message_id for row in rows]
    keys = [row.idempotency_key for row in rows]
    if len(ids) != len(set(ids)):
        failures.append("DUPLICATE_TELEGRAM_MESSAGE_ID")
    if len(keys) != len(set(keys)):
        failures.append("DUPLICATE_IDEMPOTENCY_KEY")
    for row in rows:
        if row.report_date_wat != report_date_wat:
            failures.append("REPORT_DATE_MISMATCH")
        if row.report_sha256 != expected_report_sha256:
            failures.append("REPORT_HASH_MISMATCH")
        if row.destination_fingerprint != expected_destination_fingerprint:
            failures.append("DESTINATION_MISMATCH")
        local = row.delivered_at_utc.astimezone(WAT)
        if local.date().isoformat() != report_date_wat:
            failures.append("DELIVERY_LOCAL_DATE_MISMATCH")
        if not (time(6, 0, 0) <= local.timetz().replace(tzinfo=None) < time(6, 1, 0)):
            failures.append("DELIVERY_OUTSIDE_0600_WAT_MINUTE")
    local_times = sorted(row.delivered_at_utc.astimezone(WAT) for row in rows)
    return DeliveryAuditResult(
        passed=not failures,
        report_date_wat=report_date_wat,
        expected_chunks=expected_chunks,
        received_chunks=len(rows),
        first_delivery_wat=local_times[0].isoformat(),
        last_delivery_wat=local_times[-1].isoformat(),
        failures=tuple(dict.fromkeys(failures)),
    )
