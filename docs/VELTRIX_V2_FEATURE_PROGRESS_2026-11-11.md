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
- Seven focused tests added; CI verification for this newest module is pending.

## Evaluation foundation added

- Expanding-window walk-forward fold builder partitions fixtures into disjoint chronological test windows.
- A training fixture is eligible only if its kickoff precedes the test window and its outcome settlement timestamp is no later than the training-label cutoff.
- Supports a configurable embargo, minimum training sample and number/duration of folds.
- Rejects duplicate fixture IDs, naive timestamps, invalid windows, empty test folds and insufficient training samples.
- This is evaluation infrastructure only; it does not fit models or calculate performance metrics.

## Verification state

- Foundation suite including venue context: **38 passed, 0 failed**; legacy-import boundary check passed on PR merge commit for head `ee90b575edeb3ff6a769333389469f5eab6a73ca`. [GitHub Actions run #42984863222](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42984863222).
- Corrected walk-forward suite: **45 passed, 0 failed**, including all seven walk-forward tests; legacy-import boundary check passed. [GitHub Actions run #42987573786](https://github.com/Nexora-Apparel/veltrix-football/actions/runs/42987573786).
- Elo feature and seven new tests were committed after that successful run. They are not yet included in a verified CI result.
- No model fitting, calibration, prediction publication, provider ingestion or production activation has been performed.

## Next gate

1. Verify the Elo module and tests in CI.
2. Continue deterministic, evidence-backed feature contracts only while StrikerAPI is credit-blocked.
3. Resume the provider dry-run only after credit balance/entitlement is restored.
4. Sign Phase 3 only after the provider dry-run completes with complete accounting, zero unresolved identity/score conflicts and unchanged database counts.
