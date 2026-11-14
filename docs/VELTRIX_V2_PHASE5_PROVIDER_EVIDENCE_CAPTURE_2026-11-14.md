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

The 5Dollar historical parser's conservative availability estimate is retrieval-derived, and the recovered archive lacks proven source publication/availability timestamps and complete revision history. Those records therefore remain non-certifiable. This adapter does not promote those historical records.

A future provider-specific prospective adapter must populate this contract from source-documented timestamps and raw responses. If the provider does not expose adequate timestamps or revision history, the result remains ineligible. No timestamp may be manufactured to satisfy this contract.

## Safety and release boundary

- No live provider calls.
- No paid provider calls or paid historical odds.
- No production database writes or migrations.
- No paper-ledger persistence.
- No scheduler, Telegram, website publication or value-bet activation.
- Draft PR only; real predictive performance remains unproven.
