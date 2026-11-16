# OpenLigaDB offline parser contract

Date: 2026-11-14

## Scope

`veltrix_v2/data/openligadb.py` parses only exact UTF-8 response bytes already supplied by a caller. It performs no HTTP, secret lookup, provider dispatch, DB access, persistence, scheduling or retry.

The provider API describes match records with match ID, league ID, UTC kickoff, teams, finished flag, match result rows and a `lastUpdateDateTime` field. The parser preserves every result type and order, including separate `pointsTeam1` and `pointsTeam2` fields. A dedicated selector accepts only exactly one `After90Minutes` result row on a finished match; it never substitutes half-time, extra-time, penalties or list order. See the official API catalogue: https://api.openligadb.de/index.html, the published OpenAPI schema at https://api.openligadb.de/swagger/v1/swagger.json (MatchResult defines pointsTeam1/pointsTeam2 and resultTypeKind), and the match response schema: https://skmtc.dev/openligadb/apis/openligadb-api/docs/getmatchdata/:leagueShortcut/:leagueSeason/get.

## Timestamp semantics

- `matchDateTimeUTC` is required and must include an explicit timezone.
- Naive `matchDateTime` is not substituted for UTC kickoff.
- `lastUpdateDateTime` is retained only as `provider_update_at`.
- The provider's own license page explicitly says there is no public change history or immutable historical snapshots. Consequently, `lastUpdateDateTime` does not establish source publication time, actual first availability, or complete revision history.
- Retrieval time is supplied by the caller and stored separately.
- This parser does not emit `source_published_at`, `available_at`, rights approval, canonical fixture IDs or PIT-certifiable observations.

## Integrity and rejection behavior

- Hash exact raw response bytes with SHA-256.
- Require a JSON array root.
- Validate provider match, league, team identities, UTC kickoff and finished flag.
- Preserve all score result types and order.
- Reject malformed result rows rather than selecting a guessed final score.
- Reject every occurrence of duplicate provider match IDs.
- Stable rejection reason codes are emitted per row.
- Provider match IDs are not canonical fixture IDs. Crosswalk resolution and rights/temporal approval remain separate gates.

## Provider use boundary

The API terms require low-frequency centralized polling, caching, jitter and exponential backoff; the operator reserves throttling/blocking rights. The license is ODbL 1.0 and requires attribution; redistributed modified databases have share-alike obligations. Team crests and icon URLs are not covered by the data license. The API terms and data license are separate. See:

- https://www.openligadb.de/en/terms-of-use
- https://www.openligadb.de/en/license

This code change makes no provider request and does not approve recurring collection. OpenLigaDB remains conditional until the product's intended use is reviewed against the API terms and ODbL obligations.

## Validation

Offline tests cover raw-byte hashing, exact result-type preservation, missing/naive timestamps, duplicate IDs, malformed result rows, malformed roots and naive retrieval clocks. These tests validate parser behavior only, not provider accuracy, rights, coverage or prediction performance.
