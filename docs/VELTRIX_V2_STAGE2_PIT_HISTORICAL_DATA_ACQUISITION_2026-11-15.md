# VELTRIX FOOTBALL 2.0 — Stage 2: Rights-approved PIT historical data acquisition

Status: IN PROGRESS — the OpenFootball base pack has been captured and independently verified (5,182 unique result versions across 20 source paths, 49 snapshots, 375/500 requests, zero source failures). The supplemental CC0 FootballData Brazil Serie B collector and independent verifier are implemented and included in the same bounded workflow; the latest artifact verification result still needs confirmation. Staging persistence, exact rights-scope records, archive-proof model integration and cross-provider identity resolution remain outstanding.

## 1. Acceptance boundary

Each accepted observation must retain source/repository identity, exact competition/season path, immutable source revision, timezone-aware snapshot timestamp, actual retrieval timestamp, raw bytes and SHA-256, parsed payload hash, kickoff precision, licence evidence, permitted use, revision history and an archive proof ID.

A snapshot fetched today cannot be represented as if it had been captured on the match date. The current walk-forward evaluator still requires recorded_at <= cutoff. Retrospective archive-proof support must be integrated and tested separately before it can be used for historical backtests.

## 2. Rights-approved scope

The OpenFootball base pack covers six CC0-1.0 repositories and seven competition scopes: England Premier League, Spain La Liga, Germany Bundesliga, Italy Serie A, France Ligue 1, Brazil Serie A and Brazil Serie B. Three seasons are enumerated for the four European core leagues and France; Brazil Serie A uses 2024, 2025 and 2026 calendar-year files, while Brazil Serie B uses the available 2024 and 2025 files. The collector rechecks each repository's SPDX licence metadata at runtime.

The detailed scope review is docs/legal/openfootball-cc0-scope-review-2026-11-15.md. It covers text fixture/result facts only. It does not cover logos, media, odds, xG, lineups or player-level data. Competition/team IDs remain source-scoped pending evidence-backed crosswalks.

Nigeria NPFL is separate and must not be mapped to another competition by name or country alone. The OpenFootball archive has only 57 Brazil Serie B 2025 results and no 2026 file. A supplemental CC0 FootballData archive is being captured separately: 2025 full-season JSON plus a 2026 partial snapshot dated 2026-07-08. The supplemental source's reported clock has no timezone, so kickoff_at remains null.

## 3. Collector implementation

The bounded push/manual workflow is .github/workflows/phase2-openfootball-pit-snapshot-pack.yml. It emits separate OpenFootball and FootballData artifacts; neither writes to staging or production.

The OpenFootball collector:
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

The supplemental FootballData parser preserves the reported local clock string but does not infer its timezone. Numeric suffixes after newline team names are normalized only when the clean base name is present in the same snapshot; each normalization is retained in the audit manifest. These source-scoped IDs are not joined to OpenFootball or 5Dollar yet.

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


## 7. Independent temporal-semantics audit — 2026-11-15

**Important correction: the current CC0 archive packs are not yet proof of historical point-in-time public availability.**

The collector currently reads GitHub commit metadata `commit.committer.date` and labels it as `source_snapshot_available_at` / `source_published_at`, with `source_timestamp_basis=archival_snapshot_timestamp`. The verifier recomputes the commit SHA, raw snapshot hash, parsed observation set and archive-proof hash. This proves the identity and integrity of the source version and its commit metadata. It does **not**, by itself, prove the date on which that version first became publicly available to a forecaster. Git commit timestamps are commit metadata and are not equivalent to an independently attested provider publication timestamp or immutable provider-side as-of snapshot.

The current OpenFootball and supplemental FootballData parsers also set `point_in_time_certifiable=True`. That flag is too strong for historical-cutoff certification unless the source-availability semantics are independently established. A CC0 licence establishes reuse rights; it does not establish temporal availability.

### Safe current model boundary

- Do not treat the repository commit timestamp as a verified public publication timestamp.
- Do not use the archive proof to bypass the walk-forward evaluator's `recorded_at <= cutoff` requirement. The current evaluator's recorded-time check correctly prevents data imported in November 2026 from entering a historical training fold whose cutoff predates that import.
- Do not set historical `available_at` to the commit timestamp as a substitute for first-observed availability.
- Keep source commit timestamp, actual collector retrieval/import timestamp, and any independently verified source-publication timestamp as separate fields.
- Keep the archive pack as rights-approved, immutable retrospective source material. It is useful for source reconstruction, result-label comparison and future model inputs only from a defensible first-observed/availability time; it is not admitted as a historical PIT training dataset on the evidence currently available.
- The GitHub SHA/raw-hash verifier remains useful for content integrity and revision reconstruction, but it is not a temporal-availability attestation.

