# VELTRIX FOOTBALL 2.0 — Phase 2: Provider Rights and Access

**Date:** 2026-11-12  
**Working branch:** phase2/provider-rights-access  
**Status:** IN PROGRESS — legal-use registry and source-specific approvals implemented; final current-account entitlement reconciliation and CI remain.  
**Safety:** read-only provider evidence and local code/docs only. No production database writes, historical imports, model changes, prediction publication, Telegram delivery, Vercel deployment or scheduling.

## 1. Phase 2 objective

Convert provider discovery into explicit, source-specific and purpose-specific rights/access decisions. A successful HTTP response or API key is not blanket permission. Every source must be classified separately for:
- provider and exact source ID;
- data type and competition scope;
- account plan and current endpoint entitlement;
- collection, storage, caching, historical import, model training, benchmarking and public display;
- commercial-use permission;
- attribution obligations;
- raw-data redistribution prohibition;
- terms/licence version, review date and immutable evidence hash.

Rights approval and account entitlement are separate gates. A source may have terms that permit a use while the user's plan does not expose the required endpoint. The ingestion gate must require both.

## 2. Approved source stack

| Source | Data scope | Rights decision | Access decision | Restrictions |
|---|---|---|---|---|
| 5DollarFootballAPI | Fixtures and settled results | APPROVED under October 2026 Terms for commercial VELTRIX use | Community account observed active; 300/hour, 20/minute; exact seven-competition catalogue | Linked attribution required on public-facing Free/Community products. No raw-feed resale. Entitlement snapshot must restrict imports to the seven observed competition IDs. |
| The Odds API | Current/prospective bookmaker odds | APPROVED under Terms last updated 31 August 2026 | Current soccer odds endpoint access was verified in bounded provider qualification. Account tier is not independently recorded by that probe. | Storage, commercial display, derived values and statistical/ML training permitted. No raw-feed resale. Historical odds are paid-plan only and remain PROVISIONAL until paid entitlement is proven. |
| Pappalardo et al. / Wyscout Open Event Dataset | Historical shot/event data | APPROVED under CC BY 4.0 | Public historical dataset; no API account entitlement required | Historical only. Preserve attribution and licence notices. Train a VELTRIX-owned xG model; do not label it official Wyscout xG. Raw redistribution remains disabled by VELTRIX policy. |

## 3. 5DollarFootballAPI — account-scoped approval

The official Terms page last updated October 2026 grants use in a customer's own commercial websites, apps, models and internal tools; response caching and end-user display are permitted. Raw-feed resale or redistribution as a competing feed is prohibited. Community public-facing products must show the linked attribution:

**Football data by 5DollarFootballAPI** — https://5dollarfootballapi.com

The account evidence recorded in GitHub Actions run #43280026573 reports:
- Plan: Community
- Rate limit: 300 requests/hour
- Burst limit: 20 requests/minute
- Exact visible competitions: Brazil Serie A, Brazil Serie B, England Premier League, France Ligue 1, Germany Bundesliga I, Italy Serie A and Spain La Liga.

The later 365-day read-only acquisition run #43299701499 returned 2,496 finished fixtures across those seven competitions, complete pagination (26 pages), 28/40 requests, no duplicates and no rejected/quarantined rows. It performed no database writes.

**Country-pack handling:** the provider entitlement record did not expose a definitive country_pack_code. Brazil is visible in the exact competition catalogue, but VELTRIX does not infer or fabricate a country-pack code. Store country_pack_code as null and enforce the observed exact competition-ID set from the entitlement snapshot. No eighth competition may be imported without a new entitlement observation.

**Timestamp boundary:** the sampled market feed contained timestamps on 7/77 market blocks (9.09%). The 1X2 opening timestamp was present in the seven-fixture sample, while the other sampled market blocks lacked timestamps. The Community BTTS tick-history request returned HTTP 403. This does not meet the later 98% odds-timestamp certification gate. Historical scores may be target labels with the documented conservative kickoff-plus-four-days availability proxy; that proxy is not point-in-time feature evidence.

Review record: docs/legal/5dollar-terms-review-2026-11-12.md.

## 4. The Odds API — current odds approved, historical archive blocked

The official Terms last updated 31 August 2026 permit indefinite storage, commercial UI display, derived values and statistical/ML model training. They prohibit raw-feed resale, repackaging or redistribution as a standalone data product. Attribution is not required. Bookmaker names are for factual identification and comparison only; do not imply endorsement or sponsorship.

The bounded multi-source provider qualification verified current soccer catalogue/odds access, including h2h and totals, and event-specific BTTS capability. The official plan page currently advertises 500 monthly credits on its Free tier and states that historical odds are available on paid usage plans only.

