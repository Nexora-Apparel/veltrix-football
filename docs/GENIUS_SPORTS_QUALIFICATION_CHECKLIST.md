# Genius Sports Settlement-Time Vendor Qualification Checklist

**Project:** VELTRIX FOOTBALL 2.0  
**Candidate:** Genius Sports Warehouse football data  
**Status:** Research checklist only. No provider access, commercial terms, sample payloads, or source qualification have been verified.  
**Related assessment:** docs/SETTLEMENT_TIMESTAMP_SOURCE_DISCOVERY.md

## Purpose

Obtain authoritative written answers before any paid access, provider request, data acquisition, source-registry admission, or model-training use. The target is a defensible settlement timestamp and a lawful historical evidence path, not merely a match status or a timestamp that looks plausible.

## 1. Timestamp semantics

Request written confirmation for the football timeEndActual field:

1. Does it represent the actual instant the referee ends play (final whistle), rather than the end of a data-capture session, feed session, broadcast, or provider processing operation?
2. Is the definition consistent across all supported football competitions and data collection methods?
3. Does the streaming summary.timeEndActual field have exactly the same semantics as the REST match-resource timeEndActual field?
4. Is the value UTC in both interfaces? The streaming schema explicitly states UTC; the reviewed REST match-resource schema does not state a timezone. What timezone/offset is used by REST?
5. What is the precision and expected clock error? Are capture devices synchronized to UTC using NTP or another audited clock source?
6. Is the value generated from a referee/operator event, automated capture, or a later data-processing step?

**Required evidence:** versioned official schema or contract language defining the event and timezone semantics. Do not infer REST timezone from the streaming schema.

## 2. Match lifecycle and exception semantics

Require exact behavior and examples for:

- Regular-time matches.
- Extra time and penalty shootouts.
- Half-time and extra-time breaks.
- Matches interrupted and resumed.
- Suspended or abandoned matches.
- Matches awarded by forfeit or administrative decision.
- Postponed and cancelled fixtures.
- Replayed matches and duplicate fixture records.
- Matches with disputed or corrected final scores.

For each case, identify whether timeEndActual is populated, null, revised, or represented by a separate status. A non-played/awarded fixture must not be mislabeled as a final-whistle event.

## 3. Revision history and auditability

The Warehouse REST documentation warns that data can be removed or changed. Ask:

1. Are previous versions of a match record retained?
2. Is there a revision ID, immutable event ID, update timestamp, or audit log for changes to timeEndActual?
3. Can Genius Sports provide the original value and every subsequent correction, with when each version was created and made available?
4. Are raw event messages or original response bytes available for historical matches?
5. Can the provider attest that a timestamp was not retrospectively backfilled or rewritten?
6. What happens when the match time, match status, score, teams, or competition assignment is corrected?

**Minimum acceptance:** either an immutable source record with a documented revision guarantee, or complete version history sufficient to preserve and audit every revision. A current REST response alone is insufficient.

## 4. Historical coverage and retrieval

Request a coverage matrix before any data purchase:

| Required field | Requested evidence |
|---|---|
| Competition | Provider competition ID and canonical name |
| Country / region | Coverage scope |
| Season | Earliest and latest season available |
| Match count | Total and finished matches per season |
| timeEndActual coverage | Populated count and percentage |
| Match identity | Native match ID and team/competition IDs |
| Raw evidence | Whether original response or event messages can be exported |
| Revisions | Whether historical changes are available |
| Retrieval | REST endpoint, pagination, filters, rate limits and quota |
| Retention | Historical retention period and deletion policy |

Specifically confirm whether the REST endpoints can retrieve all historical match records and populated timeEndActual values for the competitions VELTRIX intends to model. “Past and future matches” in general documentation does not prove coverage for a particular competition or season.

## 5. Historical point-in-time feature availability

This is a separate requirement from final-whistle time.

For historical model features, VELTRIX must establish when the final score, result, team statistics and other inputs were actually available to a consumer. Ask whether Genius Sports can provide:

