# VELTRIX FOOTBALL 2.0 — OpenFootball archive adapter

## Source and scope

The adapter parses OpenFootball Football.TXT files. The OpenFootball repositories used by VELTRIX identify their football data as CC0-1.0. Each imported snapshot must be bound to an exact Git commit SHA, the commit timestamp, exact source-content hash and actual retrieval timestamp; the parser does not infer availability from the file's human-readable retrieval comment. The Stage 2 collector rechecks the repository SPDX licence metadata at runtime.

## Temporal precision

The archive format provides match calendar dates but no exact kickoff clock or timezone. The adapter therefore stores kickoff_at as null and retains the original kickoff_date. It never fabricates a kickoff time.

For date-only observations, model eligibility is conservatively delayed until 00:00 UTC two calendar days after the source-local match date. This bounds timezone uncertainty (including UTC-12) and prevents a date-only match from leaking into a forecast made on the same or immediately following UTC date. The exact source snapshot commit timestamp and actual local import timestamp must also be at or before the forecast cutoff.

## Provenance

- snapshot_commit_sha: exact GitHub commit that introduced the source file version.
- snapshot_available_at: timestamp from that commit's GitHub metadata.
- imported_at: caller-supplied actual ingestion timestamp.
- content_sha256: hash of exact UTF-8 source text.
- source_path, competition, season title and source-prefixed team IDs are retained.

## Limitations

- Date-only rows are candidates for future forecast features only after both the source snapshot and actual import timestamps are at or before the forecast cutoff and the conservative eligibility boundary has passed; the production feature path remains gated until the Stage 2 artifact and identity crosswalks are independently verified.
- They are never walk-forward evaluation targets because exact kickoff times are absent. The current model evaluator also requires recorded_at <= cutoff, so a snapshot imported today cannot be silently used for a historical cutoff before today's import. Retrospective archive-proof integration is a separate gate.
- They cannot be backdated to their match dates or used for historical pre-match backtesting.
- Team identity is source-scoped; cross-provider team mapping remains a separate, evidence-backed step.
- Unscored fixtures are counted but never converted into results.
- This adapter is offline and does not download data or call GitHub. A caller must supply the exact source snapshot and commit metadata.
