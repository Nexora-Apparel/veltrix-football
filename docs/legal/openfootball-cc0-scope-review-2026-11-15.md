# VELTRIX FOOTBALL 2.0 — OpenFootball CC0 rights scope review

Review date: 2026-11-15.

GitHub repository metadata was verified as CC0-1.0 (Creative Commons Zero v1.0 Universal) for the following sources:

| Repository | Competition | Source paths |
|---|---|---|
| https://github.com/openfootball/england | English Premier League | 2024-25/1-premierleague.txt; 2025-26/1-premierleague.txt; 2026-27/1-premierleague.txt |
| https://github.com/openfootball/espana | Spanish La Liga | 2024-25/1-liga.txt; 2025-26/1-liga.txt; 2026-27/1-liga.txt |
| https://github.com/openfootball/deutschland | German Bundesliga | 2024-25/1-bundesliga.txt; 2025-26/1-bundesliga.txt; 2026-27/1-bundesliga.txt |
| https://github.com/openfootball/italy | Italian Serie A | 2024-25/1-seriea.txt; 2025-26/1-seriea.txt; 2026-27/1-seriea.txt |

## Approved internal use

Subject to CC0-1.0 and applicable law, the selected text fixture/result facts are approved for COLLECTION, STORAGE, HISTORICAL_IMPORT, MODEL_TRAINING and BENCHMARKING. This review does not cover team logos, photographs, video, commentary, player biographies, bookmaker odds, xG or lineup data.

The runtime collector rechecks each repository's SPDX identifier and refuses any source that is not CC0-1.0. Rights approval ID: approval-openfootball-cc0-archive-2026-11-15.

## Temporal and provenance requirements

- Fetch each source version by immutable Git commit SHA.
- Retain exact raw source bytes and SHA-256.
- Preserve the source commit timestamp and actual retrieval/recording timestamp separately.
- Preserve score corrections as separate immutable versions.
- Retain date-only kickoff precision; never invent a kickoff clock or timezone.
- Enforce the existing two-calendar-day UTC safety boundary for date-only results.
- Never backdate a current snapshot to the match date.
- Keep competition/team identifiers source-scoped until independently evidenced crosswalks exist.

The archive proof links repository, path, commit SHA, commit timestamp, raw-content hash, CC0 licence identifier and approval ID. The current model evaluator still requires recorded_at <= cutoff. Historical archive-proof integration must be separately implemented and tested; this review does not authorize changing import timestamps to bypass that rule.

## Exclusions

France Ligue 1 and Brazil Serie A/B are not included in this first pack because their exact source repository/path and licence evidence have not yet been verified. Nigeria NPFL remains a separate source scope. No third-party assets or odds are included.

Decision: approve the four listed CC0 repositories for the stated internal uses. This rights approval alone does not certify individual rows, source completeness, cross-provider identity or market performance.
