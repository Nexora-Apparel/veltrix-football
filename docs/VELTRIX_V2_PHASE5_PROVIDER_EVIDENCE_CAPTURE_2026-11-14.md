# VELTRIX 2.0 Phase 5 — Provider Evidence Capture Contract

Date: 2026-11-14

## Purpose

The provider evidence capture module is an offline adapter that turns an already-retrieved provider result response into immutable, content-addressed item evidence and a deterministic batch manifest. It does not make HTTP requests, read secrets, write to a database, or activate any publishing path.

## Required evidence per result

- Exact provider/source/endpoint/request identity and provider fixture, competition and team IDs.
- Exact raw response bytes, hashed with SHA-256. Normalized JSON is not a substitute for the raw response.
- Source publication timestamp and an explicit timestamp basis.
- Result availability timestamp and explicit provider timestamp basis.
- Source effective timestamp, when supplied; never substitute it for publication or availability.
- Request, retrieval and recording timestamps, all timezone-aware and ordered.
- Exact kickoff timestamp.
- Explicitly complete source revision history.
- Versioned, resolved provider-to-canonical fixture/team/competition crosswalk with a supporting evidence hash.
- Use-time rights approval, scoped to provider competition and evaluated separately for COLLECTION, STORAGE and MODEL_TRAINING.

Both publication and availability timestamp evidence hashes must bind to the exact raw response hash for provider-timestamp basis. Unsupported timestamp bases and missing evidence fail closed. Retrieval time is never substituted for source publication or result availability.

## Certification

An item is marked point_in_time_certifiable=true only if every required check passes. Rejected items remain in the manifest with stable reason codes. Duplicate canonical fixture IDs or duplicate provider fixture IDs invalidate all affected rows in the batch.

The manifest hashes canonical item evidence hashes and request-level identity/timestamps. The item and manifest records are frozen dataclasses. The manifest is content-addressed; durable append-only persistence is a separate controlled operation and is not performed by this adapter.

## Model and paper-ledger boundary

The certified_match_observations adapter converts only certified evidence items into model observations. Each observation carries:
- Exact raw response SHA-256.
- Evidence manifest SHA-256.
- Item evidence SHA-256.
- Rights approval identity.
- A dedicated provider_evidence_manifest_v1 availability basis.

Paper admission recognizes that basis and requires valid manifest and item evidence hashes before training evidence can enter the admission digest. Admission independently rechecks source rights at its own use-time timestamp. Existing non-manifest observations retain their separate contract and are not silently upgraded by this adapter.

## Current provider limitations

The 5Dollar page adapter now maps parsed result pages into this capture contract while preserving the exact page response hash. It deliberately does not forward the parser's conservative kickoff-plus-four-day availability proxy. The current 5Dollar contract does not prove source publication time, result availability time or complete revision history, so its finished results remain in the manifest as rejected items.

A future provider-specific prospective adapter must populate this contract from source-documented timestamps and raw responses. If the provider does not expose adequate timestamps or revision history, the result remains ineligible. No timestamp may be manufactured to satisfy this contract.

## Safety and release boundary

- No live provider calls.
- No paid provider calls or paid historical odds.
- No production database writes or migrations.
- No paper-ledger persistence.
- No scheduler, Telegram, website publication or value-bet activation.
- Draft PR only; real predictive performance remains unproven.


## Append-only persistence adapter

The staging persistence adapter is implemented in `veltrix_v2/data/evidence_persistence.py`. It appends:
- The immutable capture manifest and a manifest event.
- The exact raw provider response bytes and SHA-256.
- The provider request record linked to the stored response.
- One source-observation row per captured fixture, including rejected rows and their reason codes.

All writes execute in one DB-API transaction. Replays are idempotent by manifest key, response identity and source-observation identity. Each referenced source approval must already exist in the target database.

Writes are disabled by default. The explicit guard requires the staging environment label, the dedicated staging database, the known direct staging host and the staging role. The adapter does not create connections or read environment secrets. Tests assert that disabled or non-allowlisted calls never open the supplied connection. PostgreSQL integration tests create an isolated schema on PostgreSQL 16 and 18, write and read back exact raw bytes and manifest/item links, verify replay idempotency, and confirm missing approval rolls back the entire transaction. These are isolated CI databases, not Neon staging. No database writes have been performed by this component.


## StrikerAPI dataset refresh evidence

The official StrikerAPI changelog publishes a dataset-level Written timestamp for "Fixtures, results and box scores". The offline parser in veltrix_v2/data/strikerapi_freshness.py preserves the exact changelog response hash, dataset name, through-date, written timestamp and retrieval timestamp. It rejects missing, malformed, naive or future timestamps.

This is dataset-level refresh evidence, not a per-fixture publication timestamp or per-record revision ID. StrikerAPI documents that it overwrites corrected records and does not retain per-record revision history. Therefore this parser does not certify individual fixtures or historical walk-forward rows by itself. A prospective capture process must archive the raw list_games response and changelog snapshot each refresh, track per-fixture payload changes in our own append-only history, detect missed refresh intervals, and only then mark a locally complete as-of interval eligible. The source's documented lack of historical revisions must never be concealed or treated as proof of historical completeness.
