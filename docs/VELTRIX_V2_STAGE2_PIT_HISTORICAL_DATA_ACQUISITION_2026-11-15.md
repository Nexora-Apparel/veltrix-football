# VELTRIX FOOTBALL 2.0 — Stage 2: Rights-approved PIT historical data acquisition

Status: IN PROGRESS — project-wide non-commercial source authorization is recorded; the pinned OpenPlay release (15 assets, 2,975,394 Parquet rows, 74,460,817 raw bytes) is qualified, imported into isolated Neon staging and independently read back. The OpenFootball archive pack is captured and hash-verified, but remains retrospective/date-only rather than proven historical PIT. Supplemental FootballData artifact verification, OpenFootball staging persistence, evidence-backed cross-provider identity resolution, genuinely PIT historical observations and historical odds access remain outstanding.

## 1. Acceptance boundary

Each accepted observation must retain source/repository identity, exact competition/season path, immutable source revision, timezone-aware snapshot timestamp, actual retrieval timestamp, raw bytes and SHA-256, parsed payload hash, kickoff precision, licence evidence, permitted use, revision history and an archive proof ID.

A snapshot fetched today cannot be represented as if it had been captured on the match date. The current walk-forward evaluator still requires recorded_at <= cutoff. Retrospective archive-proof support must be integrated and tested separately before it can be used for historical backtests.

## 2. Rights-approved scope

The OpenFootball base pack covers six CC0-1.0 repositories and seven competition scopes: England Premier League, Spain La Liga, Germany Bundesliga, Italy Serie A, France Ligue 1, Brazil Serie A and Brazil Serie B. Three seasons are enumerated for the four European core leagues and France; Brazil Serie A uses 2024, 2025 and 2026 calendar-year files, while Brazil Serie B uses the available 2024 and 2025 files. The collector rechecks each repository's SPDX licence metadata at runtime.

The detailed scope review is docs/legal/openfootball-cc0-scope-review-2026-11-15.md. It covers text fixture/result facts only. It does not cover logos, media, odds, xG, lineups or player-level data. Competition/team IDs remain source-scoped pending evidence-backed crosswalks.

The project-wide non-commercial source authorization is recorded in [the authorization register](legal/veltrix-all-source-noncommercial-authorization-2026-11-15.md). The pinned OpenPlay `data-v0.1.0` release is separately approved in Neon staging under `approval-openplay-whoscored-opta-noncommercial-2026-11-15`; all 15 raw release assets are persisted as immutable provider responses with linked source-observation metadata. Monetisation is prohibited. This rights decision does not make static OpenPlay data historically PIT.

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

**Stage 2 remains OPEN.** The OpenFootball base pack is an immutable, rights-cleared retrospective archive, not a demonstrated historical PIT feed. The supplemental FootballData pack requires its own latest artifact verification. No independently attested pre-match feature snapshots or timestamped historical bookmaker quotes have been demonstrated. The 5Dollar historical result rows remain non-PIT. The provider also exposes genuine timestamped odds ticks, but the user account previously verified as Free cannot access the full tick-history endpoint; it requires Ultra. The separate odds_quote rights approval is also absent. No historical odds endpoint request has been made.

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


## 9. Corrected archive regression outcome — 2026-11-15

The corrected code head `593b3fcd28ba1e0129e781652cb036daff9ca214` passed the following relevant checks:

- Phase 2 Data Foundation run [43712883985](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43712883985): SUCCESS. The OpenFootball archive parser, export script, rights-scoped OpenFootball snapshot pack, FootballData CC0 parser/snapshot pack, and chronological/date-only walk-forward test steps all completed successfully.
- PostgreSQL 16/18 historical foundation acceptance [43712884068](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43712884068): SUCCESS.
- Historical Model Audit [43712884051](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43712884051): SUCCESS.
- Certification Evidence Integrity [43712883984](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43712883984): SUCCESS.
- Phase 5 Shadow Regression [43712884088](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43712884088): CANCELLED during superseding commits; no pass is claimed for this run.
- Earlier Stage 2 collection workflow [43712824451](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43712824451): FAILED on the pre-test-correction commit `48c6e89f1915ef2543ff58d61f8cb5c88c9fc8e3`. Its two failures were stale expectations that archive commit time was PIT availability and that the retrospective archive could train a historical cutoff. The corrected tests passed in the later Foundation run, but the full external archive collection/verification workflow has not been rerun on the corrected code.

