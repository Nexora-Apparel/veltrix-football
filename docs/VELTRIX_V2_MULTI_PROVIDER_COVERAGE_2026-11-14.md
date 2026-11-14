# VELTRIX 2.0 — Multi-provider coverage and dispatch policy

Date: 2026-11-14

## Purpose

The model pipeline requests data domains, not named vendors. This registry is policy metadata only: it makes no network calls, reads no secrets, spends no credits, and grants neither source rights nor point-in-time eligibility.

## Current provider assignments

| Provider | State | Permitted role |
|---|---|---|
| 5DollarFootballAPI | Active, limited | Primary live fixtures/results within free quota and accessible competitions |
| OpenFootball | Archive only | Supplementary historical scores; date-only imports are not point-in-time certifiable |
| StatsBomb Open Data | Research archive, gated | Selected historical matches include event data, lineups and shot-level xG; research-use/attribution review required |
| The Odds API | Optional, gated | Odds only after rights, allowance, remaining quota and explicit spend caps are verified |
| GOAL API | Suspended — credits exhausted | No calls, retries, scans or credit checks until reset and requalification |
| StrikerAPI | Suspended — credits exhausted | No calls, retries, scans or credit checks until next monthly reset and requalification |

## Domain ownership

- Fixtures: 5DollarFootballAPI. OpenFootball is a static archive, not a live fixture feed.
- Results: 5DollarFootballAPI and OpenFootball, subject to their distinct timestamp limitations.
- Team form and strength: calculate internally from eligible observations; do not ingest model outputs as ground truth.
- Rest days: derive only when exact timezone-aware kickoff timestamps exist.
- 1X2 and totals odds: optional The Odds API markets, gated by rights/quota/spend authorization and quote timestamps.
- BTTS odds: optional event-specific market, separately verified per event.
- xG and lineups: StatsBomb Open Data is a candidate for selected historical research matches only. It is not a live/current source, and its research-use and attribution terms must be reviewed before any use in the public/commercial product.
- Injuries and current player availability: no currently qualified source is declared. Keep unavailable fields missing until another provider is independently qualified.

## Evidence rules

1. Provider availability does not equal source-rights approval.
2. A retrieval timestamp does not prove when a result became available to the source.
3. OpenFootball date-only observations remain useful for reconciliation and exploratory coverage, not strict timestamped walk-forward training.
4. The 5Dollar historical parser's four-day availability proxy is not source publication or availability evidence.
5. Derived features inherit the temporal eligibility of their underlying observations.
6. Conflicting records require identity and payload reconciliation; never average contradictory scores.
7. Missing xG, lineups, injuries or player information stays missing. No zero-fill or synthetic replacement.
8. GOAL API and StrikerAPI are hard-blocked before transport construction while credits are exhausted.
9. The Odds API remains excluded from dispatch until separate rights, quota and spend gates pass.
10. StatsBomb Open Data is archive-only and research-gated; its published terms require source attribution and use of the StatsBomb logo when publishing analysis. No commercial rights are inferred.
10. The registry does not relax publication, prospective paper-ledger or value-bet certification gates.

## Next integration

Each new provider adapter must normalize source data into the immutable evidence-capture contract and pass raw-byte, timestamp, crosswalk, rights and revision-history checks. Only certified observations may enter point-in-time training or paper admission. This document does not claim xG/lineup/injury coverage or launch-ready model evidence.

## Coverage report interpretation

The registry distinguishes three separate questions: whether a provider has a field, whether it may be contacted now, and whether its returned observation is temporally eligible for a model. These are independent gates. A source may appear in the coverage report while remaining non-dispatchable (archive or optional provider), and a retrieved result may remain non-certifiable despite a successful response. The `providers_for` function reports declared source coverage; `dispatchable_providers_for` reports the narrower set permitted for live collection.
