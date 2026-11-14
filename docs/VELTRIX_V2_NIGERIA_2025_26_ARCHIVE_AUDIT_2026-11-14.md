# VELTRIX FOOTBALL 2.0 — Nigeria 2025/26 free archive audit

## Source identity

- Repository: openfootball/world
- Source path: africa/nigeria/2025-26_ng1.txt
- Source commit: 94624a1b29c197cc9ac0d318a354e7f8062bb81e
- Committer timestamp: 2026-08-21T07:43:54Z
- Competition: Nigeria Professional League
- Season: 2025/2026
- Fixture lines observed: 380
- Ordinary scored results accepted: 379
- Awarded result explicitly excluded: 1
- License: repository identifies its football datasets as public domain/CC0

## Parser acceptance policy

The parser accounts for all 380 fixture lines. One score is annotated as awarded. That row is not silently treated as a normal played match. The exporter permits exactly one rejected row for this known annotation; any additional rejected scored row stops export.

## Time and evaluation policy

The source has calendar dates but no exact kickoff time or timezone. The import preserves kickoff_at as null and stores kickoff_date. It uses the exact source-file commit timestamp as the earliest repository-observed availability and the actual import time as recorded_at.

Date-only observations become eligible for future training only after 00:00 UTC two days after the source-local match date and after both provenance timestamps. They are not walk-forward target fixtures and cannot be backdated into historical model evaluation.

## Export verification

GitHub Actions run 43537526180 exported 379 JSONL observations and a manifest. The artifact SHA-256 is f3c2e4d7844a339ff95a04e7e3d77428ae94725b45cd2770a284e2688adaf37f. Independent verification confirmed 379 unique fixture IDs, 20 distinct team IDs and a matching observations JSONL hash.

## Operational boundary

The workflow writes a 30-day GitHub Actions artifact only. It does not write to Neon, production, staging, website, Telegram, or any schedule.