The latest PR head is `bc0a5f053b7e6a10e6b6d9f9e9d0bcaa30f4fbba`; this is a documentation-only commit after the tested code head above. No exact-head code test is claimed for the documentation-only commit.

**Final Stage 2 disposition for this execution window: NOT COMPLETE.** The timestamp misclassification has been corrected and the focused regression/integration checks passed. The actual Stage 2 exit gates remain unmet: a genuinely PIT-qualified historical source, independently verified source availability timestamps, confirmed supplemental artifact evidence, guarded staging import, and exact cross-provider identity resolution are still outstanding. No production data, schedules, Telegram or publication settings were changed.


## 10. 5DollarFootballAPI historical odds source qualification — 2026-11-15

### Provider evidence

Official provider documentation reviewed:
- Terms: https://5dollarfootballapi.com/terms (October 2026).
- API overview and history depth: https://5dollarfootballapi.com/docs.
- Odds movement history: https://5dollarfootballapi.com/docs/odds-history.
- Fixture and opening/closing odds: https://5dollarfootballapi.com/docs/fixture.

The October 2026 Terms permit using the data in models and internal tools, caching/storing responses and displaying data in user-facing products, while prohibiting redistribution of raw data as a competing feed. Free/Community/Education public-facing products require the documented attribution. This is an appropriate rights basis for an internal historical research collector, subject to a source-specific approval record.

The provider documents:
- GET /v1/fixtures/{id}/odds/history?market=1x2 returns the full pre-match and in-play price tick history, oldest first.
- Each tick includes recorded_at in UTC, prices, line and score state. These timestamps are the source observation times and are suitable for point-in-time odds reconstruction after raw-response verification.
- The same endpoint supports goalline, btts and other markets, with bookmaker/market-specific coverage.
- The full tick-history endpoint requires Ultra; Free and Pro receive HTTP 403 insufficient_plan.
- Free plan history is limited to the last three months; Pro to twelve months; Ultra reaches back to 2014 for supported competitions. Competition-specific coverage is not uniform.

### Current access and rights gate

The user's 5Dollar account was previously verified as Free. Therefore the full tick-history endpoint is not currently available. Do not attempt it, retry it, or label opening/closing summary prices as full timestamped tick history.

The existing database approval approval-5dollar-community-fixture-result-2026-11 is scoped to fixture_result; it does not explicitly approve odds_quote. The terms review supports model training and evaluation, but the persisted rights model requires an explicit data-type and purpose scope. Do not infer odds rights from the fixture-result approval.

### Acquisition design

Once the account has Ultra access and an explicit staging approval for odds_quote:
1. Enumerate finished fixtures only within the account's permitted competition/season scope and pin the query time window.
2. Fetch one 1x2 history response per fixture initially; request totals and BTTS only after their coverage and request cost are separately budgeted.
3. Persist raw response bytes, SHA-256, request manifest, retrieval timestamp, response status, allowlisted rate-limit headers and exact fixture/provider IDs.
4. Preserve every tick's recorded_at as source_published_at; never replace it with retrieval time.
5. Keep retrieval/recording time separate from source tick time.
6. Exclude in-play ticks from pre-match features; only use ticks whose source timestamp is strictly before the fixture kickoff and whose tick state is explicitly pre-match.
7. Preserve suspended/withdrawn rows and null prices as evidence, but never turn them into prices.
8. Deduplicate by provider fixture, bookmaker, market, selection/line and source tick timestamp; conflicting duplicate identities fail closed.
9. Reconcile raw hashes, row counts, timestamp coverage and per-competition coverage independently before staging import.

The 5Dollar results endpoint still does not provide the exact first-publication timestamp or a complete historical revision stream for final scores. Result rows remain outcome labels only; do not use them as historical pre-match form inputs under a fabricated publication timestamp. The separate OpenFootball/FootballData archives remain retrospective labels until a verified source-publication proof path is integrated.

### Stage 2 disposition

**BLOCKED — PLAN AND RIGHTS SCOPE**

