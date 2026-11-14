# VELTRIX V2 Telegram operator reconciliation contract — 2026-11-14

## Purpose

Resolve a durable Telegram delivery claim in `OUTCOME_UNKNOWN` after a timeout, process interruption, partial multi-message send, or receipt-persistence failure. Reconciliation records evidence about what happened; it must never silently replay a report.

## Non-negotiable invariants

1. An `OUTCOME_UNKNOWN` claim is terminal for automated dispatch.
2. Reconciliation never edits, deletes, truncates, or reopens the original delivery claim.
3. Reconciliation does not send Telegram messages and does not call Telegram APIs.
4. A later report revision has a new report ID/hash and is a distinct report, not a retry of the prior one.
5. An operator's statement without independently reviewable evidence is not proof of delivery or non-delivery.
6. Reconciliation evidence is append-only, content-addressed, and tied to the exact delivery claim, report identity, and destination hash.
7. The system must not expose or persist the raw Telegram destination in reconciliation records.

## Reconciliation outcomes

| Outcome | Required evidence | Effect |
|---|---|---|
| `CONFIRMED_SENT` | Exact report identity, destination match, Telegram message IDs, and a verifiable Telegram message link/export or bot-side receipt evidence | Record that the report was delivered; original claim remains `OUTCOME_UNKNOWN` |
| `CONFIRMED_NOT_SENT` | Evidence that no message was accepted for the exact destination and attempt, including review of the full send window and all chunks | Record non-delivery; original claim remains `OUTCOME_UNKNOWN`; no automatic retry is authorized |
| `INCONCLUSIVE` | Evidence reviewed but unable to establish sent or not sent | Record inconclusive result; keep all retry paths blocked |

A missing message ID is not proof of non-delivery. A successful first chunk followed by a timeout on a later chunk is a partial delivery and must be reconciled as such; it cannot be classified as `CONFIRMED_NOT_SENT`.

## Implemented reconciliation foundation

The repository now contains migration `0010_telegram_delivery_reconciliation.sql`, the pure validator and PostgreSQL writer in `veltrix_v2/reporting/reconciliation.py`, and unit/PostgreSQL integration tests. The writer re-reads evidence bytes through an injected trusted evidence reader, verifies their SHA-256, binds the event to the exact `OUTCOME_UNKNOWN` claim, and writes an append-only event. Database triggers enforce claim identity, outcome constraints, supersession links, and append-only behavior. The writer has no Telegram transport and cannot resend a message.

The caller must still authenticate the operator and independent reviewer identities and provide an approved evidence reader. The database stores identity strings; it does not itself prove those identities were authenticated.

## Required reconciliation event fields

The future append-only reconciliation event must contain:

- `reconciliation_id`: unique immutable event ID.
- `delivery_idempotency_key`: foreign key to the original claim.
- `report_id` and `report_sha256`: exact report identity copied from the claim and verified before insertion.
- `destination_sha256`: exact destination hash copied from the claim; raw chat ID is forbidden.
- `outcome`: one of the three outcomes above.
- `telegram_message_ids`: non-empty only for `CONFIRMED_SENT`.
- `evidence_uri`: durable evidence location, not an expiring local path.
- `evidence_sha256`: SHA-256 of the exact evidence bytes.
- `evidence_kind`: controlled vocabulary describing the evidence format.
- `operator_id`: authenticated GitHub/organization actor identifier, not a free-form display name.
- `reviewer_id`: independent second reviewer for `CONFIRMED_NOT_SENT`; must differ from operator.
- `observed_at` and `recorded_at`: timezone-aware timestamps; recorded time must not precede observation time.
- `reason_code`: stable machine-readable reason.

The evidence object must be retained under the project's approved storage/retention policy. The database stores its immutable URI and hash, not a fabricated evidence timestamp.

## Validation rules

- The referenced claim must exist and be `OUTCOME_UNKNOWN`.
- Report ID/hash and destination hash must exactly match the claim.
- Evidence URI must be non-empty and evidence SHA-256 must be valid lowercase hex.
- All timestamps must be timezone-aware and satisfy `observed_at <= recorded_at`.
- `CONFIRMED_SENT` requires at least one non-empty message ID and evidence that links those IDs to the exact destination and report content.
- `CONFIRMED_NOT_SENT` requires zero message IDs and two-person review.
- `INCONCLUSIVE` requires zero message IDs and a reason code.
- Conflicting reconciliation outcomes for one claim are rejected; correction is a new superseding event with explicit evidence and review, never an update.
- Duplicate `reconciliation_id` or duplicate evidence digest for the same claim is rejected.
- The reconciliation table must reject UPDATE, DELETE and TRUNCATE at the database layer.

## Retry policy

This reconciliation contract deliberately does not implement retry authorization.

Even after `CONFIRMED_NOT_SENT`, the original idempotency key remains consumed. No worker may automatically retry it. A separate future change must introduce an explicit one-time retry authorization linked to the prior claim and reconciliation event, with a fresh attempt key and independent operator approval. Until that separate mechanism is implemented and reviewed, the only safe action is to leave the original report undelivered and issue a new report revision only when the reporting policy allows it.

## Release gate

Before any live Telegram dispatch:

- Reconciliation event schema, append-only migration and integration tests pass PostgreSQL 16 and 18.
- Evidence URI/hash verification is implemented.
- Operator and independent reviewer identity are authenticated.
- The operator workflow has no Telegram send capability.
- Unknown, partial, conflicting, or missing evidence remains blocked.
- The authoritative publication verifier is connected to the real certification engine.
- The sender, scheduler and website all consume the same immutable report artifact.
- Staging-only migration and read-only post-migration audit pass.

No Telegram send, retry, schedule activation, database migration, or publication is authorized by this document.
