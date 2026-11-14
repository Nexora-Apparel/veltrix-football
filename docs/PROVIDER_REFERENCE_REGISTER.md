# Veltrix Football — Provider Reference Register

This register captures the exact provider references found in the earlier project discussion. A URL in this file is a research starting point, not proof of successful access, free-tier availability, or production suitability.

## Candidate sources from the multi-source plan

### 1. 5DollarFootballAPI
- Website: https://5dollarfootballapi.com/
- Python SDK repository: https://github.com/5dollarfootball-api/football-api-python-sdk
- Intended evaluation: fixtures, results, bookmaker odds and available match statistics.
- **Status (2026-10-28): LIVE AUTH + FIXTURE + ODDS ENDPOINTS VERIFIED.** GitHub Actions authenticated successfully and retrieved today's fixtures. The odds endpoint returned `1x2`, `btts`, `goal_line`, and `goal_line_fixed` market keys, but the latest live report matched no usable 5Dollar prices; treat 5Dollar as the fixture/results source until price coverage is confirmed.
- Integrated as the primary fixture/results source in `app/provider_adapters.py`; historical refresh is bounded and records failed dates separately so successful dates are preserved.
- Continue monitoring free-tier coverage, request quotas, and historical gaps. The live check verifies endpoint/schema access, not complete coverage of every competition.

### 2. InferSports
- OpenAPI specification referenced in the earlier discussion: https://github.com/infersports-dev/infersports/blob/main/openapi.yaml
- Intended evaluation: secondary odds and market information.
- **Status (2026-10-28): KEYLESS EVENT CONNECTIVITY VERIFIED; MARKET COVERAGE NOT CONFIRMED.** The keyless REST endpoint returned 200 same-day events, but three bounded odds requests returned no current quotes. A read-only adapter is implemented behind `VELTRIX_ENABLE_INFERSports=false`; do not enable it until a real quote-bearing fixture is verified. Current API schema supports 1X2 and totals, not BTTS.

### 3. The Odds API
- Website: https://the-odds-api.com/
- Additional listing referenced in the earlier discussion: https://rapidapi.com/theoddsapi/api/live-sports-odds
- Intended evaluation: supplemental bookmaker odds and market coverage.
- **Status (2026-10-28): LIVE AUTH + SOCCER MARKETS VERIFIED.** Direct API access accepted the configured key and listed 50 active soccer sports. A bounded live probe returned `h2h`, `totals`, and `btts` market keys; the event-specific BTTS endpoint returned prices. The probe consumed three odds credits, leaving 497 at that time.
- Integrated as a quota-bounded supplemental source; the daily report requests only supported competitions represented in the report, and caps event-specific BTTS requests at three.
- The RapidAPI listing is a distinct product/configuration and is not used by this integration.

### 4. Open Matchday
- GitHub repository referenced in the earlier discussion: https://github.com/oladeeayo/open-matchday
- Intended evaluation: supplementary historical fixtures, results and match statistics.
- **Status: RESEARCH-ONLY / NOT INGESTED.** The current README describes daily CSV data for 2026/27 and limits use to non-commercial purposes. Do not add it to production until licensing is confirmed compatible and historical coverage is shown to fill a real gap.

## Separate provider previously investigated: OddsPapi

- RapidAPI documentation/listing referenced earlier: https://rapidapi.com/odds-papi-odds-papi-default/api/odds-api1
- Existing repository integration: `app/oddspapi_odds.py` and `scripts/enrich_oddspapi_odds.py`.
- Repository README describes it as optional odds enrichment using the GitHub Actions secret `ODDSPAPI_API_KEY`, attached after the primary report and matched by exact home/away team names.
- This is distinct from The Odds API and from API-Football/API-Sports. Do not conflate the provider names, keys or API endpoints.
- Existing repository adapter is retained and included as optional post-report enrichment. Its status is separate from The Odds API; confirm fresh live coverage in its own workflow before treating it as healthy.

## Suspended provider — do not use as active dependency

- API-Football / API-Sports v3 was reported by the project owner as suspended.
- `API_FOOTBALL_KEY` must not be required for builds, scheduled reports, history refreshes or production data fetching while suspended.
- Keep historical records and useful code for audit purposes, but disable active calls and ensure failure cannot block the new provider path.

## Integration checklist

