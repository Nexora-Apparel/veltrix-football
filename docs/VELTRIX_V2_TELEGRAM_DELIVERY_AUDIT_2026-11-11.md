# VELTRIX 2.0 Telegram delivery audit contract

Date: 2026-11-11

## Timing proof

`veltrix_v2/publishing/delivery_receipt.py` validates actual Telegram `Message.date` timestamps returned by the Bot API. It does not trust the GitHub runner's local clock or a scheduler's successful exit code.

For a report dated D in `Africa/Lagos`, every Telegram message chunk must be received in the WAT minute beginning D 06:00:00 and ending immediately before D 06:01:00. The report hash, destination fingerprint and idempotency key are carried into the audit. The expected chunk count must match the receipts, and duplicate message IDs/idempotency keys fail the audit.

## Acceptance test

A delivery is accepted only when:

- every expected chunk has a Telegram server receipt;
- all receipts belong to the expected WAT report date;
- every receipt is within 06:00:00–06:00:59 WAT;
- all chunks carry the same report SHA-256 and destination fingerprint;
- message IDs and idempotency keys are unique.

The sender must capture the Bot API response's server `date` field, message ID and destination identity. A workflow marked green without these receipts is not proof of delivery.

## Current status

No V2 production report has been sent and no 06:00 WAT delivery has been verified. Existing Telegram schedules remain paused. The audit contract is a testable boundary for a later controlled delivery rehearsal after release certification.
