# VELTRIX FOOTBALL 2.0 — Quota and Deployment Budget Policy

**Status:** Binding operational policy for V2 development and production.
**Primary objective:** Preserve daily provider/API quotas and deployment/build allowances while maintaining sufficient data freshness and validation quality.

## 1. Provider API request budget

- Never poll providers continuously or per fixture when a batch endpoint can cover the same request.
- Fetch a competition/date window in batches; normalize and persist the response once.
- Cache successful responses with provider-aware TTLs. Reuse cached fixtures, results, team metadata and odds until their freshness window expires.
- Use incremental synchronization with a persisted cursor/watermark. Request only new or changed records.
- Use conditional requests/ETags when supported.
- Apply exponential backoff with jitter for transient failures; respect Retry-After and provider rate-limit headers.
- Do not retry authentication, permission, plan-limit or invalid-request failures automatically.
- Set explicit per-provider daily request ceilings and a reserve. Stop noncritical enrichment before the hard ceiling.
- Reserve quota for the scheduled daily fixture/result run and essential recovery. Historical backfills and experiments must use a separate, explicitly budgeted allowance.
- Never run historical backfills from a deployment/build hook or normal daily report job.
- Odds collection must be scoped to relevant fixtures, markets, regions and bookmakers. Do not repeatedly refresh unchanged odds.
- Optional providers may enrich a record but must not cause duplicate primary ingestion or unbounded retries.
- Log request count, remaining quota, reset time, endpoint, cache hit/miss, response status and retry count without logging secrets.

## 2. Data freshness and graceful degradation

- Define freshness TTLs per data class and provider; do not assume one TTL fits fixtures, results, team metadata and odds.
- A cache hit is usable only when its source timestamp and identity remain valid for the intended purpose.
- If a provider quota is exhausted, use already verified cached data only within its approved freshness window.
- If required evidence is stale or unavailable, mark the relevant fixture/market withheld. Never fabricate data or probabilities to preserve report volume.
- Optional odds-provider failure must not trigger repeated calls to the primary fixtures provider.
- Provider health checks must be lightweight and must not call expensive endpoints on every page view.

## 3. GitHub Actions budget

- Run V2 tests only when V2 source, tests, workflow or dependency manifests change.
- Cancel superseded branch runs.
- Keep job timeouts bounded.
- Avoid matrix expansion until there is a demonstrated compatibility need.
- Do not schedule CI polling or recurring test workflows.
- Install only required test dependencies; avoid unnecessary package upgrades and repeated heavyweight installs.
- Use artifacts only for outputs that need to survive the run. Set short retention for temporary diagnostics.
- Do not trigger production report generation, provider backfills or Telegram delivery from CI.

## 4. Vercel deployment budget

- V2 development pushes may create preview deployments through the existing Git integration. Therefore, batch related commits and push at deliberate checkpoints rather than deploying after every tiny edit.
- Prefer one preview deployment per coherent milestone; do not force redeploys when an equivalent build already exists.
- Use preview builds for interface and integration checks only when necessary. Domain/unit tests should run in GitHub Actions without requiring a Vercel deployment.
- Do not run production deployments during architecture, data-audit or model-research stages.
- Configure and verify an affected-path/ignore-build rule for V2-only changes before relying on it. Do not change production project settings until the effect on the retained website is proven.
- Do not run repeated deployment status polling. Check once after a known deployment trigger, then only when a meaningful state transition or failure investigation is needed.
- Keep production deployment and V1 rollback target untouched until formal V2 release acceptance.

## 5. Historical data and model compute budget

- Inventory and checksum existing historical data before any backfill.
- Never re-download the complete historical dataset when a verified local/source copy exists.
- Use resumable, chunked backfills with checkpoints, deduplication and a strict per-run record/request budget.
- Separate data ingestion from model training. Training must consume versioned local/managed snapshots, not call live providers.
- Cache deterministic feature snapshots keyed by data cutoff, feature version and fixture/team identity.
- Run fast unit tests on each relevant change; run larger integration, walk-forward and bootstrap evaluations only at planned milestones.
- Do not repeatedly train every candidate model on every code edit. Use fixed evaluation datasets and experiment manifests.

## 6. Operational safeguards

Every scheduled ingestion/report run records:
- provider and endpoint;
- request count and quota remaining/reset where available;
- cache hits and misses;
- records fetched, changed, skipped and quarantined;
- retries and failure classifications;
- elapsed time and run ID.

Every deployment records:
- commit SHA and branch;
- reason for deployment;
- preview/production target;
- build result and duration;
- whether the deployment was reused or newly built.

Secrets are never printed, included in logs, or copied into documentation.

## 7. Initial conservative operating mode

Until actual provider plan limits and usage headers are verified:
- Keep automated polling disabled outside the essential scheduled ingestion/report window.
- Do not run full historical backfills.
- Do not run broad all-league/all-market odds scans.
- Do not run recurring deployment checks.
- Use read-only audits and cached repository data first.
- Treat unknown quota as scarce quota.

## 8. Release gate

Before enabling V2 scheduled ingestion, establish a measured budget for each provider: daily cap, observed cost per endpoint, reset time, required daily calls, contingency reserve, cache TTL and stop condition. The schedule must fit below the cap with headroom. If the provider does not expose usage, enforce a conservative local request ledger and ceiling.

**Non-negotiable:** No deployment, test, backfill, model experiment or monitoring loop may consume provider quota unless it has a defined purpose, bounded request budget and observable stop condition.