For each candidate, record:
1. Exact official product and documentation URL.
2. Credential variable name (never record the credential value).
3. Base URL and API version.
4. Authentication test result and timestamp.
5. Fixtures/results/history/odds capabilities tested separately.
6. Free-tier quota and observed request consumption.
7. Competition and bookmaker coverage observed in responses.
8. Data freshness and market timestamp behavior.
9. Fixture matching and normalization tests.
10. Go/no-go decision with evidence.

Do not put API keys or tokens in this document, source control, logs, screenshots or Telegram messages.

---

# VELTRIX FOOTBALL 2.0 — Consolidated provider register (2026-11-14)

This section is the current V2 register. The 2026-10-28 snapshots above are retained as historical records; where their plan, coverage or status differs from this section, this V2 register supersedes them. This is a reconciliation of providers already researched in the project, not a new discovery exercise.

| Provider | V2 role | Current qualification / rights state | Operational decision |
|---|---|---|---|
| **5DollarFootballAPI** | Primary fixtures and settled results; selected match statistics where fields are actually returned | Community entitlement last observed 2026-11-12: 7 competitions, 300 requests/hour, 20/minute, 299 remaining at observation time. Commercial model/app use, cache and display allowed. Public Community products require linked attribution. Raw feed redistribution prohibited. No explicit BENCHMARKING permission in the stored approval row. | **Qualified, scoped primary.** Use for fixtures/results and approved statistics. Do not use its odds as the bookmaker certification benchmark without explicit benchmarking rights. Attribute on website and Telegram. No new API call was made in this audit. |
| **The Odds API** | Supplemental prospective bookmaker prices and de-vigged benchmark | Official Terms last updated 2026-08-31 permit commercial UI display, derived values, model training and indefinite storage; prohibit raw-feed resale/redistribution; attribution not required. Account-specific accepted Terms version, current monthly quota and a V2 rights approval record are not present in Neon. Last historical probe on 2026-11-12 recorded 295 credits remaining after 205 used; this is stale, not a current balance. | **Selected but locked.** No requests until account acceptance, current quota/budget and scoped rights evidence are recorded. Historical price endpoint is not assumed entitled. |
| **OpenFootball** | Supplementary historical fixtures/results and reconciliation | Public CC0 archive; adapter and reconciliation exist. Nigeria 2025/26 archive contained 379 accepted ordinary results; awarded result excluded. Date-only historical data cannot establish original publication time. EPL comparison with 5Dollar showed only 45% score coverage and six one-day date conflicts. | **Archive/reconciliation only.** Read-only; not current-results primary and not PIT-certified training data. |
| **OpenPlay** | Historical player-match statistics, shots, xG, lineups and team statistics | Technical qualification passed on a pinned dataset (26,547 matches; 669,404 shots; static through 2025/26). Upstream WhoScored/Opta/Stats Perform provenance and commercial training/display rights remain unresolved. | **Quarantined.** No production ingestion, model training or public display until upstream rights are confirmed. |
| **PitchAPI** | Candidate live player/team statistics, xG/xGOT, lineups/events, shots and PPDA | Documentation reviewed; no account/key or endpoint request made. Storage, model-training, retention and commercial display rights not established. | **Optional candidate, disabled.** No calls or model dependency. |
| **Wyscout public event data** | Historical shot/event research for a VELTRIX-owned xG model | Public research dataset reviewed under CC BY 4.0 with attribution/change-notice obligations. No production import. | **Research-only approved.** Keep attribution and licence evidence with any model artifact; no PIT or production certification claim. |
| **StatsBomb Open Data** | Selected-match historical event/lineup research | Selected competitions/seasons only. README attribution/logo conditions apply; research scope does not establish blanket commercial VELTRIX rights. | **Research-only / gated.** No production training or public display without separate rights approval. |
| **football-data.org** | Conditional fixtures/results/tables/lineups fallback | Free-tier and competition limits apply. Exact VELTRIX rights, competition access and point-in-time revision history are not qualified. | **Conditional candidate, disabled.** No ingestion until scope and rights qualify. |
| **OpenLigaDB** | Offline parser and potential supplementary fixtures/results | Parser contract exists; no endpoint calls or data import. ODbL share-alike/attribution obligations and operator approval for automated public-product collection remain unresolved. lastUpdateDateTime is not proof of first publication or full revision history. | **Parser-only.** No live dispatch or model training until operator/rights review. |
| **InferSports** | Limited secondary odds/event discovery candidate | Prior bounded probe returned 63 same-day events and 1X2/totals; no verified archive, quote-created timestamps or BTTS coverage. Rights and retention terms remain unclear. | **Quarantined.** No storage/training/public display until rights are explicit. |
| **GOAL API** | Dormant candidate | Key previously confirmed active; latest requests blocked by Cloudflare/browser-signature restriction and credits are exhausted. This is not evidence of an invalid key. Underlying data rights remain unresolved. | **Hard blocked.** No requests until credits reset and access/rights are separately reviewed. |
| **StrikerAPI** | Dormant candidate | Latest account response was HTTP 402 / insufficient credits. No paid top-up authorized. | **Hard blocked.** No requests or credit purchase. |
| **FPL API** | None | Previously inspected snapshot; automated extraction/commercial-use restrictions unresolved. | **Quarantined/excluded.** Do not reintroduce into model features or persistent data. |
| **OddsPapi** | None | Existing adapter retained for audit; terms do not expressly grant model-training, retention and commercial-display rights; successful quote coverage not established. | **Excluded.** No model or publication dependency. |
| **Football API (footballapi.org)** | None | Terms restrict using data to build a competing product, which conflicts with VELTRIX's core product. | **Excluded.** No key or integration. |
| **Open Matchday** | None | Current README describes non-commercial use. | **Excluded from commercial V2.** |
| **Sportmonks / Goalserve** | Paid alternatives only | Documentation/pricing reviewed; no subscription, rights scope or exact competition coverage approved. | **Not integrated.** No purchase. |
| **API-Football / API-Sports** | None while suspended | Key was suspended twice per project owner. | **Do not rely on API_FOOTBALL_KEY.** No calls in V2. |

