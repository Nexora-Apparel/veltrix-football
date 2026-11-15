# VELTRIX FOOTBALL 2.0 — Stage 2: Rights-approved PIT historical data acquisition

Status: IN PROGRESS — four CC0 source scopes are documented and a bounded immutable-snapshot collector is implemented. A successful artifact capture, independent hash audit, staging persistence and cross-provider identity resolution remain outstanding.

## 1. Acceptance boundary

Each accepted observation must retain source/repository identity, exact competition/season path, immutable source revision, timezone-aware snapshot timestamp, actual retrieval timestamp, raw bytes and SHA-256, parsed payload hash, kickoff precision, licence evidence, permitted use, revision history and an archive proof ID.

A snapshot fetched today cannot be represented as if it had been captured on the match date. The current walk-forward evaluator still requires recorded_at <= cutoff. Retrospective archive-proof support must be integrated and tested separately before it can be used for historical backtests.

## 2. Rights-approved scope

The first pack covers six CC0-1.0 repositories and seven competition scopes: England Premier League, Spain La Liga, Germany Bundesliga, Italy Serie A, France Ligue 1, Brazil Serie A and Brazil Serie B. Three seasons are enumerated for the four European core leagues and France; Brazil Serie A uses 2024, 2025 and 2026 calendar-year files, while Brazil Serie B uses the available 2024 and 2025 files. The collector rechecks each repository's SPDX licence metadata at runtime.

The detailed scope review is docs/legal/openfootball-cc0-scope-review-2026-11-15.md. It covers text fixture/result facts only. It does not cover logos, media, odds, xG, lineups or player-level data. Competition/team IDs remain source-scoped pending evidence-backed crosswalks.

Nigeria NPFL is separate and must not be mapped to another competition by name or country alone. Brazil Serie B 2026 is absent from the selected archive and remains a season coverage gap.

## 3. Collector implementation

The manual-only workflow is .github/workflows/phase2-openfootball-pit-snapshot-pack.yml.

The collector:
- enumerates commit history for every approved source path;
- downloads each source version by immutable commit SHA;
- checks CC0-1.0 repository licence metadata;
- stores exact raw source snapshots and SHA-256 hashes;
- parses only results whose source snapshot clears the two-calendar-day safety boundary;
- records snapshot time separately from actual retrieval time;
- preserves score corrections as separate versions;
- deduplicates unchanged fixture/result versions;
- produces JSONL observations, snapshot proofs and a manifest;
- enforces request and history limits and refuses truncated histories;
- writes only a workflow artifact, never Neon or production.

## 4. Model-use boundary

The archive is date-only. It can provide historical result observations for future forecast feature construction after the archive snapshot and ingestion are both known. It cannot supply exact kickoff/rest-day features or become a historical walk-forward target set.

The archive proof ID is intended for the existing temporal_eligibility.evaluate_observation(..., archive_proof_verified=True) contract. The current MatchObservation walk-forward integration does not yet use that proof path. Do not bypass recorded_at <= cutoff or rewrite historical ingestion timestamps.

## 5. Historical odds blocker

The Odds API terms reviewed on 2026-11-14 permit model training and indefinite storage, but account evidence has not established historical-odds endpoint entitlement. Historical snapshots are a paid-plan endpoint with a documented 10-credit per region/market cost. No historical request is dispatched by this stage. The account tier and quota must be verified, then a separate hard credit cap and exact market/region scope must be recorded before any paid request.

5Dollar historical result rows remain settled labels but have no source-publication timestamp or complete revision history. They remain non-PIT for historical feature training. The four-day proxy is not promoted.

## 6. Stage 2 exit gates

1. Rights approval is complete for each selected source, competition, season and use.
2. Manual collector run completes without source failures, truncated histories or request-budget overruns.
3. Raw snapshot hashes and observation JSONL hash are independently recomputed.
4. Per-competition coverage, season gaps, duplicate fixture IDs, score revisions and rejected rows are reconciled.
5. Date-only observations remain non-targets; exact kickoff is never fabricated.
6. Evidence-backed competition/team crosswalks exist where data is combined with 5Dollar targets.
7. Guarded import to dedicated Neon staging is implemented and accepted; production remains untouched.
8. Historical odds entitlement is independently verified; otherwise odds remain unavailable.
9. Historical archive-proof eligibility is integrated into chronological evaluation without falsifying recorded_at.

No model fitting, public predictions, Telegram delivery, scheduling, value betting or production deployment is authorized by Stage 2.
