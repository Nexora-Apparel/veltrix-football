# VELTRIX V2 — timestamped bookmaker quote evidence contract

Date: 2026-11-15
Status: IMPLEMENTED IN PR BRANCH; NOT APPLIED TO STAGING

## Purpose

Keep The Odds API quote observations as immutable, independently auditable evidence. The provider response, request, fixture identity, bookmaker, market, selection, price, source market timestamp, retrieval timestamp and rights approval must remain linked.

This is an evidence layer only. It does not create a bookmaker consensus, select a bet, change a model, publish predictions, or unlock value betting.

## Evidence identity

Each observation records:

- Provider/source: `the_odds_api` / `odds_api_v4`
- Sport key and provider event ID
- Canonical fixture ID and exact resolved FIXTURE crosswalk version
- Exact provider response ID and capture-request ID
- Bookmaker key/title
- Market key: `h2h`, `totals`, or `btts`
- Selection name and normalized selection key
- Totals line/point where required
- Decimal odds, strictly greater than 1 and below the defensive upper bound
- Provider market-level `last_update` raw value and parsed UTC timestamp
- Retrieval timestamp from the collector clock
- Exact raw-response SHA-256
- Source approval ID and rights-evidence SHA-256
- Immutable observation key and database-recorded timestamp

The database relation is `odds_quote_observations`, introduced by migration `0011_odds_quote_observations.sql`. It is append-only. A changed price, line, source timestamp, retrieval timestamp or response hash produces a new observation key; prior quote evidence is never overwritten.

## Point-in-time admission

For a forecast cutoff (T_c) and fixture kickoff (T_k), a quote is eligible only if:

1. Exact provider event → canonical fixture crosswalk is RESOLVED and valid at retrieval time.
2. The quote belongs to the exact fixture, bookmaker, market and selection.
3. The market-level source timestamp is timezone-aware and no later than retrieval.
4. The market-level source timestamp is no later than (T_c).
5. The collector retrieval timestamp is no later than (T_c).
6. Both timestamps precede kickoff, and (T_c < T_k).
7. The exact rights approval was effective, recorded, approved and valid at retrieval time for COLLECTION and STORAGE.
8. Response SHA-256, request/response/provider linkage and evidence hashes are valid.

A retrieval timestamp never substitutes for the provider market timestamp. Missing, naive, future, post-cutoff, post-kickoff or ambiguous observations are rejected. No timestamp is inferred from a neighboring field.

## Persistence integrity

Migration 0011 adds:
- Unique immutable observation key.
- Foreign keys to fixture, crosswalk, request, response and source approval.
- Composite provider/source response linkage.
- Database trigger checking that the crosswalk resolves the exact provider event to the exact canonical fixture at retrieval.
- Database trigger checking capture request ↔ response ↔ provider identity and raw response hash.
- Append-only trigger preventing UPDATE/DELETE.
- Indexes for fixture/market/time, provider event, response hash and rights lookup.

The writer must insert the request, response and quote observations atomically. The DB trigger independently checks identity and hash linkage; application-level checks independently validate raw bytes and rights evidence.

## Usage and release boundary

- Staging only; migration is not applied by application startup.
- No historical odds backfill or inferred quote timestamps.
- The one-event research probe remains capped at one credit-consuming request, one UK region, three markets, at most three estimated credits, and no retries.
- A fresh zero-credit quota preflight and approved competition/region/market rights remain mandatory immediately before dispatch.
- No recurring odds collection.
- No production deployment, prediction publication, Telegram delivery or value-bet activation.
- Market/odds evidence contributes to walk-forward or prospective evaluation only after the above gates pass.
- 98% timestamped odds coverage and all independent market certification thresholds remain unmet until measured from actual eligible observations.