Therefore:
- Current/prospective odds may be collected and retained with exact provider quote timestamps and quota headers.
- Historical archive access is not assumed from a valid API key or current-odds response.
- No paid upgrade, historical endpoint call or credit purchase is authorised in this phase.
- A future read-only account entitlement probe must establish the historical endpoint tier before any historical snapshot import.
- Preserve provider bookmaker/market last_update; never substitute local fetch time.

Review record: docs/legal/the-odds-api-terms-review-2026-11-12.md.

## 5. Wyscout open event dataset — historical CC BY 4.0 approval

The Pappalardo et al. public event dataset is identified as CC BY 4.0 in its data descriptor. It is suitable for historical shot-event research and training a VELTRIX-owned xG estimator from raw shot locations and event context.

Required attribution:

**Shot-event training data: Pappalardo et al. (2019), “A public data set of spatio-temporal match events in soccer competitions”, CC BY 4.0. Adapted to train the VELTRIX xG model.**

The dataset is historical, not a current-season feed. Preserve source IDs and licence/change notices. Do not represent a VELTRIX estimate as official Wyscout xG. The dataset is not imported in Phase 2; ingestion belongs to the traceable data pipeline phase.

Review record: docs/legal/wyscout-cc-by-4.0-review-2026-11-12.md.

## 6. Excluded or provisional providers

| Provider/source | Status | Reason |
|---|---|---|
| The Odds API historical odds | PROVISIONAL | Terms permit use, but account paid historical endpoint entitlement is not verified. |
| GOAL API | EXCLUDED | User confirms key is active; latest runner response was Cloudflare browser-signature HTTP 403. Upstream sports-data rights and intended-use grant remain unresolved. |
| StrikerAPI | EXCLUDED / conditional candidate | Account probe returned HTTP 402 with zero credits. Terms version depends on account acceptance date; no paid credits authorised. |
| OddsPapi | EXCLUDED | Terms do not expressly grant model-training, retention and commercial-display rights; no successful live quote evidence. |
| InferSports | EXCLUDED from ingestion | Bounded response schema exists, but no verified historical archive or quote-time coverage and rights grant is not established. |
| OpenPlay | QUARANTINED | Upstream WhoScored/Opta/Stats Perform data lineage and rights are not independently established, notwithstanding repository-level licence text. |
| StatsBomb Open Data | RESEARCH-ONLY / EXCLUDED from commercial pipeline | Published open-data agreement does not provide blanket commercial model-training approval. |
| OpenFootball / Football-Data.co.uk | EXCLUDED | Results quality/coverage and source-specific personal/academic-use restrictions do not support commercial V2 ingestion. |
| API-Football/API-Sports | EXCLUDED | Prior key suspensions; do not depend on this provider. |
| Highlightly | EXCLUDED | Limited coverage and rate-limit failures. |

Excluded sources must not be silently promoted to approved status because a future request succeeds. Requalification requires current terms evidence, exact account entitlement, data-type scope and source timestamp verification.

## 7. Implementation on this branch

- Added a formal The Odds API Terms review.
- Added a typed provider-rights registry that computes SHA-256 from the exact local legal review documents and builds SourceApproval objects.
- Separate approval records for The Odds API current odds (APPROVED) and historical archive (PROVISIONAL).
- Rights evaluator remains fail-closed for expired, provisional, revoked, unapproved, out-of-scope and non-commercial uses.
- Public display returns exact attribution obligations for 5Dollar and Wyscout.
- Raw redistribution remains prohibited by VELTRIX policy for every selected source.
- Provider entitlement remains a separate runtime check; rights approval cannot bypass the exact 5Dollar competition list or The Odds API historical-plan restriction.

No API keys, bearer tokens or credentials are written into the registry or review documents.

## 8. Phase 2 exit gates

1. **Terms evidence:** current official terms/licence review exists for every selected source, with exact version/date and SHA-256-bound local evidence.
2. **Rights code:** source-specific approvals are built from those exact review documents; rights decisions are purpose-specific and fail closed.
3. **Attribution:** public-display rights return exact required attribution for 5Dollar and Wyscout; The Odds API does not require attribution.
4. **Account entitlement:** 5Dollar Community entitlement is restricted to its exact seven observed competition IDs; no inferred country-pack code. The Odds API current odds access is distinguished from paid historical archive access.
5. **Exclusions:** GOAL API, StrikerAPI, OddsPapi, InferSports and OpenPlay remain excluded until their missing rights/access evidence is independently supplied.
6. **Tests:** provider rights registry and rights evaluator tests pass alongside the existing historical data foundation suite.
7. **Safety:** no database writes, data imports, prediction changes, Telegram delivery, deployment or scheduling.

**No provider may enter the Phase 3 traceable data pipeline without both an APPROVED source-rights record and a current entitlement observation covering the exact endpoint, competition, data type and intended use.**
