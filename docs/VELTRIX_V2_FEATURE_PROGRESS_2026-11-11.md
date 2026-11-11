# VELTRIX FOOTBALL 2.0 — Feature Foundation Progress
Date: 2026-11-11
Branch: `veltrix-2.0-architecture-blueprint`

## Data qualification gate

- Neon production read-only acceptance: PASS. The workflow verified the intended `veltrix-football` database, PostgreSQL 18.6, 11 public tables, 11 primary keys, 7 foreign keys, 5 unique constraints, 83 CHECK constraints, 22 indexes, one migration and one PASS reconciliation audit. The transaction was explicitly read-only.
- Isolated provider-backed dry-run: BLOCKED. The isolated Neon connection and database identity checks passed, but the first StrikerAPI fixture request returned HTTP 402. The account owner confirmed the StrikerAPI credit balance is exhausted.
- No provider import or database write occurred. Do not retry provider calls until credits/entitlement are restored and the account is confirmed usable.
- Phase 3 remains unsigned. The bounded source scope and NWSL exclusion remain unchanged.

## Independent feature modules implemented

### Team form
- Recency-weighted goals for, goals against and points per match.
- Strict provider, competition and season scope.
- Results must be final, kicked off before cutoff and available by cutoff.
- Missing history remains missing; small samples are explicitly marked.
- Duplicate provider fixture IDs and duplicate source-observation IDs fail closed; non-finite half-life parameters are rejected.

### Team schedule load
- Rest days since last match.
- Match counts over rolling 7/14/30-day windows across competitions.
- Uses only settled, point-in-time-available matches.
- Rejects duplicate fixture and source-observation identities.

### Venue context
- Reads only explicit provider venue observations for the exact fixture.
- Encodes neutral-ground status only when the provider explicitly supplies a boolean.
- Records whether a venue identity is actually available.
- Future observations are excluded; missing or unknown neutral status remains missing.
- Does not infer venue from the nominal home-team designation.
- Multiple eligible observations fail closed pending upstream correction resolution.

### Competition-scoped Elo
- Replays settled results chronologically within a single competition; ratings carry across seasons but never across competitions.
- Uses pre-match ratings for simultaneous home/away updates and configurable K-factor/home advantage.
- Excludes results not available by the forecast cutoff and all future kickoffs.
- Exposes ratings and Elo expected score as descriptive features, not calibrated match probabilities.
- Cold-start teams remain explicitly missing; no fabricated 1500 rating is emitted for a team with no eligible appearances.
- Duplicate fixture/source identities and invalid timestamps/parameters fail closed.

## Evaluation and market-coherence foundation

- Expanding-window walk-forward fold builder partitions fixtures into disjoint chronological test windows.
- Training outcomes must be settled before the test-window cutoff, with configurable embargo; test windows are disjoint.
- Strict 1X2 proper-scoring functions calculate multiclass Brier, log loss and ranked probability score.
- RPS uses the ordinal AWAY/DRAW/HOME order by increasing home goal difference.
- Paired model-versus-benchmark comparison reports Brier, log-loss and RPS deltas on the exact same settled fixture set; negative deltas indicate lower scoring loss.
- Forecast vectors must be real, finite, strictly positive, normalized and uniquely keyed; forecast/outcome fixture sets must match exactly.
- Joint scoreline distribution contract derives 1X2, BTTS and half-goal O/U probabilities from the same normalized scoreline mass. Integer totals lines are rejected until explicit push settlement is implemented.
- No market-specific independent fallback or silent probability renormalization is allowed.
- Scoreline-derived markets are deterministic transformations only; this does not fit or train the goal model.

## Verification state

- Foundation suite including venue context: **38 passed, 0 failed**; legacy-import boundary check passed. [Run #42984863222](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42984863222).
- Corrected walk-forward suite: **45 passed, 0 failed**, including all seven walk-forward tests; legacy-import boundary check passed. [Run #42987573786](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42987573786).
- Elo feature suite: **52 passed, 0 failed**; legacy-import boundary check passed. [Run #42988271363](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42988271363).
- Team-form duplicate-evidence guards and initial 1X2 scoring tests: **66 passed, 0 failed**; legacy-import boundary check passed. [Run #42988562701](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42988562701).
- Paired benchmark comparison, strict probability typing and ordinal RPS ordering: **70 passed, 0 failed**; legacy-import boundary check passed. [Run #42988827971](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42988827971).
- Scoreline-to-market derivation, including half-goal-line/push safeguards, was added after run #42988827971. Fresh CI verification is pending.
- No model fitting, calibration, prediction publication, provider ingestion or production activation has been performed.

## Next gate

1. Verify scoreline-derived market coherence tests in CI.
2. Resume provider dry-run only after StrikerAPI credit balance/entitlement is restored.
3. Sign Phase 3 only after the provider dry-run completes with complete accounting, zero unresolved identity/score conflicts and unchanged database counts.