No subscription change, paid request, API call or database rights mutation was performed. The next implementation task is a dry-run-first, rate-budgeted 5Dollar odds-history collector with strict recorded_at parsing and staging-only persistence. The first live acquisition must remain blocked until both the account's Ultra entitlement and a separate odds_quote approval are confirmed.


## 11. Community Access historical qualification key — 2026-11-15

The user selected Brazil as the Community Access country pack. The previous setup record confirms that Community Access had not yet been connected and that the ordinary Free API key must remain unchanged.

Community Access is a separate $0 plan. Official documentation states it adds one country pack, extends result/odds history from three to twelve months, and raises throughput to 300 requests/hour with a 20 requests/minute ceiling. It does not include full tick-by-tick odds history; that remains an Ultra/Education feature. It is suitable for the bounded one-year fixture/result qualification probe, not a replacement for the missing historical result publication timestamps or full odds-tick data.

The dry-run workflow now reads only the dedicated GitHub Actions secret:
- Secret name: FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY
- Existing Free secret FIVEDOLLARFOOTBALL_API_KEY is not overwritten or used by this workflow.
- Country pack expected by the allowlist: Brazil (Brazil Serie A and Brazil Serie B) in addition to the top-five leagues.

Manual blocker: activate Community Access on the provider account with Brazil selected, then add the Community credential as a repository Actions secret. The repository secret form is:
https://github.com/Nexora-Apparel/veltrix-football/settings/secrets/actions/new

Provider Community Access page:
https://5dollarfootballapi.com/community

Manual workflow:
https://github.com/Nexora-Apparel/veltrix-football/actions/workflows/phase2-historical-data-dry-run.yml

The workflow performs a read-only 365-day, 40-request qualification probe and emits a sanitized artifact. It does not import to staging or certify historical PIT eligibility. The result data remains non-PIT for feature reconstruction unless the provider supplies source publication/revision timestamps. Do not execute the Phase 3 staging importer as a substitute for this qualification or as a way around PIT requirements.


## 12. Community Access 1X2 opening-quote parser — 2026-11-15

The 5Dollar per-fixture odds response includes a timestamped Bet365 1X2 opening quote through the documented opened_at field. This quote is available on the Free and Community plans and is distinct from the full odds-history endpoint.

Implemented on the integration branch:
- Offline 1X2 opening-quote parser: veltrix_v2/providers/fivedollar_odds_history/fixture_odds_parser.py
- Regression tests: tests/providers/test_fivedollar_opening_odds.py
- The parser preserves opened_at and retrieved_at separately, verifies all three prices, rejects missing/naive/future timestamps, and only marks the quote eligible when opened_at is strictly before kickoff.
- Closing and in-play prices are deliberately ignored because their individual source timestamps are not present in this fixture response.
- The full tick-history parser remains separate and Ultra/Education gated.

Exact-head verification on commit e30d6d870da8cebc61eab483e7fcf587fa72ffc8:
- Phase 2 Data Foundation: SUCCESS; the new Community opening-quote parser test passed.
- Historical Model Audit: SUCCESS.
- PostgreSQL 16/18 integration and acceptance: SUCCESS.
- Phase 5 Shadow Regression: SUCCESS.
- Certification Evidence Integrity: SUCCESS.
- Daily fixture predictions: intentionally SKIPPED.

No Community API key has been connected to the workflow, no live 5Dollar odds request has been made, no quote observations have been persisted, and no source_approvals odds_quote record has been added. The parser is validated offline only.

### Stage 2 current disposition

The 12-month Community Access source path is ready for a bounded data qualification run once the dedicated Community credential is available. The separate key name is FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY; Brazil is the selected country pack. The existing Free credential remains unchanged.

Still outstanding:
1. User adds the Community credential as a GitHub Actions secret.
2. Run the read-only Community 365-day fixture/result qualification workflow.
3. Implement and run the bounded per-fixture 1X2 opening-quote collector, preserving raw-response hashes and opened_at/retrieved_at.
4. Add and independently verify the exact odds_quote rights approval and staging persistence contract.
5. Measure real timestamp coverage by competition/date; do not infer 98%.
6. Obtain a genuinely PIT result-feature source or keep historical form/strength features excluded from walk-forward evaluation.

Stage 2 remains OPEN. The new 1X2 opening-quote path is a qualified acquisition candidate, not yet an acquired dataset.