### Required remediation before any PIT admission

1. Correct both archive parsers and both observation serializers so Git commit time is stored only as `source_commit_timestamp`, never represented as verified `source_published_at`.
2. Record actual `retrieved_at` / `recorded_at` as the earliest defensible VELTRIX availability time; use that time for any prospective feature eligibility.
3. Set archive-derived rows to non-historical-PIT status unless an independent provider/publication attestation establishes source availability before the relevant cutoff.
4. Update independent verifiers and regression tests to reject commit-time-as-publication substitutions and any archive-proof attempt to bypass post-cutoff retrieval/recording.
5. Keep date-only kickoff precision and unknown timezone explicit; these rows cannot become exact-kickoff historical targets.
6. Do not import to operational staging until the corrected schema/serializer, append-only evidence links, rights scope, identity crosswalk and independent read-after-write reconciliation are all verified.

### Current Stage 2 decision

**Stage 2 remains OPEN.** The OpenFootball base pack is an immutable, rights-cleared retrospective archive, not a demonstrated historical PIT feed. The supplemental FootballData pack requires its own latest artifact verification. No independently attested pre-match feature snapshots or timestamped historical bookmaker quotes have been demonstrated. The 5Dollar historical result rows remain non-PIT. No historical odds endpoint request has been made.

The latest exact-head CI on commit `9bd078cd741248feb50aadcaf337b37f32dc5db5` reports Phase 2 foundation, Phase 5 shadow regression, historical model audit, certification evidence integrity and PostgreSQL 16/18 acceptance all successful; the daily fixture workflow is intentionally skipped. These are software/integration checks, not evidence that the source archives are PIT or that Stage 2 has passed.

**No-go:** do not mark Stage 2 complete, do not run historical walk-forward evaluation using these archive commit timestamps as pre-match publication times, and do not loosen the temporal evaluator. The next implementation task is the parser/serializer/verifier correction above, followed by a separately qualified genuine PIT source acquisition.


## 8. Temporal-semantics remediation implementation — 2026-11-15

The first corrective implementation is now committed on the integration branch:

- OpenFootball parser: `e8745dd6679a005d7a2475768118e6e9bee35cc0`
- FootballData parser: `863380763133b5d9205a31262b27b7d95194472c`
- OpenFootball collector: `78ba613965c7678312d3c41f9288be06b0aa8504`
- OpenFootball independent verifier: `0e891ec19176e84e601878a57216aacf2f209b4f`
- FootballData collector: `81b6da325a94527616f581f00c0b802f1a92377c`
- FootballData independent verifier: `685282e8b9f258601e8de37f8f0fc409c3825343`
- Model prospective-availability allowlist: `6e43e4c3befb49f8e628d9fd95f3034252e1be8c`
- Archive pack and parser regression assertions: `4f029771b9c0ec5eb7c17c3577d1de4fe80cdd64`, `6e59a9f4d1044053956c8daa5faa425423c47f1b`, `2e88bac3d225ea0f9ce263660ea7a69dbf9d4830`, `20085045a590d6a6a134e7f4b351822aa4ce32af`, `593b3fcd28ba1e0129e781652cb036daff9ca214`.

The corrected contract is:
- Git commit time remains available as `source_commit_timestamp` / `source_snapshot_available_at` metadata only.
- Archive rows have `source_published_at=null` and `source_timestamp_basis=unverified_repository_commit_timestamp`.
- Archive row `available_at` and `recorded_at` now use the actual collector import/retrieval time.
- Both archive parsers set `point_in_time_certifiable=false`.
- A distinct `archive_first_observed_at_import_v1` availability basis is recognized only by the explicit prospective-observation path; it does not enter the historical walk-forward training path, which still requires `point_in_time_certifiable=true`.
- OpenFootball metadata retains the actual source commit timestamp separately from import time.

The first Stage 2 workflow run on the initial parser correction (run 43712824451, commit `48c6e89f1915ef2543ff58d61f8cb5c88c9fc8e3`) failed two legacy assertions that still expected commit-time availability and historical training eligibility. Those assertions were corrected: archive availability must equal import time, and the archive cannot train a historical PIT forecast without independent source-publication evidence.

The updated foundation regression run on commit `593b3fcd28ba1e0129e781652cb036daff9ca214` is in progress at the time of this note. No pass is claimed until the exact-head checks finish. The Stage 2 archive-collection workflow itself has not been rerun on this corrected head.

**Stage 2 remains OPEN.** This correction removes an unsafe PIT claim; it does not create the missing historical as-of data. Staging import, identity crosswalk integration, external historical PIT provider evidence and verified historical odds remain outstanding.
