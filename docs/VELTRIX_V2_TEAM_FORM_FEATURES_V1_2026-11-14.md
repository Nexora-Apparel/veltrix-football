# VELTRIX FOOTBALL 2.0 — Team form and schedule features v1

## Purpose

Expose transparent, results-derived team form features for later model comparison. This is a feature extractor, not a prediction model.

## Features

For each team, calculated from eligible competition-specific history:
- Match count and W/D/L record.
- Points per match.
- Goals for, goals against and goal difference per match.
- Last-five points per match.
- Home/away match counts and venue-specific goals-for rates.
- Rest days only when the most recent result has an exact kickoff timestamp.

## Temporal rules

- Only rows explicitly marked point-in-time-certifiable are admitted.
- Kickoff, result availability and recorded timestamps must all be no later than the requested cutoff.
- Date-only archive results use the shared conservative availability boundary.
- Date-only results never produce fabricated exact rest-day values.
- Duplicate fixture IDs are excluded in full.
- Competition history is isolated; unknown team history fails closed.

## Model-selection boundary

These features are research candidates. Their coefficients or inclusion must be selected through chronological walk-forward evaluation against the existing results-only Poisson baseline. No feature may be promoted because it improves a random split or in-sample fit.

No xG is inferred from goals, no provider calls are made, and no forecast publication, database writes, migrations, deployment, Telegram or scheduling are enabled.
