# 5DollarFootballAPI — VELTRIX non-commercial authorization record

**Approval ID:** `approval-5dollar-community-fixture-result-benchmarking-2026-11-14`  
**Provider:** 5DollarFootballAPI  
**Account scope:** Community account; seven provider competition IDs listed below  
**Status:** APPROVED for the VELTRIX FOOTBALL 2.0 project-owner-authorized, non-commercial project use  
**Recorded:** 2026-11-15  
**Commercial use:** PROHIBITED  
**Raw redistribution:** PROHIBITED

## Authorization basis

The project owner has explicitly authorized use of covered project data for VELTRIX FOOTBALL 2.0 on the condition that the project is not monetised. The controlling project-wide record is:

- `docs/legal/veltrix-all-source-noncommercial-authorization-2026-11-15.md`

The provider-specific terms review is:

- `docs/legal/5dollar-terms-review-2026-11-12.md`
- Official terms: https://5dollarfootballapi.com/terms
- Terms version reviewed: October 2026

This record combines the project-owner non-commercial restriction with the provider-specific terms review. It does not grant new API entitlements, bypass account authentication, increase quotas, authorize paid endpoints, or establish source publication timestamps.

## Approved scope and uses

The account-entitled competition scope is restricted to these exact provider competition IDs:

- Brazil Serie A — `3118717965`
- Brazil Serie B — `522514093`
- England Premier League — `4160026622`
- France Ligue 1 — `3614399544`
- Germany Bundesliga I — `686337048`
- Italy Serie A — `3405541143`
- Spain La Liga — `4212821298`

Permitted non-commercial project uses within the account's actual technical entitlement:

- collection and automated acquisition;
- internal caching and storage;
- historical import of fixture/result labels;
- internal analysis, research, model training, validation and benchmarking;
- public display of permitted fixture/result fields with required attribution.

The Community account's previously observed limits were 300 requests/hour and 20 requests/minute. Those values are historical observations, not a live quota guarantee; every capture must re-check current provider status and remaining quota before making requests.

## Restrictions

- No monetisation, paid subscriptions, advertising-funded data exploitation, resale, sublicensing or commercial licensing.
- No raw response/feed redistribution.
- Preserve provider attribution for public display: **Football data by 5DollarFootballAPI** — https://5dollarfootballapi.com.
- Restrict all collection to the seven listed competition IDs and currently account-entitled endpoints.
- Do not treat settled-result availability proxies as exact source publication timestamps.
- Do not backdate observations or admit them as point-in-time pre-match features without independent source-time evidence.
- No historical odds endpoint use is authorized by this fixture/result record.

## Evidence and review

The approval record's evidence digest is computed from the exact bytes of this file by the Community qualification script. The linked project-wide authorization and provider terms review must be retained with it. Re-review if the provider terms, account plan, competition entitlement, attribution rules or project-owner authorization changes.

**Operational decision:** non-commercial Community fixture/result qualification may proceed as a bounded, read-only probe, subject to fresh account/quota checks and the script's hard request budget. All production, publication, scheduling and value-betting release gates remain separate and unchanged.
