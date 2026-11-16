# VELTRIX FOOTBALL 2.0 — OpenPlay / WhoScored / Opta Authorization Record

**Record date:** 2026-11-15  
**Project scope:** VELTRIX FOOTBALL 2.0  
**Status:** USER-CONFIRMED AUTHORIZATION — NON-COMMERCIAL ONLY  
**Applies to:** OpenPlay release `data-v0.1.0` and its disclosed underlying WhoScored.com / Opta (Stats Perform) match data lineage.

## Authorization statement

The project owner has explicitly confirmed in the VELTRIX project conversation on 2026-11-15:

> "We also have authorisation on whoscored/Opta. We can use it as we see fit as long as we don't monitise it"

VELTRIX therefore records the user's confirmation that authorization covers use of the OpenPlay dataset and its underlying WhoScored / Opta data for VELTRIX FOOTBALL, provided the project remains non-commercial.

This supersedes the earlier qualification note that treated upstream rights as unresolved. That earlier note was accurate based on the evidence then recorded, but is now superseded by this authorization confirmation.

## Permitted project activity under the confirmed scope

For non-commercial VELTRIX FOOTBALL use:
- acquire and retain the pinned OpenPlay historical release and source provenance;
- parse, normalize and store match, team, player, lineup, shot and event observations;
- perform historical football analysis and feature research;
- train, validate and compare VELTRIX-owned analytical and prediction models;
- create derived statistics, forecasts, research reports and non-commercial product displays;
- use the source data for internal research and model evaluation.

## Hard restrictions

- No monetisation of the data or data-derived VELTRIX service.
- No commercial licensing, resale, sublicensing or paid redistribution of source data.
- Do not redistribute raw WhoScored / Opta / OpenPlay datasets as a standalone feed.
- Keep source attribution and provenance attached to all ingested records and derived research.
- Preserve the exact OpenPlay release version, source IDs, original xG model identifier, hashes, competition/season coverage and known data-quality flags.
- Any change to commercial status requires a new rights review and a separately recorded authorization; this record does not authorize monetisation.

## Attribution and lineage

Pinned OpenPlay source:
- Repository: https://github.com/nlbair/openplay
- Release: `data-v0.1.0`
- Tag commit: `ac0bd9aff52016066433ebebf818bec4278fcf54`
- Declared release licence: CC BY 4.0
- Attribution: `openplay (Noah Bair)`, linked to the repository.
- Disclosed upstream lineage: WhoScored.com public match pages displaying Opta / Stats Perform data.

Retain upstream lineage attribution in the internal provenance record. Do not represent OpenPlay xG as a VELTRIX-trained xG estimate; retain its source `xg_model` identifier.

## Evidence registration status

The project owner's explicit authorization statement is recorded above as the current project instruction. The following evidence metadata has not yet been supplied in a machine-verifiable form and must be appended when available:
- authorization grantor / rights-holder identity;
- written authorization document or message URI;
- evidence SHA-256;
- authorization effective date and any expiry;
- exact rights-holder wording and whether any conditions beyond non-commercial use apply.

Until those fields are attached, the authorization is **user-confirmed and operationally accepted for non-commercial project work**, but the database's formal `source_approvals` row must not be fabricated with invented evidence hashes, grantor identities or terms versions.

## Data admission and point-in-time controls

Rights authorization does not itself establish historical point-in-time availability. Each observation must still retain:
- original source event / match / player identifiers;
- source publication or effective timestamp, where supplied;
- VELTRIX retrieval timestamp;
- exact release/file hash and provider response or manifest link;
- competition and season coverage;
- source xG model identifier;
- known gaps and data-issue flags.

Only observations with defensible source-availability and capture timestamps at or before the relevant prediction cutoff may enter historical pre-match features. Match events and post-match statistics remain target/label or post-match research data unless a separate timestamp proves they were available before cutoff. Do not backdate static historical release data or infer pre-match availability from match-event timestamps.

## Decision

- Rights classification: **AUTHORIZED FOR NON-COMMERCIAL VELTRIX FOOTBALL USE**, based on explicit project-owner confirmation.
- OpenPlay / WhoScored / Opta upstream-rights quarantine: **LIFTED for the stated non-commercial scope**.
- Raw source redistribution: **NOT AUTHORIZED by this record**.
- Commercial use / monetisation: **PROHIBITED**.
- Technical ingestion: may proceed in an isolated, auditable historical-data lane, subject to point-in-time, data-quality and provenance gates.
- Production feature admission: only after PIT and competition-season validation.
- Prediction publication, value-betting certification, deployment and scheduling: unchanged; this authorization does not unlock them.
