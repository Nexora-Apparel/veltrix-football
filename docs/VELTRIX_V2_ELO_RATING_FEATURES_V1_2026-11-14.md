# VELTRIX FOOTBALL 2.0 — Elo rating features v1

## Purpose

Provide an independent, competition-scoped Elo rating snapshot as a challenger feature for the results-only Poisson model. This module does not generate 1X2 probabilities and does not claim predictive skill.

## Temporal and provenance contract

- Reuses the new model's observation contract and point-in-time eligibility function.
- Only rows explicitly marked `point_in_time_certifiable=true` can update historical ratings.
- Kickoff, result availability and ingestion timestamps must all precede the requested cutoff.
- Date-only observations use the existing conservative availability boundary.
- Rows from another competition are never mixed into the rating state.
- Duplicate fixture IDs are excluded in full, independent of input order.
- Unknown team histories fail closed; the initial rating is not emitted as a substitute forecast.

## Rating update

- Initial rating: 1500.
- K-factor: 20.
- Home advantage: 60 Elo points.
- Expected home score uses the standard logistic Elo expectation.
- Actual result score is 1 for a win, 0.5 for a draw and 0 for a loss.
- Same-timestamp fixtures are processed as an indivisible round: every expected score is computed from pre-round ratings, then all deltas are applied together.

These values are explicit research defaults, not fitted or certified parameters. They must be selected or tuned only through chronological walk-forward evaluation.

## Output

The snapshot returns each team's rating and eligible match count, the home-adjusted rating difference, expected home score, eligible observation count, and count of excluded non-certifiable records.

## Release boundary

- Elo is a feature/challenger, not a publishable probability model.
- No conversion to 1X2, BTTS or totals probabilities.
- No provider calls, paid services, database writes, migrations, website or Telegram integration.
- Any combined Poisson/Elo model requires separate chronological fitting and comparison against the existing Poisson and competition baselines.
