# VELTRIX 2.0 — Staging evidence coverage baseline

Audit date: 2026-11-14
Environment: dedicated Neon staging branch only
Method: read-only SQL inspection; no inserts, updates, deletes, migrations or provider calls

## Executive result

The staging database contains 2,496 imported fixtures across seven 5DollarFootballAPI competitions. All 2,496 are currently non-certifiable for strict point-in-time model training. The result is not caused by GOAL API or StrikerAPI being unavailable: the imported historical snapshot itself lacks the required temporal evidence.

## Competition inventory

| Competition | Fixtures | Exact kickoff timestamp present | Linked source observation | Point-in-time certified |
|---|---:|---:|---:|---:|
| Brazil Serie A | 391 | 391 | 391 | 0 |
| Italy Serie A | 380 | 380 | 380 | 0 |
| France Ligue 1 | 284 | 284 | 284 | 0 |
| England Premier League | 370 | 370 | 370 | 0 |
| Spain La Liga | 381 | 381 | 381 | 0 |
| Brazil Serie B | 391 | 391 | 391 | 0 |
| Germany Bundesliga I | 299 | 299 | 299 | 0 |
| **Total** | **2,496** | **2,496** | **2,496** | **0** |

## Evidence gaps

| Evidence check | Observed count |
|---|---:|
| Source observations | 2,496 |
| Rows marked point-in-time certifiable | 0 |
| Rows with an availability timestamp field | 2,496 |
| Rows with a recorded-at timestamp | 0 |
| Rows with a source-publication timestamp | 0 |
| Rows linked to a rights approval ID | 2,496 |
| Provider raw responses | 28 |
| Capture manifests | 0 |
| Capture manifest events | 0 |
| Provider capture request records | 0 |

The availability timestamp field does not establish provider publication time or actual result-availability time. The earlier 5Dollar historical adapter used a conservative availability proxy; it must not be promoted to source publication or source availability evidence. A linked approval ID alone also does not establish that all rights scopes and use purposes pass at a particular evaluation time.

## Interpretation

- Exact kickoff timestamps exist for all 2,496 fixture rows.
- Every imported observation remains non-certifiable.
- No durable Phase 4/5 capture manifests or request-linkage rows have been written to staging yet.
- The historical rows can still support fixture reconciliation, exploratory summaries and non-certifying diagnostics where the applicable rights allow.
- They cannot be counted toward certified walk-forward training, calibration, prospective paper admission or public prediction eligibility.
- The current strict eligible-history coverage for these imported observations is therefore 0/2,496 (0%).

## Release consequence

Do not relax the temporal gate to make this inventory appear usable. The next coverage increase must come from new source evidence with exact publication/availability semantics, complete revision history, explicit rights approval evidence and immutable capture linkage. GOAL API and StrikerAPI remain dormant until their credit resets; this baseline was obtained without calling either provider.
