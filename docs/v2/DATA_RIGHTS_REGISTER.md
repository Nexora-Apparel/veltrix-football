# VELTRIX FOOTBALL V2 — Data Rights Register

**Last reviewed:** 2026-11-06  
**Purpose:** Prevent technical availability or a repository-level licence label from being mistaken for permission to train or operate a commercial football-prediction product.  
**Policy:** Unknown rights = not approved. Do not ingest a source into V2 training/calibration or expose derived commercial outputs until the intended use is supported by documented rights.

## Source register

| Source | Intended role | Evidence currently available | Status for V2 commercial model use |
|---|---|---|---|
| xgabora/Club-Football-Match-Data / Football-Data.co.uk | Historical results, odds and statistics | Dataset README identifies Football-Data.co.uk as the underlying match source. Football-Data.co.uk's current fair-use policy limits free data to private/personal and academic research and says it is not intended for commercial or AI/data-training projects; it says to assume no permission for such use. V1 validation metadata itself records `commercial_use_eligible=false`. | **BLOCKED** pending a suitable commercial subscription or written permission. |
| ClubElo (Elo fields embedded in historical CSV) | Historical team-strength fields | V1 validation metadata identifies ClubElo as the underlying Elo source. Separate terms/rights for the embedded fields have not been verified. | **BLOCKED / RIGHTS UNVERIFIED** pending source-specific clearance. |
| 5DollarFootballAPI | Primary fixtures/results and possible historical results/odds | V1 metadata records a commercial-with-attribution licence label for some cached rows; provider contract, scope, retention and model-training terms have not been independently reviewed in this audit. | **PENDING CONTRACT REVIEW**. Do not infer rights beyond the documented account terms. |
| The Odds API | Supplementary fixtures/market prices | Connected in V1 and used as reference price data. Current plan limits and permitted retention, display, derived use and training scope have not been verified in this audit. | **PENDING CONTRACT REVIEW**. Prefer live price reference use only after terms are checked; do not use for training without explicit permission. |
| OpenLigaDB | Supplementary historical results | V1 cache metadata records ODbL-1.0 and attribution. The command-data branch contains ODbL attribution/notice files. V2 must review share-alike and database-right obligations for its exact use. | **CONDITIONAL**; preserve attribution and complete legal review before commercial redistribution or database combination. |
| InferSports | Optional fixture/odds enrichment | Disabled by default in V1; coverage and source rights were not established. | **DISABLED / UNVERIFIED**. |
| OddsPapi | Optional odds enrichment | Optional V1 integration exists; contractual rights, quote retention and commercial display/training scope were not verified. | **UNVERIFIED**; do not rely on it for V2 training. |
| API-Football / API-Sports | Legacy provider | User has explicitly directed that the suspended credential must not be accessed, tested, changed or used. | **EXCLUDED BY PROJECT DECISION**. |

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
