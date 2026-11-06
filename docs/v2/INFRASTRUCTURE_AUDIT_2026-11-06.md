# VELTRIX FOOTBALL 2.0 — Infrastructure Audit (2026-11-06)

This audit used read-only metadata and schema inspection. No Neon data, production environment variables, Vercel deployments, GitHub production branches or provider credentials were modified.

## GitHub

- Repository: `Nexora-Apparel/veltrix-football`
- Repository ID: `1430818677`
- Default branch: `main`
- Existing report branch: `command-data`
- New isolated V2 branch: `v2/foundation`
- Repository permissions: admin/maintain/push available to the connected GitHub identity.

The root README confirms the intended provider strategy and documents the historical dataset import, production daily pipeline, Telegram delivery, market validation and value-bet release gates.

## Vercel

A project named `veltrix-football-commands` was found:
- Project ID: `prj_k2AFGi4UB5EoC6sLSawChmhAkrpm`
- Team ID: `team_Lj9bVie6YVKgrQTBNNwj1ieu`
- Framework: Python
- Domains: `veltrix-football-commands.vercel.app`, `veltrix-football-commands-nexora-apparel.vercel.app`, `veltrix-football-commands-git-main-nexora-apparel.vercel.app`
- At inspection time, project metadata reported `live: false`; its latest deployment was in `BUILDING` state. This must be rechecked before treating it as the active production website.

Production environment-variable names visible without decrypting values:
- `API_FOOTBALL_KEY`
- `APIFOOTBALL_API_KEY`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_BOT_TOKEN`

The Vercel production environment listing did not show `FIVEDOLLARFOOTBALL_API_KEY`, `THE_ODDS_API_KEY` or `ODDSPAPI_API_KEY`. Repository documentation says provider keys are configured as GitHub Actions secrets. Do not copy secrets into Vercel or V2 until the actual runtime/deployment boundary is confirmed. Do not read/decrypt secret values as part of this audit.

## Neon

Two Neon projects were visible to the connected Neon account. Neither can currently be identified as the VELTRIX FOOTBALL database:

### Project `wandering-tree-79173263` (`neon-camel-mirror`)

- Default branch: `main` (`br-winter-rain-b7e0nn37`)
- Database objects in `public`: `gold_scalper_history`, `gold_scalper_outcomes`, `gold_scalper_state`.
- This is a Gold Scalper database, not the football database. Do not use it for V2.

### Project `old-rice-08119663` (`neon-cyclamen-house`)

- Default branch: `main` (`br-hidden-mouse-awzrca75`)
- Schema inspection showed Neon Auth and a broad `public` schema containing Nexora/Cardinal, content, ads, automation and publishing tables.
- No football-specific fixture, provider, forecast, odds or paper-tracking tables appeared in the inspected schema.
- This is not established as the football database. Do not use it for V2.

A number of preview/archived branches exist under these projects. They were not modified.

## Consequence

The current Neon account view does not establish a safe existing VELTRIX FOOTBALL database target. V2 must not attach to either discovered Neon project. The football app may be using repository artifacts, GitHub Actions artifacts, flat files, a different database account/project, or another persistence layer; this remains to be traced from the actual application and workflow configuration.

## Required next infrastructure work

1. Inspect repository workflows and application configuration to identify the actual production data store and report publication path.
2. Inspect GitHub Actions secret *names only* and environment protections; never print secret values.
3. Confirm which Vercel deployment is serving the website and which Git branch it builds from.
4. Verify report artifacts and `command-data` snapshots before designing an import.
5. Locate or establish a dedicated V2 Neon project/branch only after the legacy data-store inventory is complete.
6. Keep both discovered Neon projects and all their branches untouched.

## Current V2 implementation on `v2/foundation`

- `docs/v2/ARCHITECTURE.md`
- `docs/v2/LEGACY_MIGRATION_INVENTORY.md`
- `veltrix_v2/domain/contracts.py`
- `veltrix_v2/domain/eligibility.py`
- `tests/v2/test_eligibility.py`
- `.github/workflows/v2-ci.yml`

The V2 CI workflow runs the isolated domain tests on pushes to V2 branches and pull requests. Its first hosted run has not yet been confirmed in this audit.
