# VELTRIX 2.0 timestamped odds source and fallback policy

Date: 2026-11-11

## Source order

1. Primary: 5DollarFootballAPI Bet365 per-fixture odds response.
2. BTTS fallback: The Odds API event-specific BTTS endpoint, only when the primary BTTS market is incomplete or absent.
3. No quote: abstain from value-bet selection for that market. Never infer a missing price, carry a quote across fixtures, or substitute another market's price.

The football-strength model never consumes bookmaker odds. Odds are a separate benchmark, value-selection and CLV lane.

## Primary capture contract

For each selected fixture, V2 calls the 5Dollar per-fixture odds endpoint once and records the V2 response-retrieval timestamp as captured_at. The parser accepts only complete market groups:

- 1X2: HOME, DRAW, AWAY;
- BTTS: YES, NO;
- O/U 2.5: OVER, UNDER on the exact 2.5 line.

The current pre-match closing/current price is used; opening prices are not silently substituted for missing current quotes. All snapshots carry fixture ID, source ID, bookmaker ID, market, selection, line, captured_at and kickoff_at. Any provider-supplied quote timestamp is stored separately. Captures at or after kickoff are rejected.

A single response may legitimately omit a market. Missing market coverage is reported explicitly and does not create a partial selection group.

## BTTS fallback

The Odds API event-specific endpoint requests only the btts market for the already-matched provider event. It returns bookmaker prices and market last_update. V2 stores:

- local fixture ID and provider event ID;
- sport key and bookmaker key;
- YES and NO prices;
- response captured_at;
- provider last_update when valid and no later than captured_at;
- kickoff_at.

The provider event must match the canonical home/away team identities and kickoff. Ambiguous, mismatched or duplicate event joins are rejected.

Quota guardrails:
- maximum 10 event-specific BTTS fallback requests per day;
- maximum 300 requests per provider quota window;
- preserve at least 100 requests of headroom against the documented 500/month Free allowance;
- stop fallback requests when the provider reports insufficient remaining quota or a rate limit;
- do not retry 401, 403 or 429 automatically.

The current 2026-11-11 probe reported 298 requests remaining. The cap is intentionally below the plan ceiling and must be enforced by a persistent quota ledger before prospective collection starts.

## Coverage and certification

The 2026-11-11 5Dollar sample covered five upcoming EPL fixtures:
- 1X2 complete: 5/5;
- O/U 2.5 complete: 5/5;
- BTTS complete: 3/5.

This is a small qualification sample, not a population estimate and not certification. The Odds API fallback is intended to cover missing BTTS prices, subject to its daily/monthly budget. Additional competition-level samples are still required.

For prospective certification, calculate timestamped-odds coverage separately for 1X2, BTTS and each supported O/U line over the complete eligible prediction universe. The threshold is at least 98% for each market. Every missing, stale, mismatched or post-kickoff quote counts as uncovered. Do not exclude abstained forecasts from the odds-coverage denominator after seeing whether a quote exists.

If coverage falls below 98%, the market remains uncertified and no value-bet verdict is published for it.

## Closing-line value

A later pre-kickoff snapshot is required to measure CLV when no verified provider opening/closing archive exists. A 06:00 WAT capture is the report-time quote; it is not a closing quote for a fixture kicking off later. CLV is computed only from the same bookmaker, market, selection, line and fixture, with strictly increasing quote times and both observations before kickoff.

## Release boundary

This policy does not authorize value-bet publication. The existing prospective requirements remain: at least 300 settled selections, at least 90 distinct dates, positive net ROI with a positive lower 95% confidence bound, and 1X2 Brier/log-loss better than a bookmaker benchmark on identical fixtures. Historical odds without source timestamps cannot satisfy prospective timestamped-odds coverage.