- Original event publication/delivery timestamps.
- Original API record creation/availability timestamps.
- Complete update/revision history.
- Historical push-message or feed archives with receipt timestamps.
- A supported replay/export that preserves original timestamps rather than assigning today's retrieval time.

A historical match record retrieved today cannot, by itself, prove that the same information was available before a later historical fixture's feature cutoff. If no contemporaneous availability evidence exists, those historical records cannot be used to reconstruct point-in-time features for past fixtures. They may only be considered for narrower label use after settlement-source qualification.

## 6. Fixture identity and cross-provider mapping

Confirm the availability and stability of:

- Native match ID.
- Competition and season IDs.
- Home and away team IDs.
- Kickoff timestamp and timezone.
- External IDs supplied by leagues or other data providers.
- Stable identifiers across REST, streaming, historical replay and corrections.

VELTRIX will require exact fixture-level identity. Team-name similarity, kickoff proximity, or fuzzy matching alone will not be accepted as proof of a cross-provider mapping.

## 7. Commercial rights and costs

Obtain written terms covering:

- API access and permitted competitions.
- Historical data access and one-time backfill fees.
- Request quotas, rate limits and overage charges.
- Raw payload storage and long-term archival retention.
- Use of match results and statistics for internal machine-learning training.
- Storage of derived features, model artifacts and evaluation evidence.
- Use in an internal analytical website and private Telegram reports.
- Restrictions on redistribution, sublicensing or public display.
- Data deletion, contract termination and post-termination retention.
- Any required attribution or licensing notices.

No provider budget or commercial entitlement is assumed. No trial or paid request should be initiated until the exact scope and cost are understood.

## 8. Controlled sample qualification plan

Only after written confirmation of semantics, access, coverage and rights:

1. Obtain a small provider-approved sample across at least two target competitions and multiple seasons.
2. Include normal full-time, extra-time, penalty, abandoned/suspended and corrected-match cases where available.
3. Preserve exact HTTP response bytes or original stream messages, response headers, endpoint, request ID, retrieval time and provider match ID.
4. Recompute SHA-256 over the exact bytes and retain every repeated retrieval as a separate immutable observation.
5. Parse the timestamp using only the explicitly documented timezone contract. Reject naive REST timestamps until UTC/offset semantics are confirmed.
6. Compare a predeclared sample against independent official competition records or another qualified source. Do not select only matches that agree.
7. Measure coverage and timestamp disagreement by competition and season.
8. Test record revision behavior by retrieving the same sample on separate dates and comparing exact response digests and timestamp values.
9. Produce a signed qualification evidence package; do not mark the source qualified merely because the sample parser succeeds.

## 9. Engineering admission gates

The source must not enter app/source_qualification_registry.py until all of the following are met:

- [ ] Written final-whistle/event-time semantics confirmed.
- [ ] REST timezone explicitly confirmed, or only the separately documented UTC stream contract is used.
- [ ] Revision/immutability behavior documented and tested.
- [ ] Historical season and competition coverage measured.
- [ ] Fixture identity and crosswalk process validated.
- [ ] Raw evidence retention and digest verification tested.
- [ ] Independent timestamp comparison passed against predeclared acceptance tolerances.
- [ ] Historical point-in-time availability path demonstrated for any proposed training features.
- [ ] Model-training and archival rights confirmed in writing.
- [ ] Cost and quota approved within the project budget.
- [ ] Competition-specific scope explicitly listed in the qualification record.
- [ ] Signed registry generated with the existing trusted KMS process.

Until every applicable gate passes, status remains candidate, not qualified. The dataset bridge must continue to reject the source for settlement admission.

## 10. Current project decision

No Genius Sports credentials have been requested or used. No provider calls, paid trials, quota consumption, database writes, data imports, model training, publication, Telegram delivery, or scheduling changes are authorized by this research document.

The next safe action is to obtain the written vendor answers and coverage/price proposal. Engineering can then decide whether to build the source-specific adapter and controlled sample validator. If the historical point-in-time availability requirement cannot be met, the model dataset plan must explicitly separate eligible prospective data from historical label-only data rather than silently relaxing the leakage controls.
