# VELTRIX FOOTBALL 2.0 — Master Build Register

**Snapshot date:** 2026-11-15  
**Repository:** `Nexora-Apparel/veltrix-football`  
**Canonical integration branch:** `integration/v2-report-bundle-wiring-20261114`  
**Canonical integration PR:** [#120](https://github.com/Nexora-Apparel/veltrix-football/pull/120) — open, draft, unmerged at the latest recorded project audit  
**Purpose:** One durable inventory of the VELTRIX FOOTBALL 2.0 system: what exists, what has been tested, what has been operated against staging, what remains incomplete, what has deliberately been disabled, and where its detailed implementation/evidence lives.

> This register is an index and status map, not a substitute for source code, rights contracts, immutable workflow artifacts, database readbacks or certification evidence. Status labels distinguish implementation from verified operation. The snapshot is based on the repository's existing Stage 2 ledger, acquisition report, release-readiness report and their dated evidence entries. Where those records contain different historical snapshots, the latest dated, specifically scoped entry takes precedence; old values are retained as history, not silently treated as current.

## 1. Product objective and operating boundary

VELTRIX FOOTBALL 2.0 is being rebuilt as an evidence-led football analysis and reporting system. The intended product is to research and analyse up to 25 eligible fixtures per day and produce a consistent report for the website and Telegram, with the intended delivery time of 06:00 West Africa Time.

The architecture retains the website, API/command-centre and Telegram delivery infrastructure where suitable, while replacing the legacy prediction logic with an independently validated V2 system. The current work is still internal engineering and shadow/evidence collection.

**Not currently authorised or accepted:** public prediction publication, value-bet release, scheduled 06:00 WAT operation, real Telegram broadcast, production deployment, or production database writes/migrations. The user previously instructed that the schedule be stopped; do not reactivate it without a new explicit instruction and all release gates passing.

## 2. Architecture inventory

| Domain | What has been built | Current status / boundary |
|---|---|---|
| Repository integration | Canonical V2 integration branch and consolidated PR #120; historical phase PRs reviewed and superseded/closed without merging | Integration candidate only; PR remains draft/unmerged |
| Data foundation | Provider response/observation evidence contracts, rights-aware admission, source provenance, timestamp semantics, immutable hashes and staging-oriented ingestion paths | Implemented across V2 modules; each provider/data class has its own eligibility limits |
| Provider adapters | 5DollarFootballAPI core and Community paths; OpenPlay/WhoScored/Opta staging pipeline; OpenFootball archive collector; FootballData CC0 supplemental collector; The Odds API discovery/quote research; GOAL/Striker provider references | Different providers have different rights, quota, evidence and availability status; see Sections 4–5 |
| Identity | Provider-scoped fixture/team/competition crosswalk structures and conservative exact-ID/alias matching | Partial; unresolved or ambiguous identities remain quarantined; no fuzzy display-name-only joins |
| Temporal/PIT layer | Observation timestamps, source publication/availability evidence, cutoff evaluation, archive-proof concepts and strict `recorded_at <= cutoff` enforcement | Software foundations exist; most imported historical rows are not PIT-certifiable |
| Feature construction | OpenPlay feature sidecar, feature provenance/exclusion markers and feature-aware challenger foundations | Sidecar is built and staged; not admitted as certified model training input |
| Forecast/model layer | New Poisson, Elo, team-form, challenger comparison and forecast-evidence foundations | Implemented as software foundations; not certified; legacy priors/fallback logic are excluded |
| Evaluation | Chronological walk-forward, calibration/reliability, Brier/log-loss comparison, date-clustered bootstrap and historical model audit surfaces | Implemented/tested in code; eligible evidence is insufficient for market certification |
| Paper/shadow tracking | Append-only prospective ledger, hash-chain verification, duplicate protection, first-observed shadow forecasts, settlement runner and aggregate scorecard path | Shadow evidence only; 25 predictions, zero settlements at the latest recorded audit |
| Odds | Opening-odds capture path, odds observation schema/migration, provider quote provenance and bookmaker benchmark contracts | Capture code exists; quote coverage remains zero in latest staging readback; historical odds entitlement is not established |
| Certification | Strict publication verifier, evidence-manifest byte/hash checks, source-rights evidence checks, market thresholds and release fail-closed contracts | Verifier exists; no qualifying real certification manifest/attestation is present |
| Report bundle | Canonical report identity, immutable multi-surface bundle, per-surface hashes, portable one-file envelope and commit marker | Adapter/test foundations exist; certified production bundle not present |
| Website | V2 report/dashboard loaders, portable bundle preference, bounded fetch/cache, no legacy fallback and verifier-dependent fail-closed state | Code exists; without trusted runtime verifier and certified bundle, V2 predictions remain unavailable |
| API/command centre | FastAPI publication-verifier injection, dashboard/report loaders and V2 command integration | Code exists; trusted production bootstrap/configuration is not accepted |
| Telegram | V2 command router/renderer, certified-market-only output, locked value verdict, bundle-verifying dispatch adapter and durable at-most-once delivery claim/reconciliation design | Adapter and regression tests exist; live broadcast/runner remains disabled/unaccepted |
| Scheduling/operations | Manual-only provider capture and settlement workflows, workflow guards, quota checks and operational audit tooling | No active daily schedule; dispatch availability depends on default-branch workflow exposure |
| Database | Neon staging/rehearsal schema and migrations through 0011 in documented branches; read-only inspectors and acceptance tests | Staging only; verify exact target branch before any migration or write |
| CI/quality | Foundation, PostgreSQL 16/18 acceptance/integration, Phase 5 shadow regression, historical audit and certification integrity checks | Many exact-head runs passed at recorded checkpoints; always recheck current PR head before asserting current CI status |

## 3. Implemented V2 subsystems and key paths

### 3.1 Data evidence and temporal foundations

The V2 data layer separates:
- source/provider identity from internal VELTRIX identity;
- source publication time from retrieval/recording time;
- kickoff time from result availability;
- raw provider response bytes from parsed observations and derived features;
- rights approval from PIT eligibility;
- staging admission from model-use eligibility.

Evidence contracts preserve source identifiers, hashes, rights metadata, retrieval timestamps, source timestamp precision, revision information and provenance. The evaluator must not accept an observation for a historical cutoff when its recorded time is after that cutoff. Imported or downloaded data is not backdated.

Key implementation areas include:
- `veltrix_v2/data/`
- `veltrix_v2/temporal_eligibility.py`
- `veltrix_v2/ledger/`
- `scripts/veltrix_v2/`
- `tests/veltrix_v2/`

### 3.2 OpenPlay / WhoScored / Opta

**Rights:** user-confirmed non-commercial authorization, conditioned on no monetisation. The approval is not a blanket commercial licence.

**Pinned release:** `data-v0.1.0`, commit `ac0bd9aff52016066433ebebf818bec4278fcf54`.

**Captured release:** 10 Parquet assets, 2,975,394 total rows; six feature tables contain 2,927,621 rows. The separate release/staging documentation also records 15 raw release assets persisted as immutable provider responses; do not conflate raw asset count with the 10 Parquet feature assets.

**Pipeline:** qualification, isolated Neon staging import, independent read-back, timestamp inheritance audit, identity crosswalk construction, feature-bundle generation and non-raw artifact upload.

**Feature sidecar:** 20,178 derived JSONL rows. Bundle JSONL SHA-256:
`9ed328dd7c9ae235c47252e32bde0bb06d2a030ec38d151eeda7de264408bdc1`

Artifact SHA-256:
`5e101a56f8f68b9b6bc6f9982bc3e282aa76e5f2c96a6b4fd91c31d412a2e3cc`

Workflow: [#43723395022](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43723395022), artifact [#14165995516](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43723395022/artifacts/14165995516).

**Quality controls:** 89 team mappings and 5 competition mappings resolved. 646 duplicate rows quarantined in the pinned release accounting; the later feature-pipeline audit reports 644 formation rows and 2 player-match-stat rows quarantined. 46 matches excluded for known gaps/data issues; 16,389 excluded for unresolved identities. The invalid `possession_pct` metric was removed from usable features: all 20,178 rows carry `SOURCE_VALUES_VIOLATE_DOCUMENTED_PERCENTAGE_RANGE`; no inferred rescaling was applied.

**Boundary:** feature sidecar only. It is not a trained model, does not retroactively make the observations PIT, and must not be monetised or redistributed as raw data. Preserve attribution and provenance.

### 3.3 OpenFootball CC0 archive

Existing implementation:
- `scripts/veltrix_v2/collect_openfootball_pit_snapshots.py`
- `scripts/veltrix_v2/verify_openfootball_pit_snapshot_pack.py`
- `tests/veltrix_v2/test_openfootball_pit_snapshot_pack.py`
- `.github/workflows/phase2-openfootball-pit-snapshot-pack.yml`

Scope recorded: six CC0-1.0 repositories, seven competition scopes (England Premier League, Spain La Liga, Germany Bundesliga, Italy Serie A, France Ligue 1, Brazil Serie A and Brazil Serie B). Collectors enumerate immutable commit revisions, check licence metadata, preserve raw bytes/hashes, parse bounded results, retain corrections as versions and produce manifests/proofs. Workflow artifacts only; no Neon or production writes.

**Boundary:** source facts are retrospective/date-only. Git commit time is not independent proof of first public availability. No fabricated `available_at`; no bypass of the PIT cutoff. Keep archive results non-PIT until independent temporal evidence and evaluator support exist. Nigeria NPFL remains a separate competition; do not map it by country/name alone.

### 3.4 FootballData CC0 supplemental archive

Existing implementation:
- `scripts/veltrix_v2/collect_football_data_cc0_snapshots.py`
- `scripts/veltrix_v2/verify_football_data_cc0_snapshots.py`
- `tests/veltrix_v2/test_football_data_cc0_snapshots.py`

Captured scope described in the acquisition record: 2025 full-season JSON plus a 2026 partial snapshot dated 2026-07-08. The source-reported clock has no timezone; kickoff timestamp remains null. Source-scoped IDs are not automatically joined to OpenFootball or 5Dollar.

**Boundary:** supplemental retrospective archive, not PIT-certified. Reuse its collector/verifier; independently verify the existing workflow artifact rather than rebuilding it.

### 3.5 5DollarFootballAPI core and Community

- Core provider key secret name: `FIVEDOLLARFOOTBALL_API_KEY`.
- Community provider key secret name: `FIVEDOLLARFOOTBALL_COMMUNITY_API_KEY`; user confirmed it has already been added. Never ask for it again unless a workflow explicitly reports it missing/invalid. Never expose secret values.
- Community qualification implementation: `scripts/phase2_fivedollar_history_dry_run.py`.
- Community workflow: `.github/workflows/phase2-historical-data-dry-run.yml`.
- Related tests: `tests/test_phase2_data_foundation.py`.
- Opening-odds capture: `scripts/phase2_capture_fivedollar_opening_odds.py`.
- Opening-odds tests: `tests/providers/test_fivedollar_opening_odds.py`.
- Opening-odds workflow: `.github/workflows/phase2-5dollar-opening-odds-capture.yml`.

A provider-scope predicate bug was fixed: approval competition IDs are provider competition IDs and must be compared with `provider_competition_id`, not the internal `competition_id`. Related commits: `58a7c79f052416f9a3fd14eb439b7b731bc7254d`, `4a9b41ca69c63932bc17184c6e7cb2be0a416233`, `c0ff02f2b021cf9afbe942056e011e59cc9cbc4a`.

A read-only opening-odds staging audit found 763 eligible candidates, 763 scope matches, 763 resolved fixture crosswalks, and zero opening quote observations, endpoint responses or historical odds tick responses at that audit. 763 candidates are not odds coverage.

A separate bounded manual capture run [#43699365581](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43699365581) made 14 provider requests and persisted 671 raw first-observed result rows; 660 were converted observations. All 671 remained non-PIT with no source publication timestamp. Twenty-five upcoming fixtures were mapped to shadow forecast candidates. Duplicate protection prevented new ledger events because those fixture/model-version keys already existed. Subsequent fixes added duplicate-only status reporting and post-commit read-back verification of the ledger hash chain.

Rights-related personal-use checks were corrected to use `commercial=False` in:
- `veltrix_v2/data/fivedollar_engine.py`
- `veltrix_v2/ledger/admission.py`
- `veltrix_v2/data/provider_evidence_capture.py`

These corrections remove a false commercial-permission prerequisite; they do not broaden the source purpose/scope or grant raw redistribution. Community rights approval/test reconciliation has now been implemented on the integration branch: source-specific record `docs/legal/5dollar-community-noncommercial-authorization-2026-11-15.md`, approval ID `approval-5dollar-community-fixture-result-benchmarking-2026-11-14`, `commercial_use_allowed=False`, and a focused regression test. The offline test has not yet been run; the bounded Community qualification remains NOT RUN pending test execution and safe workflow dispatch.

### 3.6 Other data and odds sources

- **The Odds API:** terms/owner scope reviewed for specified soccer competitions/markets; account entitlement, current quota and event-market quote evidence are not established in the latest detailed audit. Catalogue responses are not event odds. Historical endpoint is paid and requires verified entitlement, cost cap and request reservation before use.
- **GOAL API / StrikerAPI:** previous monthly credits exhausted; do not call, probe, retry or top up before reset and fresh authorization.
- **API-Football/API-Sports:** previously suspended twice; not the primary source.
- **Highlightly:** insufficient coverage for the required data role.
- **InferSports:** supplemental discovery only; no verified historical archive, BTTS or quote-time coverage in the current evidence record.

### 3.7 Cross-provider identity

The system has source-scoped identifiers and exact crosswalk structures. OpenPlay currently has 89 team and 5 competition mappings. 5Dollar staging audit found 763 resolved fixture crosswalks in its target scope. OpenFootball and FootballData IDs remain source-scoped until evidence-backed mapping is available.

No fuzzy/display-name-only joins. Ambiguous entities remain quarantined. Do not map NPFL to another league based on name/country similarity.

## 4. Model, evaluation and shadow evidence

### 4.1 Rebuilt model foundations

V2 code includes new Poisson, Elo, team-form, challenger comparison, calibration and chronological evaluation foundations. These are separate from the old prediction stack and are not certified simply because code or tests exist.

No legacy home-default prior, generic fallback probability, legacy feature logic or legacy prediction decision rule is to be reintroduced into V2. No unsupported probability should be published when source evidence is insufficient.

### 4.2 Evaluation and certification targets

The release verifier and evaluation framework encode the following targets:
- At least 1,000 chronological walk-forward matches per market.
- At least 300 prospective settled selections.
- At least 90 distinct prospective dates.
- At least 98% timestamped pre-kickoff odds coverage.
- Net ROI above zero and a date-clustered 95% lower ROI confidence bound above zero.
- 1X2 must beat a de-vigged bookmaker baseline on both Brier score and log loss using the identical eligible fixture set.
- Certification and rights evidence must be bound to exact bytes/hashes and correct model/feature identities.
- Markets are evaluated independently; value betting is separately locked.

These are acceptance thresholds, not achieved metrics.

### 4.3 Prospective ledger and settlement

Built components include:
- append-only paper/shadow ledger;
- hash-chain and event-hash verification;
- fixture/model identity checks;
- duplicate protection;
- first-observed shadow forecast classification;
- manual-only settlement workflow and aggregate scorecard;
- quota headroom checks;
- fresh-connection post-commit verification.

Latest detailed readback: 25 shadow prediction events for 25 unique fixtures, zero prospective settlements, and one forecast session/date. This does not satisfy the 300-settlement or 90-date requirements. A later bounded capture did not append new events because all 25 fixture/model keys were duplicates. The settlement runner is manual-only and waits for eligible target kickoffs; do not claim settlement completion.

## 5. Odds evidence and bookmaker benchmarking

Built:
- odds quote observation schema/migration path;
- source/market/region/fixture provenance contracts;
- opening quote capture workflow and CLI;
- timestamp and retrieval-time eligibility checks;
- decimal-odds range validation;
- exact fixture crosswalk requirement;
- changed-price immutability tests;
- bookmaker baseline/de-vig comparison contracts.

Outstanding:
- actual timestamped event-market quote capture;
- provider entitlement/quota and hard cost-cap evidence;
- 98% eligible quote coverage;
- bookmaker benchmark on the same eligible 1X2 fixture set;
- historical odds rights and availability.

No paid historical odds calls or credit spending without recorded entitlement, scope, request cap and cost evidence.

## 6. Certification and immutable report delivery

### 6.1 Certification verifier

The pure V2 publication verifier checks report identity, exact evidence bytes/hashes, certification manifest and attestation, per-market thresholds, rights approval evidence and publication status. It rejects caller-supplied status booleans/labels as proof. Public market whitelist is 1X2, BTTS and TOTALS_2_5; value betting cannot be unlocked by a generic publication certificate.

A valid certification bundle has not yet been produced. A file-integrity check is not model certification. The attestation workflow or verifier utility existing in the repository is not itself a release certificate.

### 6.2 Portable report bundle

Built components include:
- canonical report identity and hash verification;
- website/scheduled/Telegram surface parity checks;
- immutable canonical, scheduled, Telegram and website surface artifacts;
- one portable bundle containing all four surfaces and their hashes;
- final commit marker binding the four surface files and portable bundle;
- bounded 8 MB website retrieval and 30-second repository/branch-scoped cache;
- strict JSON parsing, including duplicate-key rejection;
- rejection of empty reports, duplicate fixture IDs and more than 25 fixtures;
- read-back bundle verifier and offline CLI;
- authorization-gated scheduled consumer;
- Telegram bundle-verifying dispatch adapter;
- durable at-most-once delivery claims and append-only uncertain-outcome reconciliation evidence.

The bundle adapters have CI-level integration coverage using the same bytes, controlled verifier and stub Telegram transport. This is adapter parity, not production end-to-end delivery acceptance. A certified portable bundle and matching attested manifest remain absent from the command-data branch in the latest detailed release audit.

## 7. Website, API and Telegram implementation

### 7.1 Website/dashboard

- V2 loaders prefer the portable report bundle.
- Invalid or unauthorized present bundle fails closed; no fallback to legacy forecasts.
- Browser-side raw GitHub/CDN fallbacks to legacy `dashboard_snapshot.json` and `paper_tracking_ledger.json` were removed.
- Browser consumes `/api/dashboard-data`; without trusted V2 verifier/report it displays unavailable state.
- Bounded fetch, size cap and cache are implemented.
- Legacy experimental labels/static fallback paths are removed or covered by regression guards.

### 7.2 FastAPI command centre

- Publication-verifier injection point is exposed server-side.
- Dashboard/report and Telegram command loaders receive the configured verifier.
- Legacy paper-ledger/model-validation snapshots are not loaded into V2 dashboard/Telegram command responses.
- No production bootstrap currently has an accepted trusted verifier configuration; fail-closed unavailable behaviour is intentional.

### 7.3 Telegram

- Webhook command router uses `veltrix_v2.reporting.telegram_commands.handle_v2_command`, not the legacy `app.telegram_commands.handle_command`.
- `/1x2`, `/btts`, `/overunder` render only explicitly certified V2 probability vectors.
- `/match` renders only certified markets; fixture IDs must be unique and report is limited to 25 fixtures.
- Legacy `status`, `probabilities`, `expected_goals` and `value_bet_screen` fields are ignored.
- Value commands return a locked verdict; uncertified expected-goals/odds diagnostics are not exposed.
- Scheduled Telegram formatter marks value betting locked.
- Delivery adapter verifies the full bundle and publication authorization before delivery.
- Durable at-most-once claim and uncertain-outcome reconciliation structures exist; reconciliation writes require authenticated actor/reviewer callbacks, with operator and reviewer distinct for confirmed non-delivery.

These are software and adapter controls. Real Telegram delivery remains disabled/unaccepted. Legacy send/recovery workflow paths remain guarded off.

## 8. Database, migrations and staging

Neon staging/rehearsal infrastructure is used for isolated validation. Recorded branch names include:
- operational staging parent: `br-silent-violet-bc5de88s` (database `veltrix_football_staging`);
- migration rehearsal child: `br-red-grass-bclcmtk1`.

A later audit recorded migrations 0001–0011 on both the operational staging target and rehearsal child; always re-verify exact branch/database identity and migration table before any operation. Never infer that a rehearsal migration proves production or another branch state.

Recorded operational staging counts at one read-only checkpoint: 2,496 fixtures, 4,509 source observations, 72 provider responses, 25 paper-ledger events and zero odds quote observations. A later capture/readback described 5,180 source observations and 86 provider responses after additional 5Dollar collection. Treat these as dated snapshots, not live counts.

Built database-related components include schema/migration chain, odds quote observation schema, delivery claim/reconciliation schema, read-only Telegram reconciliation inspector, schema-mode writer acceptance and PostgreSQL 16/18 integration/acceptance tests. No production migrations/writes are authorised by this register.

## 9. Workflow and operational controls

Existing workflows cover foundation tests, PostgreSQL acceptance/integration, Phase 2 historical data qualification, OpenFootball/FootballData archive capture, 5Dollar opening-odds capture, 5Dollar shadow capture, shadow settlement, Phase 5 regression, historical model audit, certification evidence integrity and related artifact verification.

Safety controls include:
- manual-only bounded data capture;
- quota and request-budget guards;
- no automatic retries where explicitly prohibited;
- exact staging database/role allowlists;
- no production writes from archive collectors;
- fail-closed publication and delivery;
- legacy prediction, dashboard snapshot, historical reconstruction, paper recovery and Telegram recovery workflows deliberately paused/guarded;
- GOAL/Striker probes held until credit reset;
- no cron/schedule activation.

Workflow presence does not prove dispatchability, a successful run or production acceptance. Some workflows exist only on the integration branch; GitHub workflow dispatch requires default-branch visibility. Do not merge PR #120 just to expose a workflow. Do not re-enable any paused workflow merely because a test or manual dispatch becomes available.

## 10. Rights and source-use register

The current project basis is non-commercial/personal-use where the recorded source approval permits it. No monetisation. Raw redistribution is prohibited unless an explicit source licence independently permits it. Attribution and provenance must be retained.

Important records:
- `docs/legal/veltrix-all-source-noncommercial-authorization-2026-11-15.md`
- `docs/legal/openplay-whoscored-opta-authorization-2026-11-15.md`
- `docs/legal/openfootball-cc0-scope-review-2026-11-15.md`
- `docs/legal/football-data-cc0-supplemental-rights-review-2026-11-15.md`
- `docs/legal/5dollar-terms-review-2026-11-12.md`
- `docs/VELTRIX_V2_STAGE2_NONCOMMERCIAL_ODDS_ACQUISITION_2026-11-15.md`
- `docs/VELTRIX_V2_5DOLLAR_HISTORICAL_ODDS_PIT_SOURCE_REVIEW_2026-11-15.md`

An approval is source-, purpose-, scope- and time-specific. It does not prove PIT eligibility, provider account entitlement, or permission for unrelated uses.

## 11. Historical/legacy components intentionally excluded

VELTRIX 2.0 is not to reuse the previous prediction models, global priors, fallback probabilities, legacy feature engineering, calibration or prediction decision rules. Valuable historical data, website/API/Telegram infrastructure and credentials are preserved where appropriate; legacy prediction execution is not the V2 model.

Legacy daily predictions, dashboard snapshot publishing, legacy Telegram recovery/sender, paper-tracking recovery, historical reconstruction/backtests and daily-report watchdog workflows have been paused or guarded off to prevent accidental publication or reactivation. Their source/history may remain for audit, but their outputs are not V2 evidence and must not silently feed V2.

Historical PR branches and commit histories are retained for audit/recovery. The consolidated PR #120 is the intended integration path; do not merge superseded phase PRs back into it without proving a specific missing capability.

## 12. Current known completion matrix

| Component | Classification | Evidence / next action |
|---|---|---|
| OpenPlay rights + pinned raw staging | VERIFIED within recorded non-commercial scope | Preserve rights restrictions; no rebuild |
| OpenPlay feature sidecar | VERIFIED as staging sidecar | Preserve hashes; not a trained/PIT model input |
| OpenPlay identity crosswalk | PARTIAL | 89 team + 5 competition mappings; unresolved rows quarantined |
| OpenFootball collector/verifier | IMPLEMENTED / ARTIFACT RECONCILIATION REQUIRED | Inspect existing workflow artifact and independently verify; no rebuild |
| FootballData collector/verifier | IMPLEMENTED / ARTIFACT RECONCILIATION REQUIRED | Inspect existing workflow artifact and independently verify; no rebuild |
| Archive PIT admission | BLOCKED | No independent historical publication-time proof |
| 5Dollar Community qualification | QUALIFIED — READ-ONLY / NON-PIT | Workflow #43726672957: 59 tests passed; 2,505/2,505 fixture/result labels qualified across seven competitions; 28/40 requests; no side effects. Report SHA-256 `3bf4d797df92c293af6f346e296d3d76f7e7d9ec8988320d3992da1b5f6c668a`. Explicitly not PIT-certifiable and not pre-match feature evidence. |
| 5Dollar opening-odds code | VERIFIED code correction/test at recorded checkpoint | Preserve; verify exact current-head CI |
| 5Dollar opening-odds quote capture | IMPLEMENTED / NOT RUN | 763 candidate audit but zero quotes at that audit; bounded capture outstanding |
| 5Dollar shadow capture | EXECUTED, NON-PIT | 671 rows observed; all non-PIT; duplicate protection worked |
| Shadow ledger | IMPLEMENTED / PARTIAL | 25 shadow events, zero settlements in latest recorded count |
| Settlement runner | IMPLEMENTED / WAITING FOR ELIGIBLE TARGETS | Manual-only; verify real settlement and post-commit evidence |
| Historical odds entitlement | BLOCKED / NOT VERIFIED | No paid request before entitlement/quota/cost evidence |
| Model foundations | IMPLEMENTED / NOT CERTIFIED | Require eligible PIT and prospective evaluation evidence |
| Evaluation/certification verifier | IMPLEMENTED / NO MARKET CERTIFIED | Thresholds not met; no valid real certificate |
| Portable report bundle | IMPLEMENTED / NOT RELEASE-ACCEPTED | Need signed manifest, trusted runtime wiring and real artifact |
| Website/API V2 | IMPLEMENTED / FAIL-CLOSED | Trusted production verifier/config and certified bundle absent |
| Telegram V2 adapters/commands | IMPLEMENTED / NOT LIVE-ACCEPTED | Real workflow/destination/delivery verification absent; sends remain disabled |
| Cross-surface production parity | ADAPTER TESTED / LIVE NOT VERIFIED | Production scheduled workflow and Telegram runner not accepted |
| 06:00 WAT schedule | DISABLED | User previously stopped schedule; no reactivation |
| Production deployment/publication | DISABLED | No-go until release gates pass |
| Value betting | LOCKED | Separate certification and evidence requirements remain unmet |

## 13. Fixed remaining work — close existing work, do not expand scope

The Stage 2 master ledger remains the operational queue. Preserve this order:

1. Reconcile 5Dollar Community probe rights contract/tests against the current non-commercial approval and confirm the existing Community secret reference.
2. Run the existing Community qualification in a bounded, read-only manner once safely dispatchable.
3. Inspect existing OpenFootball and FootballData workflow artifacts and run their independent verifiers.
4. Resolve any default-branch dispatch constraint without merging PR #120 merely to expose workflows.
5. Run bounded 5Dollar opening-odds capture (maximum 25 fixture requests per run, no retries) only after safe dispatch and quota/rights guards are confirmed; reconcile persisted quotes.
6. Reconcile crosswalk and historical odds gates using existing evidence only.
7. Publish one definitive Stage 2 exit report.

Do not introduce new providers, architecture or unrelated features while closing Stage 2. After Stage 2, subsequent phases should append to this master register rather than create a competing source of truth.

## 14. Authoritative project documents and continuity

- [Stage 2 Master Execution Ledger](VELTRIX_V2_STAGE2_MASTER_EXECUTION_LEDGER.md) — fixed queue, current workstream classification, evidence log and session update template.
- [Stage 2 PIT Historical Data Acquisition](VELTRIX_V2_STAGE2_PIT_HISTORICAL_DATA_ACQUISITION_2026-11-15.md) — archive/provider scope, collector design, temporal caveats.
- [Release Readiness and Hard Blockers](VELTRIX_V2_RELEASE_READINESS_BLOCKERS_2026-11-14.md) — certification, report delivery, website/API/Telegram, staging and release blockers.
- [Stage 2 non-commercial odds acquisition](VELTRIX_V2_STAGE2_NONCOMMERCIAL_ODDS_ACQUISITION_2026-11-15.md) — odds-source scope and restrictions.
- [5Dollar historical odds PIT source review](VELTRIX_V2_5DOLLAR_HISTORICAL_ODDS_PIT_SOURCE_REVIEW_2026-11-15.md) — historical odds provenance/entitlement assessment.
- `docs/VELTRIX_V2_OPENPLAY_STAGING_FEATURE_PIPELINE_2026-11-15.md` — OpenPlay pipeline detail.
- `docs/legal/` — source-specific rights and licence evidence.

### Session-start protocol

At every continuation:
1. Read this master build register and the Stage 2 execution ledger.
2. Verify actual PR #120 head, branch state and exact-head checks; do not trust a stale SHA in a prior chat.
3. Inspect the relevant existing source/tests/workflow/artifact before changing anything.
4. Reuse existing components; no rebuild without a demonstrated defect.
5. Append evidence to the ledger and update this register when architecture/status materially changes.
6. Keep publication, value betting, Telegram, schedule and production deployment locked until their separate evidence gates pass.

**This register is a dated inventory, not a claim that VELTRIX FOOTBALL 2.0 is finished or production-ready.**


## Stage 2 Community qualification evidence — 2026-11-15
- Workflow [#43726672957](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957), job `132850009142`, branch `integration/v2-report-bundle-wiring-20261114`, exact commit `90d984091fdde520da4126842fb5301e5a8c0990`, completed successfully.
- Offline Phase 2 tests: `tests/test_phase2_data_foundation.py` and `tests/test_db_migrations.py`; **59 passed**.
- Community read-only historical fixture/result qualification: 2,505 fixtures, 2,505 importable, seven authorized competitions, 26 fixture pages, pagination complete, 28/40 requests, zero rejected/quarantined/duplicate rows.
- Report SHA-256 `3bf4d797df92c293af6f346e296d3d76f7e7d9ec8988320d3992da1b5f6c668a`; artifact [#14166776290](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43726672957/artifacts/14166776290), ZIP SHA-256 `29e908f311ede85de1a8a8e1f824da54520da32073d0a26cb843ef033384ddea`.
- Account quota observation: 300/hour, 20/minute; remaining 299 before and 272 after. This is a point-in-time observation, not a quota guarantee.
- Temporal qualification only: report explicitly says `point_in_time_certifiable=false`; conservative finished-status availability supports settled target labels only, not pre-match features or PIT historical model evaluation.
- Side effects reported: zero database writes, imports, prediction changes, deployments and Telegram messages. Non-commercial use only; attribution required; raw redistribution prohibited.


## OpenFootball and FootballData archive verification — 2026-11-15
- Workflow [#43727169566](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/43727169566) completed successfully on `c86163a75a8f80914de9eb2fd2bd0b2265fa3ed7`; 19 focused archive regression tests passed.
- OpenFootball: 49 immutable source snapshots; 5,182 observation versions; 375 requests; 49 archive proofs; 20/20 source paths succeeded; 5,182 unique fixtures; 82 not-yet-eligible and 2 rejected results; independent verifier `PASS`. Artifact #14166223794; ZIP SHA-256 `3dd4e89fa9c3d766e3e044efc317a88c6147b232dbb2831402cde26302e7de03`.
- FootballData: 3 immutable source snapshots; 619 observation versions; 6 requests; 539 unique fixtures; 14 audited normalizations; 1 not-yet-eligible and 0 rejected results; independent verifier `PASS`. Artifact #14166223800; ZIP SHA-256 `d8156a30d6b2f49032c157378385508fc8eefad931023ab2845255877c352acf`.
- Both packs are immutable CC0 archive evidence only. All observations are marked `point_in_time_certifiable=false`. OpenFootball commit timestamps are not independent first-public-availability evidence. FootballData's reported local match clock has unknown timezone, so `kickoff_at` remains null. Neither pack may be treated as a PIT pre-match feature set or used to satisfy chronological certification.
- Both artifacts record no database or production writes. No publication, Telegram send or schedule activation occurred.