## Current rights/entitlement gate evidence

### 5DollarFootballAPI

The actual staging source_approvals row is scoped to Community use and includes collection, caching, model training, public display, internal analytics and attribution. It records commercial use allowed, attribution required and raw redistribution prohibited. It does not include an explicit BENCHMARKING use. The actual provider_entitlement_observations row records the Community plan, seven competition IDs, 300/hour, 20/minute and 299 remaining at its 2026-11-12 observation time. Do not present that old remaining-credit value as a live balance.

Official references:
- https://5dollarfootballapi.com/docs
- https://5dollarfootballapi.com/pricing
- https://5dollarfootballapi.com/terms

### The Odds API

The current official terms support VELTRIX's intended use of market quotes for statistical/ML training, derived probabilities and display inside VELTRIX, provided the raw odds feed is not resold or redistributed as a standalone product. The public terms do not prove that the user's account accepted the relevant version or establish the current account quota. The Neon staging source_approvals and entitlement tables contain no The Odds API approval/entitlement row. The Phase 5 quota/credit snapshot tables are not yet applied to staging, so no current quota record exists there.

Official references:
- https://the-odds-api.com/terms-and-conditions.html
- https://the-odds-api.com/liveapi/guides/v4/

### Credit-blocked providers

GOAL API and StrikerAPI remain blocked. The workflows are disabled in the reconciled V2 branch. No provider request, top-up, quota reset probe or credential change was performed during this audit.

## Non-negotiable provider handling

1. Preserve this register and the individual qualification documents; do not restart discovery.
2. A provider outage, empty market, quota exhaustion or rights gap must not invoke legacy data, a generic probability prior or fabricated feature values.
3. Record source publication, provider quote time, VELTRIX retrieval time and local recording time separately.
4. Do not treat fetched_at, retrieved_at, lastUpdated or lastUpdateDateTime as a source publication timestamp unless that provider explicitly defines it as such.
5. Rights are checked per provider, competition, data domain, purpose and time of use. API connectivity does not imply permission to train or publish.
6. No new provider calls, database writes, Telegram sends, schedule activation or deployments were part of this register reconciliation.


### 5.3 Timestamp semantics for The Odds API

The Odds API V4 documentation defines the market-level last_update as the time The Odds API system last saw odds for that market from the bookmaker. This is a provider-observed timestamp, not the bookmaker's original quote-creation timestamp. V2 evidence must therefore label it PROVIDER_OBSERVED_AT (or an equivalent explicit provider-observation basis), never SOURCE_CREATED_AT. The bookmaker quote must still be observed before the prediction cutoff and kickoff. A VELTRIX retrieval timestamp is recorded separately and cannot replace the provider-observed time.

The 2026-11-12 The Odds API probe occurred after the published Terms update of 2026-08-31. The Terms state that continued use after a change constitutes acceptance. If that probe used the same active account/key, it is evidence of acceptance under the public Terms; the repository still lacks an account-specific acceptance receipt. The current quota/budget remains unverified because the last credit snapshot is stale.

