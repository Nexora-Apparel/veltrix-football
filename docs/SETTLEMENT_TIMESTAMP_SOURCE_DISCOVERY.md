# Settlement Timestamp Source Discovery

**Assessment date:** 2026-11-10  
**Status:** No source qualified; historical dataset admission remains blocked.

## Objective

Find a source that supplies an independently auditable, timezone-aware wall-clock timestamp for the actual end of a football match. The required value is the full-time event time, not the time at which a provider later processed, published, retrieved, or validated the result.

## Candidate assessment

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

Continue discovery against official competition match centres and specialist event-data providers. Require a documented immutable `occurred_at`/final-whistle timestamp before spending credits or acquiring a large historical archive. If no suitable source exists within the project's provider budget, revise the training-label temporal contract through a separately reviewed design decision rather than silently weakening it.
