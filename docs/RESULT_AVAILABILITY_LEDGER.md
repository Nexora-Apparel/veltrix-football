# Historical Result Availability Ledger

**Status:** Implemented as an append-only, in-memory contract; not connected to a scheduler, database, or provider polling job.

## Purpose

Record the first time VELTRIX independently observes a provider response showing a terminal result. This captures prospective result-availability evidence, not the actual match-end time.

## Observation record

Each observation binds:
- provider and competition scope;
- canonical VELTRIX fixture identity and provider source ID;
- endpoint and acquisition run ID;
- timezone-aware VELTRIX observation timestamp;
- observed status and terminal-state interpretation;
- retained raw response and recomputed canonical SHA-256;
- deterministic observation ID.

Provider terminal states are deliberately limited to the documented current contracts: StrikerAPI `final`, 5DollarFootballAPI `finished`.

## Integrity and append rules

- Recompute raw payload and observation hashes during validation.
- Reject unsupported providers, malformed payloads, naive timestamps and tampering.
- Preserve every distinct observation; exact duplicate appends are idempotent.
- Reject observation-time regressions for the same provider/fixture stream.
- Never overwrite an earlier response when a later response changes the score or status.
- Derive the first observed terminal response from the append-only history.

## Semantics

The derived timestamp is labelled:

`veltrix_first_observed_terminal_result_availability`

It is never labelled a settlement timestamp. The ledger explicitly marks:
- `is_settlement_timestamp = false`
- `historical_availability_reconstructed = false`

A first observation at 19:03 means only that VELTRIX observed the terminal response at 19:03. The match may have ended earlier. This evidence can support prospective label-availability controls when building future training snapshots, but it cannot repair the missing historical settlement-time evidence.

## Current integration boundary

The module is pure and in-memory. No provider calls, database writes, imports, background polling or schedules are enabled. Persistent storage and polling require a separate operational design, quota controls, retention review and explicit release approval.

The historical dataset bridge remains unchanged and continues to reject provider records lacking a qualified settlement timestamp.