## 11. Project-wide non-commercial authorization and OpenPlay staging import — 2026-11-15

The project owner has confirmed that all source permissions obtained for VELTRIX FOOTBALL permit project use on the condition that the data and outputs are not monetised. The global policy is recorded at `docs/legal/veltrix-all-source-noncommercial-authorization-2026-11-15.md`; the OpenPlay / WhoScored / Opta-specific record is `docs/legal/openplay-whoscored-opta-authorization-2026-11-15.md`.

Both approval records are registered in Neon staging with `status=APPROVED`, `rights_basis=WRITTEN_PERMISSION` and `commercial_use_allowed=false`. The OpenPlay-specific approval also retains source attribution and prohibits standalone raw-feed redistribution. Rights-based quarantine is lifted for covered project sources. Endpoint entitlement, API limits, technical access, data quality and point-in-time evidence remain independent gates.

### OpenPlay release qualification and persistence

Workflow run [#43715142465](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43715142465) passed on commit `3dd2e77b5a00089833a7ba40e1da2551d5004b17`.

- Pinned release: `data-v0.1.0`, tag commit `ac0bd9aff52016066433ebebf818bec4278fcf54`.
- 10 Parquet tables and five supporting CSV/JSON files passed digest, schema and row-count checks.
- 2,975,394 Parquet rows represented across the ten tables.
- 15/15 exact raw release assets persisted to Neon `provider_responses`.
- 15/15 linked dataset-asset `source_observations) verified.
- 74,460,817 raw bytes stored; each asset SHA-256 was recomputed before insertion and read back.
- Capture manifest ID: `87`.
- Manifest SHA-256: `1a733d1c0c84ea93366cd5db7e52967517be8e7a11c3b1394b3abb882bed72ef`.
- Independent Neon read-back confirmed 15 raw assets, 15 linked observations, a completed capture-manifest event and non-commercial approval.

The OpenPlay assets are stored as immutable raw Parquet/CSV/JSON release files, linked by manifest and source-observation metadata. The importer does not claim every Parquet row is a separate normalized source_observation. The source bundle is available for DuckDB-based research/feature extraction from staging.

### Temporal classification

All 15 asset observations have:
- `available_at = retrieved_at` (actual VELTRIX import-time availability);
- `source_published_at = NULL`;
- `source_timestamp_basis = unknown`;
- `point_in_time_certifiable = false`.

This is deliberate. The release's static historical contents and commit metadata do not prove when each underlying event/statistic first became available to a forecaster. The data is now rights-approved and persistently captured, but it is not admitted as historical pre-match PIT features until independent source-availability evidence exists.

### Updated disposition

- Rights gate for project-authorized sources: **PASS**.
- OpenPlay release integrity and staging persistence: **PASS**.
- Immutable source bytes and manifest/read-back: **PASS**.
- OpenPlay row-level PIT certification: **NOT ESTABLISHED**.
- Genuine historical PIT source acquisition: **OUTSTANDING**.
- Cross-provider identity crosswalks: **OUTSTANDING**.
- Historical odds entitlement and 98% timestamp coverage: **OUTSTANDING**.
- Stage 2 overall: **OPEN**. No legacy prediction logic is reintroduced and no prediction, publication, value-betting, Telegram or scheduling gate is changed.


### Independent CI read-back acceptance — run #43715432543

The complete OpenPlay acquisition/import/audit workflow passed on exact commit `79e6ab4035c5fcf6ba33b073d08187059ca38502`:

- Release hash/schema qualification: PASS.
- Non-commercial rights-contract tests: PASS (6 tests).
- Guarded staging import: PASS.
- Independent read-only staging audit: `PASS_INDEPENDENT_STAGING_READBACK`.
- Raw assets: 15/15; bytes: 74,460,817.
- Linked source observations: 15/15.
- Parquet rows represented: 2,975,394.
- Manifest SHA-256: `1a733d1c0c84ea93366cd5db7e52967517be8e7a11c3b1394b3abb882bed72ef`.
- The independent audit re-hashed every stored BYTEA payload and verified its source-observation link, rights approval, non-PIT timestamp fields and completed manifest event.

The workflow is repeatable and idempotent. The second successful import reused the same manifest/assets rather than creating duplicate records.
