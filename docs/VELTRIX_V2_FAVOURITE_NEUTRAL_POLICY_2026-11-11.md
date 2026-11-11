# VELTRIX V2 Favourite-Neutral Model Policy

Date: 2026-11-11
Status: enforced model-input contract

## Objective

Estimate match outcomes from verifiable football evidence. Do not select or favour a team because it is home, away, famous, popular, highly ranked, socially prominent, or priced as the bookmaker favourite.

## Prohibited predictors

The outcome model must not ingest:
- team popularity, fanbase size, social engagement, media coverage, reputation or name recognition;
- bookmaker favourite labels, implied probabilities, odds, market rank or public betting percentages;
- competition prestige or club brand as a proxy for team strength;
- a hard-coded home-win prior, fixed home boost, or home/away default outcome.

Odds are permitted only in a separate, timestamp-matched benchmark/value-evaluation lane. They must never leak into the football-strength estimator or its feature pipeline.

## Permitted evidence

- Settled scores and verified team/player performance.
- Competition- and season-scoped attack/defence estimates.
- Point-in-time player and team form with source provenance.
- Lineups, injuries, rest, travel and tactical metrics only when their availability timestamps precede kickoff and their provenance/quality gates pass.
- A home-advantage coefficient estimated from the training sample, with uncertainty and chronological validation. It is not a fixed bonus and may be weak, zero, or negative.

## Symmetry and fairness requirements

1. Home and away teams use the same team-strength estimation process.
2. Team identity is an opaque canonical ID; names, badges and popularity are presentation metadata, not model features.
3. Underdog status is not a penalty. The model must be capable of assigning the away win or draw the highest probability.
4. No favourite-selection rule is allowed in candidate generation, forecast ranking, or publication.
5. Evaluate performance by outcome class, home/away orientation, favourite/underdog cohort (benchmark-only classification), competition and confidence band.
6. Report coverage and abstentions alongside accuracy. Do not force a pick when evidence is weak.
7. Benchmark odds must be captured before kickoff and aligned to the same fixture, market and timestamp. Benchmark labels must not be used as training features.

## Current implementation boundary

The current Poisson strength estimator accepts fixture IDs, competition/season, timestamps, canonical team IDs, settled scores, source-observation IDs and quality state. It has no fields for popularity, reputation, rankings, bookmaker odds or favourite labels. Its home coefficient is fitted from training data. The Dixon-Coles head transforms expected-goal rates into one coherent scoreline distribution; it does not choose a favourite.

This policy is an architecture constraint, not evidence of predictive accuracy. It must be checked in code review and feature-manifest tests whenever new model inputs are added.
