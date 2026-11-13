# The Odds API — VELTRIX Rights and Access Review

**Review date:** 2026-11-12  
**Provider:** The Odds API Pty Ltd  
**Official terms:** https://the-odds-api.com/terms-and-conditions.html  
**Terms version:** Last updated 31 August 2026  
**API documentation:** https://the-odds-api.com/liveapi/guides/v4/  
**Plan reference:** https://the-odds-api.com/  
**Review scope:** current bookmaker odds, storage, caching, benchmarking, model training, commercial display and historical-archive entitlement.

## 1. Terms reviewed

The current Terms expressly permit:
- storing and retaining provider data indefinitely;
- displaying odds in websites, mobile apps, dashboards and other user-facing applications, including commercial use;
- calculating and displaying derived values;
- using provider data to train statistical and machine-learning models;
- research papers and analytical dashboards.

The Terms prohibit reselling, repackaging or redistributing the raw data as a standalone data product, including a competing API, feed or downloadable raw-data archive. Attribution is not required, although the provider appreciates it.

The provider states that bookmaker names and trademarks remain the property of their respective owners and may be used for identification, descriptive reference and factual market comparison, not to imply sponsorship, endorsement or commercial association. The provider supplies data as-is and disclaims warranties; VELTRIX must not present odds as guaranteed accurate or as wagering advice.

## 2. Access and entitlement boundary

The public plan page currently lists:
- Free access: 500 credits per month, current odds and sports coverage;
- historical odds: paid usage plans only.

The VELTRIX multi-source qualification run verified successful current soccer catalogue/odds responses, including h2h and totals, and the project integration supports BTTS event-market requests. This proves bounded current-odds endpoint access at the time of that run. It does **not** prove the user's account has a paid historical-odds entitlement.

Accordingly:
- **Current/prospective odds:** approved for bounded collection and use under the current terms, subject to actual response/quota headers and endpoint access at retrieval time.
- **Historical odds archive:** entitlement-blocked / provisional until a read-only account check proves the paid historical endpoint is enabled. Do not call or import historical snapshots on the assumption that a valid API key grants this tier.
- **Quote timestamps:** retain the provider's bookmaker/market last_update value. Never substitute local retrieval time for quote time.
- **Quota:** persist x-requests-remaining, x-requests-used and x-requests-last from each response. Budget each region-market combination separately.

## 3. VELTRIX permitted use

Approved for current/prospective odds:
- collection and internal storage;
- cache and operational use;
- bookmaker benchmarking and de-vigged market comparison;
- proprietary statistical/ML model training and evaluation;
- commercial display of current odds and derived values in the VELTRIX website/app.

Not approved:
- raw odds-feed resale, redistribution or provision through a competing data API;
- implying bookmaker sponsorship or endorsement;
- historical-archive ingestion before paid-plan entitlement is verified;
- treating local fetch time as the source quote timestamp.

raw_redistribution_allowed remains false even though derived-value and user-interface display are permitted.

## 4. User-facing safeguards

The project must distinguish market data from VELTRIX model output, show source quote timestamps, and disclose that odds can change or be stale. If a future page promotes bookmakers, links to wagering operators or otherwise promotes gambling services, include appropriate responsible-gambling and age-restriction messaging and complete a separate jurisdictional review. Do not add affiliate links as part of this rights approval.

## 5. Evidence and re-review

The official Terms page was checked on 2026-11-12 and states that its latest update was 31 August 2026. The official homepage was checked on 2026-11-12 for plan distinctions and current-vs-historical access. The VELTRIX approval record must store this file's SHA-256, the official Terms URL/version, review timestamp and reviewer identity.

Re-review if the Terms, plan matrix, historical endpoint entitlement, quota or bookmaker coverage changes. This is a documented VELTRIX interpretation, not legal advice or a warranty from upstream bookmakers.
