# Settlement Timestamp Source Discovery

**Assessment date:** 2026-11-10  
**Status:** No source qualified; historical dataset admission remains blocked.

## Objective

Find a source that supplies an independently auditable, timezone-aware wall-clock timestamp for the actual end of a football match. The required value is the full-time event time, not the time at which a provider later processed, published, retrieved, or validated the result.

## Candidate assessment

### Genius Sports Warehouse — strongest candidate; not yet qualified

The official Genius Sports developer documentation exposes `timeEndActual` in two relevant contracts:

1. **Football streaming API:** the `summary` message is usually sent once at the end of a match. Its `timeEndActual` field is explicitly described as the actual end date/time of the match in UTC, formatted as `YYYY-MM-DD HH:MM:SS`.
2. **Warehouse REST match resource:** the match object also exposes `timeEndActual`, described as the actual end time of the match. The REST API provides match lookup by ID and match listing by competition with date filters. The Developer Centre describes the Warehouse REST API as querying information about both past and future matches.

Official references:
- https://developer.geniussports.com/warehouse/livestream/read/index_football.html
- https://developer.geniussports.com/livestats/tvfeed/index_football.html
- https://developer.geniussports.com/warehouse/rest/index_football.html
- https://developer.geniussports.com/warehouse/old/match.html
- https://developer.geniussports.com/warehouse/old/resource_match.html
- https://developer.geniussports.com/

Positive evidence:
- The field is explicitly named `timeEndActual`, not `updated_at`, `last_processed_at`, or a retrieval timestamp.
- The official stream schema describes it as the match's actual end date/time and explicitly specifies UTC.
- The stream's `summary` message is described as normally being sent once at the end of the match.
- The REST match resource includes native match ID, competition ID, match status, kickoff, teams/competitors and `timeEndActual`, supporting exact identity and historical match lookup.
- The REST API supports listing matches by competition and date range, while the Developer Centre says the Warehouse REST API covers past and future matches. This makes historical retrieval plausible without relying solely on a live stream.

Critical limitations and unresolved qualification requirements:
1. **REST timezone ambiguity:** the streaming schema explicitly says UTC, but the reviewed REST match-resource description for `timeEndActual` does not itself specify a timezone. Do not parse a naive REST timestamp as UTC unless Genius Sports confirms that semantic. The stream and REST contracts must not be assumed identical.
2. **Mutable records:** the REST API's general documentation explicitly warns that data may be removed or changed. The match resource documentation does not specify an immutable revision history or explain how timestamp corrections are exposed. A current historical response alone cannot prove what value was present at an earlier training cutoff.
3. **Event semantics:** the documentation calls the field the actual end time, but does not explicitly state that it is the referee's final-whistle instant in every competition format. Genius Sports must clarify whether it means end of play, end of capture, or another operational marker.
4. **Historical point-in-time availability:** retrieving an old match through the REST API today proves only what the API returns today. It does not prove when the result or any related statistics first became available historically. Such a response may support a settlement label after source qualification, but cannot by itself establish that the same information was available before a later historical fixture's feature cutoff. Historical feature reconstruction still requires contemporaneous snapshots/receipts or a separately verified source publication-time history.
5. **Archive depth:** the REST API supports past-match queries, but the reviewed documentation does not establish the available historical seasons, retention period, or whether the relevant competitions and match records include populated `timeEndActual`.
6. **Access and coverage:** API keys specify access and quota; production content is limited to what the customer is licensed to receive. Competition-level availability and pricing must be confirmed before any acquisition.
7. **Rights:** raw payload retention, derived feature use, model training, and long-term archive rights must be confirmed in the applicable contract.
8. **Edge cases:** abandoned, suspended, replayed, awarded, extra-time and penalty-shootout handling needs an explicit provider contract.
9. **Evidence integrity:** every acquired response must be archived byte-for-byte with retrieval time, endpoint, provider match ID, request/run ID and SHA-256. Repeated retrievals must be retained as separate observations so changes can be detected rather than overwritten.

**Decision:** Keep Genius Sports as the primary candidate for vendor qualification. Do not admit it to the signed settlement-source qualification registry yet. The documentation supports an actual-end-time field and historical match retrieval, but does not establish REST timezone semantics, immutable revisions, universal final-whistle semantics, historical point-in-time availability, coverage, commercial access or data-use rights. No provider account, API access, archive, or terms have been verified. Do not spend credits or acquire data until these conditions are confirmed.

### Sportradar Soccer API — not qualified for settlement time

