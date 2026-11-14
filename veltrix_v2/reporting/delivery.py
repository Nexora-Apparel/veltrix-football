"""At-most-once Telegram dispatch boundary with explicit uncertain outcomes.

The store must implement atomic durable claims. This module deliberately has
no network client and never retries an uncertain Telegram send.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from veltrix_v2.reporting.report_identity import (
    ReportIdentity,
    delivery_idempotency_key,
)


class DeliveryState(str, Enum):
    CLAIMED = "CLAIMED"
    SENT = "SENT"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    DUPLICATE_SKIPPED = "DUPLICATE_SKIPPED"


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    destination: str
    message_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.destination.strip() or not self.message_ids:
            raise ValueError("delivery receipt requires destination and message IDs")
        if any(not value or not value.strip() for value in self.message_ids):
            raise ValueError("delivery receipt contains an empty message ID")


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    idempotency_key: str
    state: DeliveryState
    receipt: DeliveryReceipt | None = None


class DeliveryStore(Protocol):
    """Implementations must make claim() atomic across workers and restarts."""

    def claim(self, key: str, report_id: str, report_sha256: str, destination: str) -> bool: ...
    def mark_sent(self, key: str, receipt: DeliveryReceipt) -> None: ...
    def mark_unknown(self, key: str, reason_code: str) -> None: ...


class DeliveryOutcomeUnknown(RuntimeError):
    """The request may have reached Telegram; automatic retry is prohibited."""


def deliver_once(
    identity: ReportIdentity,
    destination: str,
    store: DeliveryStore,
    send: Callable[[], DeliveryReceipt],
) -> DeliveryAttempt:
    """Claim before sending; never resend a claimed or uncertain report.

    A crash after claim but before send may require manual reconciliation. This
    is intentionally at-most-once, not exactly-once: Telegram and our store do
    not share a transaction coordinator.
    """
    key = delivery_idempotency_key(identity, destination)
    if not store.claim(key, identity.report_id, identity.report_sha256, destination):
        return DeliveryAttempt(key, DeliveryState.DUPLICATE_SKIPPED)

    try:
        receipt = send()
        if receipt.destination != destination:
            raise DeliveryOutcomeUnknown("Telegram receipt destination mismatch")
    except Exception as exc:
        try:
            store.mark_unknown(key, type(exc).__name__)
        except Exception:
            pass
        raise DeliveryOutcomeUnknown(
            "Telegram delivery outcome is uncertain; automatic retry is blocked"
        ) from None

    try:
        store.mark_sent(key, receipt)
    except Exception:
        try:
            store.mark_unknown(key, "DELIVERY_RECEIPT_PERSISTENCE_FAILED")
        except Exception:
            pass
        raise DeliveryOutcomeUnknown(
            "Telegram may have received the report, but durable receipt persistence failed"
        ) from None
    return DeliveryAttempt(key, DeliveryState.SENT, receipt)
