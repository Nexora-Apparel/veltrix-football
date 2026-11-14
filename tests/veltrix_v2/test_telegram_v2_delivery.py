from __future__ import annotations

import pytest

from veltrix_v2.reporting.delivery import (
    DeliveryOutcomeUnknown,
    DeliveryReceipt,
    DeliveryState,
    deliver_once,
)
from veltrix_v2.reporting.report_identity import create_report_identity


class MemoryStore:
    def __init__(self):
        self.claimed = set()
        self.sent = {}
        self.unknown = {}

    def claim(self, key, report_id, report_sha256, destination):
        if key in self.claimed:
            return False
        self.claimed.add(key)
        return True

    def mark_sent(self, key, receipt):
        self.sent[key] = receipt

    def mark_unknown(self, key, reason_code):
        self.unknown[key] = reason_code


def identity():
    from veltrix_v2.reporting.report_identity import REPORT_SCHEMA
    return create_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "delivery-test-1",
        "as_of_date": "2026-11-14",
        "predictions": [],
    })


def test_first_delivery_claims_sends_and_persists_receipt():
    store = MemoryStore()
    calls = []
    result = deliver_once(
        identity(), "telegram:chat-1", store,
        lambda: (calls.append("sent") or DeliveryReceipt("telegram:chat-1", ("msg-1",))),
    )
    assert result.state is DeliveryState.SENT
    assert calls == ["sent"]
    assert store.sent[result.idempotency_key].message_ids == ("msg-1",)


def test_duplicate_run_is_skipped_without_second_send():
    store = MemoryStore()
    calls = []
    report = identity()
    send = lambda: (calls.append("sent") or DeliveryReceipt("telegram:chat-1", ("msg-1",)))
    first = deliver_once(report, "telegram:chat-1", store, send)
    second = deliver_once(report, "telegram:chat-1", store, send)
    assert first.state is DeliveryState.SENT
    assert second.state is DeliveryState.DUPLICATE_SKIPPED
    assert calls == ["sent"]


def test_uncertain_transport_failure_is_marked_and_never_retried():
    store = MemoryStore()
    calls = []

    def uncertain_send():
        calls.append("attempt")
        raise TimeoutError("network timed out after request dispatch")

    with pytest.raises(DeliveryOutcomeUnknown):
        deliver_once(identity(), "telegram:chat-1", store, uncertain_send)
    second = deliver_once(
        identity(), "telegram:chat-1", store,
        lambda: (calls.append("retry") or DeliveryReceipt("telegram:chat-1", ("msg-2",))),
    )
    assert second.state is DeliveryState.DUPLICATE_SKIPPED
    assert calls == ["attempt"]


def test_receipt_destination_mismatch_becomes_uncertain_and_is_not_retried():
    store = MemoryStore()
    with pytest.raises(DeliveryOutcomeUnknown, match="uncertain"):
        deliver_once(
            identity(), "telegram:chat-1", store,
            lambda: DeliveryReceipt("telegram:chat-2", ("msg-1",)),
        )
    assert len(store.unknown) == 1


def test_receipt_persistence_failure_blocks_automatic_retry():
    class BrokenStore(MemoryStore):
        def mark_sent(self, key, receipt):
            raise OSError("database unavailable")

    store = BrokenStore()
    with pytest.raises(DeliveryOutcomeUnknown, match="persistence failed"):
        deliver_once(
            identity(), "telegram:chat-1", store,
            lambda: DeliveryReceipt("telegram:chat-1", ("msg-1",)),
        )
    second = deliver_once(
        identity(), "telegram:chat-1", store,
        lambda: pytest.fail("automatic retry must not run"),
    )
    assert second.state is DeliveryState.DUPLICATE_SKIPPED


def test_same_report_to_different_destinations_has_separate_idempotency_keys():
    store = MemoryStore()
    first = deliver_once(
        identity(), "telegram:chat-1", store,
        lambda: DeliveryReceipt("telegram:chat-1", ("msg-1",)),
    )
    second = deliver_once(
        identity(), "telegram:chat-2", store,
        lambda: DeliveryReceipt("telegram:chat-2", ("msg-2",)),
    )
    assert first.idempotency_key != second.idempotency_key
    assert first.state is DeliveryState.SENT
    assert second.state is DeliveryState.SENT
