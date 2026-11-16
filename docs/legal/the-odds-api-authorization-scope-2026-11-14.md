# VELTRIX 2.0 — The Odds API authorization and scope record

**Review date:** 2026-11-14  
**Provider:** The Odds API  
**API source:** `odds_api_v4`  
**Terms version:** 2026-08-31 (official Terms last updated 31 August 2026)

## Project-owner authorization

On 2026-11-14, the VELTRIX project owner explicitly confirmed that the project has full authorization to use the existing The Odds API account for VELTRIX FOOTBALL 2.0. This record captures that owner confirmation and the currently published provider Terms. It does not claim a separate provider-issued letter or change the provider's Terms.

## Provider Terms review

Official Terms: https://the-odds-api.com/terms-and-conditions.html

The official Terms last updated 31 August 2026 permit:
- storing and retaining API data indefinitely;
- displaying odds and derived information in a commercial user-facing website, dashboard or mobile application, provided the data is not sold or redistributed as the primary product;
- using data in research, analytical dashboards and derived calculations;
- training statistical and machine-learning models.

The Terms prohibit reselling, repackaging or redistributing raw API data as a standalone data product or competing feed. Attribution is not required, although it is appreciated.

## VELTRIX approved operational scope

The existing VELTRIX odds design uses the following five soccer competitions:

- `soccer_epl`
- `soccer_spain_la_liga`
- `soccer_germany_bundesliga`
- `soccer_italy_serie_a`
- `soccer_france_ligue_one`

The initial bounded capture scope is:
- Region: `uk`
- Markets: `h2h`, `totals`, and event-level `btts`
- Uses: COLLECTION, CACHE, STORAGE, MODEL_TRAINING, BENCHMARKING, and derived analytical/public display within VELTRIX
- Quote timestamps: provider market-level `last_update` only
- Raw response bytes: retained internally as immutable evidence; never exposed as a raw feed or bulk export
- Historical paid-odds endpoints: excluded from the initial prospective capture worker

The initial region and market set matches the existing VELTRIX provider adapter configuration. It is a bounded capture scope, not a claim that every bookmaker or every market is available.

## Account and quota boundary

Owner authorization and published Terms do not establish the current account plan or remaining credits. The first account verification must use the existing repository secret `THE_ODDS_API_KEY` and the no-credit `/v4/sports` discovery endpoint, preserving the response bytes, HTTP status, retrieval timestamp and documented quota headers.

No monthly allowance, remaining balance, hard cap or per-run budget is invented in this record. Odds endpoints that consume credits remain blocked until the account response and explicit hard caps are recorded in the immutable budget ledger. Every subsequent request must pass the account-specific Terms, scoped rights, quota and credit-reservation gates.

## Data integrity and release controls

- Store exact response bytes and SHA-256 before parsing.
- Preserve market-level provider timestamps separately from local retrieval and recording times.
- Quotes with missing, malformed, naive or post-cutoff timestamps remain ineligible.
- Resolve events through evidence-backed fixture crosswalks; never match by team names alone.
- Keep raw response data private; publish only permitted selected odds and derived analytics.
- No live bookmaker execution, betting action, scheduled report, Telegram broadcast or value-bet unlock is authorized by this record.

## Evidence references

- Official Terms: https://the-odds-api.com/terms-and-conditions.html (last updated 31 August 2026).
- Official v4 API documentation: https://the-odds-api.com/liveapi/guides/v4/
- VELTRIX provider capture design: `docs/VELTRIX_V2_PHASE4_ODDS_CAPTURE_ADAPTER_DESIGN_2026-11-13.md`.
- VELTRIX account activation gate: `docs/VELTRIX_V2_PHASE4_ACCOUNT_ACTIVATION_EVIDENCE_GATE_2026-11-13.md`.
- Project-owner authorization confirmation: VELTRIX FOOTBALL 2.0 conversation dated 2026-11-14.


## Additional provider documentation verification — 2026-11-14

The current official v4 documentation confirms that `GET /v4/sports/?all=true` returns in-season and out-of-season sport keys, does not count against usage quota, and returns `x-requests-used`, `x-requests-remaining`, and `x-requests-last` headers. The no-credit probe therefore uses this endpoint only; it does not call an odds or historical-odds endpoint.

The provider FAQ states that usage credits reset on the first of every month. The reset rule is recorded, but the exact account plan/allowance, reset timezone and account-specific billing evidence remain unverified until the live account probe and account dashboard evidence are captured. No credit budget or hard cap is activated by this documentation finding.

References:
- v4 API documentation: https://the-odds-api.com/liveapi/guides/v4/
- Official FAQ: https://the-odds-api.com/manage/faqs.html
- Official Terms: https://the-odds-api.com/terms-and-conditions.html (last updated 31 August 2026)
