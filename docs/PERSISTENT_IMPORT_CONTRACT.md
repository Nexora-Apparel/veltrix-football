# Persistent Import Contract

This contract governs the first historical import into the dedicated VELTRIX Football database. It does not authorize an import by itself.

## 1. Import boundary

- The source is the verified 5DollarFootballAPI account and only the date range/competitions explicitly included in its confirmed entitlement.
- Import windows are half-open UTC intervals: `[window_start, window_end)`. Convert provider-local dates to UTC using the provider's documented timezone semantics; do not assume kickoff timestamps are local.
- Do not request dates outside the entitlement's history horizon.
- Do not import live, scheduled, postponed, cancelled, abandoned or unknown fixtures as completed results.
- Only provider records explicitly marked finished/final and containing valid non-negative integer scores may populate `fixture_results`.
- The import must have a dry-run stage that reports source counts, unique fixture IDs, date range, competition coverage, unresolved team identities and duplicates before writes.

## 2. Provenance

Every imported fixture must retain:
- canonical provider name;
- provider fixture ID;
- provider competition and team IDs;
- original kickoff timestamp and normalized UTC timestamp;
- provider status and retrieval timestamp;
- SHA-256 of the exact canonicalized source payload;
- endpoint/observation reference where available.

Raw observations are append-only and unique on provider, endpoint, entity type, provider entity ID and payload hash. Unknown legacy source attribution must remain explicitly unknown; it must not be backfilled by inference.

## 3. Identity and deduplication

- Canonical fixture identity is `(provider, provider_fixture_id)`.
- Canonical team identity is `(provider, provider_team_id)`.
- Never deduplicate solely on names, scoreline, date or competition label.
- A secondary cross-provider candidate match may be created for review using competition, normalized teams and kickoff proximity, but ambiguous matches are quarantined and never auto-merged.
- A repeated import of the same source fixture updates no canonical identity and creates no duplicate fixture or result row.
- Conflicting final scores/statuses are preserved as source observations and flagged for reconciliation; do not overwrite an accepted result silently.

## 4. Resumability

- Create one `import_runs` row per intentional import execution, recording provider, import type and fixed overall boundaries.
- Divide the boundary into deterministic windows. Persist one `import_checkpoints` row per run/window.
- A window is complete only after its source records and canonical rows commit successfully in the same transaction and its checkpoint is marked completed.
- Failed windows remain retryable. Retrying a completed window must be a no-op for canonical fixture/result rows.
- A run may resume only with the same provider, import type, boundary and importer version. Changed boundaries require a new run.
- Store cursor/page tokens where the provider supports them; otherwise use deterministic date windows and provider IDs.

## 5. Reconciliation before and after import

Before import:
- verify migration checksums and schema acceptance;
- record the manifest hash and provider entitlement snapshot;
- calculate expected window count and source request budget;
- confirm remaining quota is sufficient for the planned operation.

After each window:
- reconcile fetched records = inserted + already-present + quarantined + rejected;
- verify no duplicate canonical provider fixture IDs;
- verify every result references one fixture and only finished fixtures have results;
- verify checkpoints and counts commit atomically.

After the complete import:
- compare source totals, canonical fixture totals, result totals and quarantine totals;
- produce a machine-readable audit with all exclusions and gaps;
- do not proceed to model rebuild until the historical coverage audit is accepted.

## 6. Hard stops

Stop without importing when:
- the dedicated database target is not independently verified;
- the account entitlement or country pack is unverified;
- source timestamps/status semantics are unclear;
- payload provenance cannot be retained;
- the provider quota budget cannot be bounded;
- fixture/team identity collisions cannot be resolved safely.
