# VELTRIX 2.0 — Provider Evidence Capture Contract

Status: draft implementation contract, 2026-11-14

## Purpose

The provider evidence capture adapter is the boundary between an already-retrieved provider response and the point-in-time model observation layer. It is provider-neutral and offline-only: it does not create HTTP clients, read credentials, call providers, write databases, or persist paper-ledger events.

## Evidence units

Each captured result binds:

- Provider, source/account scope, endpoint, request identity and request time.
- Exact raw response bytes and SHA-256 of those bytes.
- Source publication time and its explicit provenance basis.
- Source effective time when supplied.
- Fixture kickoff/event time.
- Result availability time.
- Retrieval time and local recording time.
- Exact provider fixture, competition, home-team and away-team IDs.
- Resolved canonical fixture, competition and team IDs with crosswalk version and evidence hash.
- Rights approval identity and evidence hash, evaluated at capture/recording time.
- Explicit revision-history completeness assertion.
- Result score and stable eligibility/rejection reason codes.

## Timestamp rules

All timestamps are separate fields. The adapter never copies retrieval time into source publication or result availability fields.

A row is ineligible if a required timestamp is missing, naive, malformed, or temporally contradictory. The manifest still retains the raw timestamp representation for rejected captures; an untrusted timestamp never becomes eligible merely because it can be serialized.

The source timestamp basis must be one of:

- `provider_timestamp`: evidence hash must equal the exact raw response SHA-256.
- `archival_snapshot_timestamp`: must be backed by a separately verified archive snapshot in a future archive adapter.
- `documented_guarantee`: must be backed by separately reviewed provider documentation.

A timestamp string alone is not proof of its semantics. A future provider-specific adapter must only set a trusted basis after validating the source contract and evidence.

## Identity and rights rules

Crosswalk status must be RESOLVED and valid at capture time. All six provider identity dimensions must match exactly; team names and fuzzy similarity are not accepted here. Canonical home and away teams must differ. Crosswalk evidence hash and mapping version are mandatory.

Source approval must match provider and source, explicitly include the provider competition ID in its competition scope, and permit COLLECTION, STORAGE and MODEL_TRAINING at the recording time. Wildcards are not accepted. The approval evidence hash is carried into every item record.

## Certification behavior

Only records with zero rejection reasons receive `point_in_time_certifiable=true`. Duplicate canonical fixture IDs or duplicate provider fixture identities invalidate every colliding row in the batch.

The adapter can convert certified evidence into `MatchObservation` records. It refuses uncertified rows. The model's existing as-of cutoff logic still independently checks that result availability and recording occurred by the forecast cutoff; capture certification does not bypass that gate.

## Manifest integrity

Each item evidence digest covers its normalized identity, timestamps, raw response hash, rights evidence, crosswalk version/evidence and eligibility decision. The manifest digest covers the ordered item digests plus request-level identity, timestamps and accepted/rejected counts.

The dataclasses are immutable. The current implementation builds manifests in memory; durable append-only database persistence remains a separate, gated integration task.

## Current limitations / next integration steps

1. Implement provider-specific parsing that binds normalized result fields to exact raw response bytes and verifies the provider's timestamp semantics.
2. Establish a verified source publication timestamp contract for each provider. If 5DollarFootballAPI does not expose a genuine publication timestamp or a documented availability guarantee, its result rows remain ineligible for strict point-in-time training.
3. Load resolved crosswalk and rights approval evidence from the approved staging evidence store, including use-time revocation history.
4. Add an isolated staging persistence adapter for the existing append-only capture manifest, request, observation and eligibility schema.
5. Add integration tests proving exact raw response linkage, crosswalk version selection, rights revocation as-of use, and staging-only writes.
6. Connect certified observations to paper admission only after these steps pass. Do not create paper entries in this phase.

No production migration, production database write, scheduled capture, live publication, Telegram delivery or value-bet unlock is authorized by this component.
