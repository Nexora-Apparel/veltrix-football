# VELTRIX FOOTBALL 2.0 — OpenFootball archive adapter

## Source and scope

The adapter parses OpenFootball Football.TXT files. The OpenFootball World repository identifies its football data as public domain/CC0 and includes Nigeria Premier Football League seasons. Each imported snapshot must be bound to an exact Git commit SHA and its commit timestamp; the parser does not infer availability from the file's human-readable retrieval comment.

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

- Date-only rows carry point-in-time-certified snapshot and import evidence and may inform future forecasts only after the conservative eligibility boundary.
- They may be training observations in a walk-forward fold only after their snapshot/import times precede that fold's cutoff; they are never evaluation targets because exact kickoff times are absent.
- They cannot be backdated to their match dates or used for historical pre-match backtesting.
- Team identity is source-scoped; cross-provider team mapping remains a separate, evidence-backed step.
- Unscored fixtures are counted but never converted into results.
- This adapter is offline and does not download data or call GitHub. A caller must supply the exact source snapshot and commit metadata.