Official documentation identifies a `match_ended` timeline event type. However, the documented Soccer Sport Event Timeline `event.time` field is explicitly the UTC time when the event record was created or most recently updated in Sportradar's system. It is not the time the event occurred on the pitch; it can lag by minutes or hours and is overwritten when the event is updated.

Therefore:
- `event.type == match_ended` is useful terminal-event evidence.
- `event.time` is provider processing/update time, not a documented final-whistle wall-clock time.
- `match_clock`, `match_time`, `period`, and stoppage-time fields describe match-clock context, not a UTC wall-clock event instant.
- The documented event fields cannot be converted into an exact settlement timestamp without inventing a time.

Official references:
- https://developer.sportradar.com/soccer/reference/soccer-sport-event-timeline
- https://developer.sportradar.com/soccer/reference/soccer-faq
- https://developer.sportradar.com/soccer/reference/soccer-push-events

**Decision:** Reject as a settlement-time source under the current documented schema. Reconsider only if the provider documents a separate immutable event-occurrence timestamp or supplies a signed/auditable event stream with that semantic.

### Sportmonks Football API v3 — not qualified for settlement time

The documented fixture schema exposes a full-time state and `last_processed_at`. The documentation describes `last_processed_at` as processing/update metadata, not as the actual final-whistle time. Fixture state `FT` proves a status, not the instant at which the referee ended play.

Official references:
- https://www.sportmonks.com/glossary/fixtures/
- https://docs.sportmonks.com/v3/definitions/states
- https://docs.sportmonks.com/v3/tutorials-and-guides/tutorials/livescores-and-fixtures/fixtures

**Decision:** Reject `last_processed_at` as settlement time. Do not derive a final-whistle timestamp from scheduled kickoff, expected match duration, or state transition observation time.

### football-data.org — not qualified on current evidence

The public Match API documentation defines the `FINISHED` status as the state reached after the final whistle. The reviewed documentation does not establish a dedicated immutable wall-clock `finished_at` field. A status and general update metadata are insufficient.

Official reference:
- https://docs.football-data.org/general/v4/match.html

**Decision:** Candidate remains unqualified unless a documented match-end timestamp with explicit semantics is identified and verified.

## Admission contract for future candidates

A source can enter the qualification registry only when all of the following are evidenced:

1. **Documented semantics:** the source explicitly identifies the timestamp as the actual match-end/final-whistle event time, not record creation, update, retrieval, publication, or validation time.
2. **Fixture identity:** exact fixture identity through a provider-native ID or an independently verified cross-provider mapping. Team-name similarity alone is insufficient.
3. **Time correctness:** timezone-aware ISO-8601 or epoch timestamp with documented UTC/offset semantics.
4. **Raw evidence:** retained original payload or signed source response, plus retrieval time, endpoint, source ID, request/run ID and canonical payload digest.
5. **Integrity:** independent digest recomputation and deterministic source-specific extraction.
6. **Revision semantics:** documented behavior for corrections, replays, abandoned/suspended matches, extra time, penalties and administrative awards.
7. **Coverage:** measured fixture-level coverage by competition and season; no extrapolation from one competition to another.
8. **Conflict handling:** conflicting independently qualified timestamps are quarantined; never averaged or silently selected.
9. **Rights:** storage and use are compatible with the provider's current terms.

## Explicitly prohibited substitutions

The following are not settlement timestamps:
- provider retrieval time;
- local ingestion or processing time;
- `last_processed_at` or `updated_at` without event-occurrence semantics;
- odds quote `recorded_at`;
- scheduled kickoff plus an assumed duration;
- event minute or match clock converted into wall-clock time;
- first observed transition to a finished status;
- result publication or statistics-validation time.

## Current consequence

The existing StrikerAPI and 5DollarFootballAPI schemas establish terminal match status but do not expose a documented wall-clock settlement timestamp. The dataset bridge must continue to reject those rows for training-history admission until a separately qualified source is integrated.

This is a deliberate fail-closed data-quality boundary. No timestamp is fabricated, no existing provider is promoted beyond its evidence, and no historical data is imported as a result of this assessment.

## Next action

Obtain written clarification from Genius Sports on the meaning, timezone and correction/revision behavior of `timeEndActual`; confirm which historical seasons and competitions expose populated values; obtain the commercial schedule and explicit rights for archival retention and model training; then validate a small, permitted sample against independent match-centre evidence. Separately, define how contemporaneous historical feature availability will be proven; a current historical REST response is not sufficient. Only after those checks pass should a source-specific extraction adapter and signed qualification record be implemented. If those conditions cannot be satisfied, continue discovery against official competition match centres and specialist event-data providers. If no suitable source exists within the project's provider budget, revise the training-label temporal contract through a separately reviewed design decision rather than silently weakening it.
