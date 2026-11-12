# VELTRIX 2.0 — Odds benchmark and CLV contracts

Status: isolated implementation on `veltrix-2.0-architecture-blueprint`. Not production-approved.

## Data boundaries

- `OddsSnapshot` is an immutable, UTC-normalized quote record.
- Quotes captured at or after kickoff are rejected; timestamps are never backdated.
- Market normalization groups only identical fixture, source, bookmaker, market, line, capture timestamp and kickoff.
- Complete selection sets are mandatory: HOME/DRAW/AWAY for 1X2, YES/NO for BTTS, OVER/UNDER for totals.
- Proportional overround removal produces benchmark probabilities; it does not create model inputs or value-bet approvals.
- Integer totals remain blocked until explicit push settlement is implemented.

## Benchmark comparison

The existing 1X2 comparison contract scores model and bookmaker forecasts against exactly the same settled fixture IDs. It reports model-minus-bookmaker deltas for multiclass Brier, log loss and ranked probability score. Negative deltas indicate lower loss. A benchmark win is not established by synthetic tests; it requires chronological, point-in-time, prospective evidence.

## CLV policy

A later pre-kickoff quote is not automatically a closing quote. CLV requires:
1. Exact fixture, source, bookmaker, market, selection and line identity.
2. Same kickoff timestamp.
3. A later capture timestamp, strictly before kickoff.
4. Explicit source-backed verification that the quote is the closing snapshot and a non-empty verification reference.

Positive probability-points CLV means the selection's implied probability rose from the taken quote to the verified close, indicating the taken price was better. The implementation labels only explicitly verified records as `VERIFIED_CLOSING_LINE_VALUE`.

## Remaining gates

- Provider-specific proof of what constitutes an official closing snapshot.
- Settlement contracts for integer-line pushes, voids, abandoned matches and extra-time rules.
- Walk-forward market comparison with timestamp-matched bookmaker quotes.
- Prospective sample and odds coverage thresholds from the accuracy standard.
- Exact-head CI and independent review.

No Neon writes, model training, calibration, production forecasts, deployment, or Telegram activation are authorized by these contracts.


## Certification provenance

Every odds snapshot intended for certification must carry a non-empty
`source_observation_id` resolving to an immutable provider observation. The
observation provider must match the quote source, its competition/season scope
must match the fixture, and it must have been available no later than quote
capture. The source approval must explicitly permit collection, storage,
benchmarking and commercial use. Quotes without this binding may still be
inspected in isolated normalization tests, but they cannot contribute to a
passing release certification.
