from datetime import datetime, timezone

import pytest

from veltrix_v2.publishing.delivery_receipt import (
    TelegramDeliveryReceipt,
    verify_telegram_delivery,
)

UTC = timezone.utc
REPORT_HASH = "a" * 64
DESTINATION = "sha256:chat-fingerprint"


def receipt(message_id, delivered):
    return TelegramDeliveryReceipt(
        report_date_wat="2026-11-12",
        message_id=message_id,
        destination_fingerprint=DESTINATION,
        delivered_at_utc=delivered,
        report_sha256=REPORT_HASH,
        idempotency_key=f"2026-11-12:chunk-{message_id}",
    )


def verify(rows, expected_chunks=1):
    return verify_telegram_delivery(
        rows,
        report_date_wat="2026-11-12",
        expected_chunks=expected_chunks,
        expected_report_sha256=REPORT_HASH,
        expected_destination_fingerprint=DESTINATION,
    )


def test_delivery_receipt_passes_only_inside_0600_wat_minute():
    result = verify([receipt(123, datetime(2026, 11, 12, 5, 0, 15, tzinfo=UTC))])
    assert result.passed
    assert result.first_delivery_wat.startswith("2026-11-12T06:00:15")


def test_delivery_after_0601_wat_fails():
    result = verify([receipt(123, datetime(2026, 11, 12, 5, 1, 0, tzinfo=UTC))])
    assert not result.passed
    assert "DELIVERY_OUTSIDE_0600_WAT_MINUTE" in result.failures


def test_delivery_on_wrong_local_date_fails():
    result = verify([receipt(123, datetime(2026, 11, 12, 23, 0, 0, tzinfo=UTC))])
    assert not result.passed
    assert "DELIVERY_LOCAL_DATE_MISMATCH" in result.failures


def test_all_chunks_must_arrive_and_share_report_hash():
    first = receipt(123, datetime(2026, 11, 12, 5, 0, 5, tzinfo=UTC))
    second = TelegramDeliveryReceipt(
        report_date_wat="2026-11-12",
        message_id=124,
        destination_fingerprint=DESTINATION,
        delivered_at_utc=datetime(2026, 11, 12, 5, 0, 25, tzinfo=UTC),
        report_sha256="b" * 64,
        idempotency_key="2026-11-12:chunk-2",
    )
    result = verify([first, second], expected_chunks=2)
    assert not result.passed
    assert "REPORT_HASH_MISMATCH" in result.failures


def test_duplicate_message_and_idempotency_are_rejected():
    first = receipt(123, datetime(2026, 11, 12, 5, 0, 5, tzinfo=UTC))
    second = receipt(123, datetime(2026, 11, 12, 5, 0, 15, tzinfo=UTC))
    result = verify([first, second], expected_chunks=2)
    assert "DUPLICATE_TELEGRAM_MESSAGE_ID" in result.failures
    assert "DUPLICATE_IDEMPOTENCY_KEY" in result.failures


def test_missing_receipt_is_failure():
    result = verify([])
    assert not result.passed
    assert "NO_TELEGRAM_RECEIPTS" in result.failures


def test_naive_telegram_timestamp_is_rejected():
    with pytest.raises(ValueError, match="MUST_BE_AWARE"):
        receipt(123, datetime(2026, 11, 12, 5, 0))
