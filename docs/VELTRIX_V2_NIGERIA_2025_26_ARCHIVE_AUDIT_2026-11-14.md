# VELTRIX FOOTBALL 2.0 — Nigeria 2025/26 free archive audit

## Source identity

- Repository: openfootball/world
- Source path: africa/nigeria/2025-26_ng1.txt
- Source commit: 94624a1b29c197cc9ac0d318a354e7f8062bb81e
- Committer timestamp: 2026-08-21T07:43:54Z
- Competition: Nigeria Professional League
- Season: 2025/2026
- Declared matches: 380
- License: repository identifies its football datasets as public domain/CC0

## Parser acceptance policy

The parser must account for all 380 fixture lines. The current source snapshot contains one score annotated as awarded. That row is not silently treated as a normal played match.

Expected export:
- 380 fixture lines observed.
- 379 ordinary scored results accepted.
- 1 awarded result explicitly excluded and listed in rejected_annotations.
- Any additional rejected scored row causes the default exporter to stop. The workflow permits exactly one rejected row for this known annotation.

## Time and evaluation policy

The source has calendar dates but no exact kickoff time or timezone. The import preserves kickoff_at as null and stores kickoff_date. It uses the exact source-file commit timestamp as the earliest repository-observed availability and the actual import time as recorded_at.

Date-only observations become eligible for future training only after 00:00 UTC two days after the source-local match date and after both provenance timestamps. They are not walk-forward target fixtures and cannot be backdated into historical model evaluation.

## Operational boundary

The export workflow is manual-dispatch only. It writes a JSONL file and provenance manifest as a GitHub Actions artifact; it does not write to Neon, production, staging, website, Telegram, or any schedule.
