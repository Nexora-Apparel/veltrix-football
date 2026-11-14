# VELTRIX FOOTBALL 2.0 — Results-only Poisson baseline v1

## Scope

A clean-room, results-only baseline under `veltrix_v2.models`. It imports no legacy prediction, calibration, feature-engineering, fallback-prior, value-bet or publication code.

## Temporal contract

A training observation is eligible only when all timestamps are timezone-aware and:

- Match kickoff is strictly before the forecast cutoff.
- Result availability/publication time is at or before the cutoff.
- Local recorded/ingestion time is at or before the cutoff.
- Competition identity matches the target competition.
- Fixture identity is unique in the input batch.

Missing or malformed temporal evidence is excluded. No retrieval timestamp is substituted for publication time. The model does not infer historical availability for imported records whose timestamps are absent.

## Estimation

- Competition home/away goal rates form the scoring baseline.
- Team scoring and conceding rates are shrunk toward the competition mean using a fixed, explicit five-match prior strength.
- Expected goals feed independent Poisson score distributions.
- The score grid yields 1X2, BTTS Yes and Over 2.5 probabilities.
- Team history of one or two matches is usable for exploratory estimation, but is explicitly marked non-publishable.
- No team history causes a hard error; a league-only generic forecast is never emitted.

## Publication boundary

This baseline is not certified for production and its publication flag is hard-locked false. A separate sample-floor indicator requires at least 100 eligible competition matches and at least five matches for each target team; passing it only permits model review, not publication. Full chronological walk-forward evaluation, calibration, recent-holdout checks and prospective settlement are still required.

## Known limitations

- Independent Poisson assumptions do not model score dependence or low-score correlation.
- Team attack/defence are pooled across home and away venues.
- No lineup, injuries, rest, travel, tactical or odds features are included.
- The model should be benchmarked against a simple competition-rate baseline and later compared with Dixon-Coles only through independent chronological tests.

## Data limitation

Phase 3 historical imports are retained as historical records but are currently marked non-point-in-time-certifiable. Their missing publication/recorded timestamps are not backfilled. They cannot silently enter a point-in-time training set until independently timestamped evidence is obtained.
