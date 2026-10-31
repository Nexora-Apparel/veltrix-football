# VELTRIX Value Intelligence and Prospective Evidence

## Current operating mode
The engine is research-only. All outputs remain `SHADOW_MODE` / `LOCKED_SHADOW_MODE`; Telegram does not publish selections as betting tips, and no bookmaker actions are possible.

## Price intelligence
- Complete bookmaker outcome sets are proportionally de-vigged.
- Cross-book consensus uses the median of de-vigged probabilities.
- Model probabilities are shrunk toward market consensus (default model weight 35%).
- Bookmaker dispersion creates a transparent screening haircut. It is a heuristic, not a calibrated confidence interval.
- Quote eligibility is timestamp checked against fixture kickoff; stale, post-kickoff, or mismatched snapshots are rejected.
- Markets screened: 1X2, BTTS, and full-time totals 1.5, 2.5 and 3.5.

## Prospective evidence ledger
`app/value_evidence_ledger.py` records each observed bookmaker/market/selection quote using fixture identity, bookmaker, quote timestamp and market. The daily workflow restores `public-data/value_evidence_ledger.json`, merges the current report, uploads an Actions artifact, and republishes the validated ledger to the `command-data` branch.

Deduplication key: fixture + market + selection + bookmaker + quote timestamp. Repeated Telegram/report publication does not create a new price observation. Original observations are retained; the processor appends new observations and derives per-book price series.

Opening odds and CLV are only calculated after at least two distinct timestamped observations. Until then, opening/closing values remain null. The current implementation deliberately labels multi-snapshot CLV as `PROVISIONAL_NOT_CLOSING`: daily snapshots do not guarantee that the final pre-kickoff quote has been captured. It must not be presented as true closing-line value.

Completed scores are joined only by explicit fixture ID and completed status. Supported settlements: 1X2, BTTS and totals. Each observation receives a one-unit paper profit/loss record; this is not a live bet or actual return.

## Evidence required before promotion
1. A sufficiently large chronological, out-of-sample sample for each market and model version.
2. Calibration and proper scoring rules (Brier score/log loss), not accuracy alone.
3. Prospective odds observations at evaluation time and reliably captured final pre-kickoff prices.
4. Positive CLV across a meaningful sample, plus positive net paper ROI after realistic bookmaker margin, limits and price availability.
5. Stable performance by competition, market, odds band and time window.
6. A separately reviewed release certificate. No single profitable streak or high hit rate unlocks alerts.

## Known limitation
The existing daily odds snapshot is not an intraday price collector. This implementation does not increase The Odds API request volume or create extra 30-minute polling. Therefore, CLV remains provisional until an appropriately quota-budgeted closing-price collection mechanism is added and validated.


## Additional validation invariants

- A consensus set is formed only from bookmaker rows containing the identical complete outcome set; mixed/incomplete outcome sets are rejected.
- A single bookmaker can be recorded as a quote but cannot produce a shadow value candidate.
- The ledger marks each candidate quote separately. The published ROI field is explicitly quote-level paper ROI, not a realized betting return or an independently validated staking strategy.
- Settled observations are not silently overwritten if a provider later changes a final score. The original settlement remains and a `RESULT_CONFLICT_REVIEW_REQUIRED` record is added.
- Fixture visibility is validated before Telegram delivery and command-data publication. Eligible fixture row counts must reconcile; unforecastable fixtures remain visible with an explicit reason.
