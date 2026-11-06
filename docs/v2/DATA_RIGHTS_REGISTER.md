# VELTRIX FOOTBALL V2 — Data Rights Register

**Last reviewed:** 2026-11-06  
**Purpose:** Prevent technical availability or a repository-level licence label from being mistaken for permission to train or operate a commercial football-prediction product.  
**Policy:** Unknown rights = not approved. Do not ingest a source into V2 training/calibration or expose derived commercial outputs until the intended use is supported by documented rights.

## Source register

| Source | Intended role | Evidence currently available | Status for V2 commercial model use |
|---|---|---|---|
| xgabora/Club-Football-Match-Data / Football-Data.co.uk | Historical results, odds and statistics | Dataset README identifies Football-Data.co.uk as the underlying match source. Football-Data.co.uk's current fair-use policy limits free data to private/personal and academic research and says it is not intended for commercial or AI/data-training projects; it says to assume no permission for such use. V1 validation metadata itself records `commercial_use_eligible=false`. | **BLOCKED** pending a suitable commercial subscription or written permission. |
| ClubElo (Elo fields embedded in historical CSV) | Historical team-strength fields | V1 validation metadata identifies ClubElo as the underlying Elo source. Separate terms/rights for the embedded fields have not been verified. | **BLOCKED / RIGHTS UNVERIFIED** pending source-specific clearance. |
| 5DollarFootballAPI | Primary fixtures/results and historical results/odds | Official Terms of Service (updated October 2026) explicitly permit use in commercial websites/apps/models/internal tools and caching; raw data may not be resold as a competing feed. Free and Community public-facing products must visibly attribute “Football data by 5DollarFootballAPI” with a link. Official docs state history depth is plan-dependent: Free 3 months, Community/Pro 12 months, Ultra back to 2014. The user's actual account plan and per-competition depth have not been verified. | **CONDITIONALLY APPROVED** for commercial model use under published terms, subject to account plan, rate/coverage limits and required attribution. |
| The Odds API | Supplementary fixtures/market prices and possible historical odds | Official Terms and Conditions (updated 31 August 2026) permit commercial use in websites/apps, derived values, indefinite storage and statistical/ML model training, while prohibiting raw standalone data-feed resale. Historical odds access is plan-dependent; the actual account plan/credits were not inspected. | **APPROVED UNDER PUBLISHED TERMS** for commercial app/model use, subject to plan access, quota and no raw-feed resale. |
| OpenLigaDB | Supplementary historical results | V1 cache metadata records ODbL-1.0 and attribution. The command-data branch contains ODbL attribution/notice files. V2 must review share-alike and database-right obligations for its exact use. | **CONDITIONAL**; preserve attribution and complete legal review before commercial redistribution or database combination. |
| InferSports | Optional fixture/odds enrichment | Disabled by default in V1; coverage and source rights were not established. | **DISABLED / UNVERIFIED**. |
| OddsPapi | Optional odds enrichment | Optional V1 integration exists; contractual rights, quote retention and commercial display/training scope were not verified. | **UNVERIFIED**; do not rely on it for V2 training. |
| API-Football / API-Sports | Legacy provider | User has explicitly directed that the suspended credential must not be accessed, tested, changed or used. | **EXCLUDED BY PROJECT DECISION**. |

## Provider-term evidence checked 2026-11-06

- 5DollarFootballAPI Terms of Service: https://5dollarfootballapi.com/terms
- 5DollarFootballAPI history-depth/endpoint documentation: https://5dollarfootballapi.com/docs and https://5dollarfootballapi.com/docs/league-fixtures
- 5DollarFootballAPI plan comparison: https://5dollarfootballapi.com/pricing
- The Odds API Terms and Conditions: https://the-odds-api.com/terms-and-conditions.html
- The Odds API plan/credit documentation: https://the-odds-api.com/

The published terms provide a viable commercial-use path through 5DollarFootballAPI and The Odds API. This does not prove that the user's current account plan has the required historical depth, league coverage, odds markets or quota. The actual 5Dollar plan is not known from the saved report, and no provider status/API call was made during this audit.

### Plan-dependent history and quota constraints

- 5DollarFootballAPI's published documentation lists historical depth as 3 months on Free, 12 months on Community and Pro, and back to 2014 on Ultra. Coverage also varies by competition and plan. The current account tier has not been verified; do not assume the V1 integration has the Ultra history window.
- The 5Dollar Free and Community plans require visible attribution in public-facing websites, apps, bots and published datasets. The V2 delivery layer must carry the attribution requirement from the rights decision into both the website and Telegram presentation when applicable.
- The Odds API's public pricing page lists 500 credits/month on Free; historical odds are offered on paid plans. Its terms permit commercial model training and indefinite storage but prohibit raw-feed resale. Current account tier and available historical endpoints remain unverified.
- Provider terms permission does not guarantee sufficient history, league coverage, timestamp density or request quota. These are separate access/quality gates.

## Mandatory gates

1. Record the exact legal entity/provider, product/plan, permitted fields, intended purpose, display/redistribution rights, derived-data rights, model-training rights, retention period, attribution requirements and termination/erasure terms.
2. Store documentary evidence of the applicable contract, licence or written permission without storing credentials in the evidence register.
3. Treat rights for fixtures, results, odds, team ratings, logos and other media as separate where applicable.
4. Do not assume that an open GitHub repository, MIT-licensed transformation code, public URL, free API tier or attribution notice grants rights to the underlying data.
5. If permission is absent or ambiguous, mark the source unavailable for the affected use and withhold any dependent model/market rather than silently substituting an unlicensed source.
6. Recheck source terms when the provider changes plan, endpoint, data fields or terms.

## Verified rights blocker: Football-Data.co.uk-derived history

The V1 dataset has 238,854 normalized rows, 38 competitions, and a SHA-256 recorded in the V1 historical audit. The dataset repository README reports 238,858 records and identifies Football-Data.co.uk as the match-results source. The V1 model-validation snapshot records the underlying source policy as personal/academic only and marks commercial use ineligible.

The current official policy page states that free downloads are intended for private personal betting and/or academic interest and research, not commercial or AI/data-training projects, and says users should assume no permission is granted for such use. The project therefore treats this source as excluded from V2 commercial training pending appropriate commercial rights. The 4-row difference between the published upstream count and the stored V1 normalized count must also be reconciled against a pinned source snapshot.

## Evidence links

- Football-Data.co.uk fair data usage policy: https://football-data.co.uk/contact.php
- xgabora dataset README/provenance: https://github.com/xgabora/Club-Football-Match-Data/blob/main/README.md
- 5DollarFootballAPI terms: https://5dollarfootballapi.com/terms
- The Odds API terms: https://the-odds-api.com/terms-and-conditions.html
