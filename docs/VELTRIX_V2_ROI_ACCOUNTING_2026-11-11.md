# VELTRIX 2.0 ROI and settlement-performance accounting

Date: 2026-11-11

## Contract

The evaluator consumes authoritative `Settlement` records from the independent
V2 settlement layer. It does not settle matches itself, infer results, query
providers, or write to the production database.

- WIN, LOSS and PUSH stake amounts form settled turnover.
- VOID bets are counted but their stake is excluded from turnover, gross
  return and net profit. The returned void stake is not a profit.
- A PUSH returns the stake, contributes zero net profit, and remains in
  turnover. It is not counted as a decisive win or loss.
- Net profit is gross return less stake.
- ROI is net profit divided by settled turnover. It is null when turnover is
  zero; it is never represented as zero merely because no valid exposure exists.
- Win rate is wins divided by wins plus losses. Pushes and voids are excluded.
  The report separately exposes all four outcome counts and denominators.
- Metrics are emitted overall and separately for every market present.

## Uniqueness and validation

The current report accepts one authoritative row for each
(fixture, market, selection, period). Duplicate identities are rejected.
Corrections/resettlements must be preserved in an audit history outside this
summary and only the authoritative current settlement supplied to evaluation.
Money fields must be finite Decimals and internally consistent with the
settlement status and quoted odds.

## Uncertainty

Win-rate intervals use the 95% Wilson score interval. ROI intervals use a
deterministic percentile bootstrap over settled bet rows. The current bootstrap
is IID at the bet-row level: correlated bets on the same fixture, date, league,
or market can make it optimistic. It is a descriptive diagnostic, not a
certification interval. Before any value-betting certification, replace or
supplement it with a chronological, dependence-aware block bootstrap (at
minimum grouped by match/date) and report the method and sample unit.

Small samples do not establish profitability. No interval is produced for ROI
with fewer than two settled rows or fewer than 100 requested bootstrap draws.
No ROI or win rate is produced when its denominator is zero.

## Release boundary

This module is an offline evaluation primitive only. It does not authorize
training, calibration, production predictions, value-bet publication, Neon
writes, deployment, or Telegram scheduling. Certification still requires
the project-level sample-size, prospective, odds-coverage, positive-ROI
lower-bound, and bookmaker-benchmark gates.
