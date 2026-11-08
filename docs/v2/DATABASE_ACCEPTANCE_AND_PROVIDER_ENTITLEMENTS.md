# V2 Database Acceptance and Provider Entitlements

Status date: 2026-11-08  
Branch: `v2/foundation`

## Database acceptance gate

`scripts/v2_database_acceptance.py` is a read-only acceptance command. It requires:
- `VELTRIX_V2_STORAGE_APPROVED=true`
- `VELTRIX_V2_EXPECTED_HOST` equal to the exact verified Neon hostname
- `VELTRIX_V2_DATABASE_URL` targeting the fixed `veltrix_football_v2` database on that hostname with TLS

It checks:
- Required V2 tables and critical columns.
- Required indexes and named constraints.
- Every expected migration version and exact SHA-256 checksum.
- No unexpected applied migration versions.
- The actual connected database name and read-only transaction state.

It does not apply migrations, mutate rows, print the DSN, or fall back to another database. Apply migrations only with `scripts/v2_apply_migrations.py` after independent target verification.

A PostgreSQL integration test applies the migration to the disposable CI database and asserts that the acceptance gate returns clean. The CI service is a local PostgreSQL 16 container named `veltrix_v2_test`; the test fixture is guarded against non-local hosts and any other database name.

## Current database inventory and blocker

The connected Neon organization is `Vercel: Nexora Apparel`, on the Free plan and marked `managed_by=vercel`.

The only visible projects at this checkpoint are:
- `neon-camel-mirror` (`wandering-tree-79173263`) — unrelated Gold Scalper project.
- `neon-cyclamen-house` (`old-rice-08119663`) — unrelated Nexora/CARDINAL project.

Neither is the V2 database. Do not connect, migrate, inspect data in, or repurpose either project for V2.

No dedicated `veltrix_football_v2` database, verified V2 connection string, or exact V2 Neon hostname is available. The Vercel `v2/foundation` Preview environment currently has no environment variables. The project's Production environment has no V2 database or 5DollarFootballAPI/The Odds API credential names; no values were decrypted. Therefore neither V2 storage nor provider access can be configured from the existing project environment at this checkpoint. The Neon organization is Vercel-managed; direct Neon project provisioning was rejected previously. Provision the V2 database through the Vercel Neon Marketplace integration on its Free plan. Until it exists, do not connect, migrate, run acceptance against another database, or import provider data.

## Provider entitlement verification — public baseline only

The following are public provider-published plan details, not verification of the user's account.

### 5DollarFootballAPI

Official pricing and docs currently describe:
- Free: 60 requests/hour (also 20/minute), top-five leagues, last three months of results and odds.
- Community Access: $0, 300 requests/hour (also 20/minute), top-five leagues plus one country pack, last 12 months of history.
- Pro: 130+ competitions and 12 months of history; paid.
- Ultra: 1,600+ competitions and history back to 2014; paid.
- Every key on an account shares its account quota.
- On $0 plans, public-facing website/app/bot output requires visible “Football data by 5DollarFootballAPI” attribution and a link.
- Raw feed resale/redistribution as a competing data feed is prohibited.

Sources:
- https://5dollarfootballapi.com/pricing
- https://5dollarfootballapi.com/docs

Implications:
- Community Access is the only plausible no-cost path to broader than top-five coverage, but it only adds one country pack and a 12-month history window.
- It does not establish that the user's account is on Community Access, which country pack is enabled, which exact competition IDs are covered, or whether required historical seasons are complete.
- No API request is authorized until the account dashboard and live quota evidence establish plan, country pack, data classes, history floor, remaining quota/reset, and endpoint permissions.
- If using a $0 plan for public Veltrix website/Telegram output, implement the required provider attribution before publication.

### The Odds API

Official terms allow storing data, displaying it in user-facing apps, calculating derived values and model training, while prohibiting raw-data redistribution as a standalone feed. Historical odds are available only on paid plans and historical requests have a higher quota cost (10 credits per region per market per event).

Sources:
- https://the-odds-api.com/terms-and-conditions.html
- https://the-odds-api.com/historical-odds-data/
- https://the-odds-api.com/liveapi/guides/v4/

Implications:
- Do not use The Odds API for historical odds ingestion under a no-paid-resources constraint unless the account already has valid paid entitlement.
- For any current-odds sample, first verify the account's actual plan, remaining credits and reset in its dashboard. Use response quota headers and reserve only a small, explicit request budget.
- No current or historical odds API calls were made during this verification.

## Actual account verification still required

Account-specific entitlement cannot be proven from public pricing pages. Verify inside the provider dashboards without sharing API keys:
1. 5DollarFootballAPI account plan and status.
2. Enabled country pack (if Community), exact competition IDs and competition coverage.
3. Available data classes/endpoints and history start per competition.
4. Current rate-limit headers, remaining quota, reset timestamp and account-wide shared usage.
5. Terms/attribution status for public website and Telegram display.
6. The Odds API subscription tier, credits remaining/reset and historical endpoint entitlement, if it is to be used.

Record evidence references and timestamps in a V2 provider-access profile. Never copy secret values into GitHub, documentation, logs or chat.

## Bounded ingestion gate

Once the database exists and account evidence is verified:
1. Start with one explicitly selected competition and a small date window.
2. Reserve a conservative request budget before transport; never exceed the account quota or the configured safety reserve.
3. Persist exact raw response bytes, SHA-256, provider/source IDs, fetched timestamp, source update timestamp, rights evidence and ingestion run ID.
4. Verify provider fixture IDs, source record counts, pagination completeness, idempotent replay and watermark advancement.
5. Reconcile team/competition identities; quarantine ambiguity; do not drop provider records.
6. Expand competition/date coverage only after source-to-canonical reconciliation and provenance checks pass.

No provider calls, imports or V2 database writes have occurred at this checkpoint.
