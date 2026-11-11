# VELTRIX FOOTBALL — Provider Terms and Data Provenance Register

Review date: 2026-11-11
Status: operational terms review completed; no legal opinion or third-party data licence is implied.

## 1. 5DollarFootballAPI

Official references:
- https://5dollarfootballapi.com/terms
- https://5dollarfootballapi.com/pricing
- https://5dollarfootballapi.com/docs
- https://5dollarfootballapi.com/docs/changelog

### Account and access requirements
- Verified project Free account; GitHub Actions secret is exactly FIVEDOLLARFOOTBALL_API_KEY.
- Authentication supports Authorization: Bearer key or X-API-Key. Keep the key in GitHub Secrets only.
- Free plan: 60 requests/hour, 20 requests/minute burst ceiling, top-five European leagues, last three months of results and Bet365 odds markets.
- Respect X-RateLimit headers and HTTP 429 / Retry-After. Extra keys do not multiply quota.
- Keys remain active after cancellation but revert to Free-plan entitlements.

### Permitted use, attribution and restrictions
- Published terms allow commercial websites, apps, models and internal tools; display of scores, statistics and odds; and caching API responses.
- Raw data cannot be resold or redistributed as a competing data feed.
- Free, Community Access and Education Access public-facing products must show the exact linked attribution: Football data by 5DollarFootballAPI. A footer, About page, bot description or README is accepted. Attribution is optional on Pro, Ultra and Business.
- Data is supplied as-is; accuracy and suitability for betting are not warranted. Non-SLA plans do not guarantee uninterrupted service.
- API keys must remain secret; account holders are responsible for activity under their keys.

### VELTRIX account-specific qualification
- Verified Free catalogue returned EPL, La Liga, Serie A, Bundesliga and Ligue 1.
- Only confirmed overlap with the StrikerAPI qualification set is EPL, provider competition ID 4160026622.
- Free plan returns only the last three months of results; it is not a full historical archive.
- Bounded EPL reconciliation compared 100 finished fixtures from each provider over 90 days: 100 unique matches, zero unmatched, ambiguous, quarantined, duplicate or conflicting rows; kickoff, status and scores agreed. It was read-only with zero database writes.
- Although Bet365 odds markets are exposed, the latest project live report found no usable matched 5Dollar prices. Do not approve 5Dollar odds until real matched, timestamped quotes are demonstrated.

### Approval
- Approve 5Dollar for EPL fixtures/results only, within the Free-plan three-month window and quota.
- Do not approve Argentina, Brazil, NWSL or other competitions absent from the verified Free catalogue.
- Do not approve odds for production model/value calculations until matched quote coverage and timestamps are demonstrated.
- Add the required attribution to a visible website footer/About location and Telegram bot description before public-facing release displaying 5Dollar data.

## 2. StrikerAPI

See STRIKERAPI_DATA_GOVERNANCE.md and STRIKERAPI_READONLY_QUALIFICATION.md.

- Free account: 500 credits/month, no card; list_games costs 2 credits.
- Key is stored as GitHub Actions secret STRIKERAPI_API_KEY.
- Commercial use of derived data and model outputs is permitted under published terms; raw feed redistribution is prohibited; no attribution is required; StrikerAPI grants no league/team marks or official rights.
- Bounded fixture/results approval: EPL, Argentina and Brazil. NWSL is excluded from the supported launch/import scope; its 2026 page/API count discrepancy remains unresolved pending written provider clarification.
- Other competitions and non-fixture datasets are not approved by this record.

## 3. Shared provenance rules

Every persisted observation must retain provider and endpoint, provider competition/team/fixture IDs, retrieval timestamp UTC, source payload SHA-256, raw and normalized status, schema/version when available, account plan/quota context, data type, competition/season coverage and correction/re-fetch lineage.

Do not infer that one provider's team or fixture ID is another provider's canonical ID. Preserve provider identity and record crosswalk evidence separately.

## 4. Phase 3 source approval matrix

| Provider | Competition | Fixture/results | Odds | xG / shot data | Decision |
|---|---|---|---|---|---|
| 5Dollar Free | EPL | Approved, last 3 months | Not approved pending matched quote evidence | Not established | Limited approval |
| 5Dollar Free | La Liga / Serie A / Bundesliga / Ligue 1 | Catalogue verified; not part of current cross-provider qualification | Not approved here | Not established | Coverage known, import not qualified |
| 5Dollar Free | Argentina / Brazil / NWSL | Not entitled in verified Free catalogue | Not entitled | Not entitled | Unsupported |
| StrikerAPI Free | EPL | Approved, bounded evidence | Not approved by this record | Not approved by this record | Limited approval |
| StrikerAPI Free | Argentina | Approved for fixture/results within bounded probe | Not approved by this record | Not approved by this record | Limited approval |
| StrikerAPI Free | Brazil | Approved for fixture/results within bounded probe | Not approved by this record | Not approved by this record | Limited approval |
| StrikerAPI Free | NWSL | Excluded from supported launch/import scope; 224 vs 240 discrepancy unresolved | Not approved; NWSL odds archive absent | Not approved for model use; shot locations from 2025 require separate validation | Excluded |
| StrikerAPI Free | Other 13 competitions | Not qualified by current bounded run | Not approved | Not approved | Unsupported pending qualification |

A limited provider/competition approval is not a full Phase 3 sign-off. Historical import pipeline qualification and execution of the reproducible Python database acceptance runner remain open. NWSL is excluded from the supported launch scope until the provider discrepancy is resolved and independently requalified.
