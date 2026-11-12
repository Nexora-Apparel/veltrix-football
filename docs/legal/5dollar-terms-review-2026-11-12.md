# 5DollarFootballAPI Terms Review — 2026-11-12

- Provider: 5DollarFootballAPI
- Official terms: https://5dollarfootballapi.com/terms
- Terms last updated: October 2026
- Official API documentation: https://5dollarfootballapi.com/docs
- Community Access plan reference: https://5dollarfootballapi.com/community
- Review date: 2026-11-12
- Review scope: fixture/results collection, storage, historical model training, public display and attribution

## Terms reviewed

The provider's Section 4 states that customers may use its data in their own commercial websites, apps, models and internal tools, display scores/statistics/odds to end users, and cache API responses. It prohibits reselling or redistributing raw data as a competing data feed.

For Free and Community Access, public-facing products (website, app, bot or published dataset) must display the linked attribution:

**Football data by 5DollarFootballAPI** — https://5dollarfootballapi.com

Attribution is optional for private/internal use and for Pro, Ultra and Business. The provider supplies data as-is and disclaims a guarantee of accuracy or suitability for betting decisions. The terms do not specify a fixed raw-response retention duration or disclose the upstream data supplier. The VELTRIX interpretation is that internal storage/cache and use in proprietary models are permitted by Section 4; this is a recorded terms interpretation, not legal advice or an upstream data warranty. Raw response bytes remain internal and must never be resold or redistributed. Reconfirm retention rights with the provider before any public raw-data archive or bulk export.

## Account-specific evidence

The VELTRIX Community account was read-only checked on 2026-11-12:
- Plan: Community
- Rate limit: 300 requests/hour
- Burst limit: 20 requests/minute
- Seven visible competitions: Brazil Serie A, Brazil Serie B, England Premier League, France Ligue 1, Germany Bundesliga I, Italy Serie A, Spain La Liga
- Account response evidence: GitHub Actions run 43280026573, artifact `veltrix-phase1-provider-qualification`, file `fivedollar-account.json`
- No API key or credential value is included in this review record.

## VELTRIX use decision

Approved for the listed account-entitled competitions and the following uses:
- fixture and settled-result collection;
- internal storage and caching for VELTRIX operation;
- historical model training and evaluation using the source's fixture/result fields;
- public display of permitted fixture/result fields with the required Community attribution.

Not approved:
- raw feed resale or redistribution;
- treating provider results as source-timestamp-certified before the provider supplies a publication timestamp;
- using the provider's odds as a historical quote archive when no valid quote timestamp exists;
- using any competition outside the observed account entitlement.

The provider's upstream data supplier and underlying data-rights chain are not identified in the public terms; VELTRIX relies on the provider's direct Section 4 grant and keeps that provenance limitation visible.

For historical result-derived features, the API does not expose the original result-publication timestamp. VELTRIX therefore stores a four-day post-kickoff availability proxy with `point_in_time_certifiable=false`. It must not be represented as exact source publication time. This limitation does not change the use of settled scores as target labels.

## Evidence and review controls

This file is the VELTRIX review record, not a substitute for the provider's live terms. The approval record must retain this file's SHA-256, the official terms URL/version, reviewer identity and review timestamp. Re-review if the provider changes its terms, plan entitlements, attribution requirement or retention policy.
