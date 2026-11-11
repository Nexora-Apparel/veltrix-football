# VELTRIX 2.0 — Market settlement policy

Status: isolated implementation on `veltrix-2.0-architecture-blueprint`; not production-approved.

## Match status

- `COMPLETED`: requires non-negative regulation-time goals.
- `ABANDONED`, `POSTPONED`, `CANCELLED`: paper selections settle as `VOID`; stake is returned and net profit is zero.
- An abandoned match's partial score is never treated as a completed result.
- Fixture IDs must match exactly between selection and result.

## Market rules

| Market | Selection | Settlement |
|---|---|---|
| 1X2 | HOME / DRAW / AWAY | Compare scores in the declared period |
| BTTS | YES / NO | Both teams score at least once in the declared period |
| Totals | OVER / UNDER | Compare combined goals with the exact line |

Supported totals lines are half-goal and integer lines only:
- Half-goal lines (e.g. 2.5): no push is possible.
- Integer lines (e.g. 2.0): exact equality is a PUSH; stake is returned.
- Quarter-goal Asian lines (e.g. 2.25, 2.75) are rejected until split-stake settlement is implemented.

## Match period

Default is regulation time. Extra time is included only when the selection explicitly declares `INCLUDING_EXTRA_TIME`. Penalty shoot-out goals are always excluded. The settlement period must match the bookmaker market's actual rules before any real benchmark or paper ROI calculation.

## Paper return arithmetic

- WIN: gross return = stake × decimal odds; net profit = gross return − stake.
- LOSS: gross return = 0; net profit = −stake.
- PUSH / VOID: gross return = stake; net profit = 0.

These are paper-ledger calculations, not live wagers or realized earnings.

## Still blocked

- Provider/bookmaker-specific settlement rules and market period verification.
- Quarter-goal Asian line split-stake settlement.
- Extra-time market identity mapping for competitions with special rules.
- Settlement corrections, resettlement audit history and duplicate result conflict handling.
- Walk-forward ROI aggregation and confidence intervals.
- Prospective evidence gates and exact-head CI.

No Neon writes, live bets, production predictions, deployment or Telegram activation are authorized.
