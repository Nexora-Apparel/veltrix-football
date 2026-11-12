# VELTRIX FOOTBALL 2.0 — Accuracy Target, Model Strategy and Publication Standard

**Decision date:** 2026-11-11  
**User objective:** pursue an 80% observed hit rate on carefully selected published predictions, while preserving probability quality, value and broad fixture coverage.  
**Status:** design standard; no production model is approved by this document.

## 1. What “80% accuracy” means

An 80% result cannot be guaranteed in advance. Football outcomes are stochastic, and a model that claims 80% on every fixture or every market without prospective evidence is not credible.

VELTRIX will report three different quantities, never blend them into one headline:

1. **Selection hit rate:** correct settled selections / all settled published selections.
2. **Coverage:** published selections / eligible fixtures considered.
3. **Probability quality:** Brier score, log loss, calibration and ranked probability score.

Each market is measured independently:
- 1X2 exact outcome (three classes);
- BTTS Yes/No;
- Over/Under for each named goal line (e.g. 1.5, 2.5, 3.5).

A combined 80% figure across markets is prohibited because it can conceal weak performance in one market. The dashboard must show sample size, date span, competition, market, confidence band, coverage, hit rate and uncertainty interval.

The 80% target applies to the **high-confidence published selection subset**, not to every match. VELTRIX may publish up to 25 fixtures per day, but must publish fewer when evidence does not support 25. Never lower a threshold just to fill the daily quota.

## 2. Prediction architecture — independently rebuilt

Use a transparent, competition-aware ensemble rather than one monolithic black-box model.

### Layer A — score-generation core
- Hierarchical attack/defence strengths with partial pooling by competition and season.
- Dixon–Coles adjusted bivariate Poisson as the initial scoreline baseline, including low-score dependence correction.
- Dynamic team strength (Elo-style) as a separate signal, not a direct probability substitute.
- Recency weighting with parameters selected only inside chronological training folds.
- Explicit home advantage and neutral-ground handling.
- Cold-start uncertainty; no fabricated league-average priors presented as team-specific evidence.

### Layer B — expected-goals and chance-quality signals
- Shot-level xG only when the provider, model version, penalty treatment, coordinates and timestamp provenance are known.
- Separate xG model identities. Never treat OpenPlay xG, provider xG and a proprietary xG model as interchangeable.
- Team shot volume, shots on target, big chances, box entries, set-piece production and chance conversion where coverage is verified.
- Shrink small samples toward competition-level estimates with uncertainty, not hard-coded defaults.

### Layer C — player and tactical context
- Confirmed lineups, player minutes, starts, goals, assists, shots, xG/xA, goalkeeper saves, defensive actions and cards.
- Availability/injury/suspension records with source timestamp, status semantics and confidence.
- Expected minutes and role, not simply player name presence.
- Rest days, congestion, travel, home/away sequence and competition switching.
- Tactical metrics such as PPDA only if the source definition and coverage are documented.
- Predicted lineups must be marked predicted; only timestamped confirmed lineups may be treated as confirmed.

### Layer D — market information
- De-vigged bookmaker prices form a strong external benchmark and may be an input feature only when their quote timestamps precede the forecast cutoff.
- Preserve bookmaker, market, line, price, timestamp, opening/closing status and source.
- Do not use closing odds to predict a match at an earlier cutoff.
- Keep a market-only baseline so the ensemble must demonstrate incremental value over bookmaker probabilities.

### Layer E — ensemble and calibration
- Generate out-of-fold predictions from each candidate model using expanding chronological folds.
- Combine models with weights learned only from historical training folds.
- Calibrate 1X2, BTTS and each goal line independently using a held-out chronological calibration segment.
- Candidate calibrators: temperature/Dirichlet calibration for multiclass 1X2; isotonic or logistic calibration for binary markets where sample size supports it.
- No calibration fit on the final test set; no random train/test split.

## 3. Confidence and abstention policy

The model must be allowed to say **NO BET / NO PREDICTION**.

For every candidate selection, store:
- calibrated probability;
- model disagreement / ensemble dispersion;
- data completeness and freshness;
- lineup status;
- competition qualification status;
- bookmaker benchmark probability and timestamp;
- expected value only when odds are valid and time-aligned.

Use a confidence tier and market-specific threshold selected from walk-forward results. Do not choose a universal 80% probability threshold by intuition. A probability threshold is not the same thing as an 80% observed hit rate.

Publication gate:
- source and competition qualified;
- all required fixture/team identities resolved;
- point-in-time feature cutoff passed;
- minimum data-completeness and freshness passed;
- calibrated probability and uncertainty available;
- no material provider conflict;
- forecast generated before kickoff;
- selection clears the market-specific historical precision threshold and minimum sample requirement.

If the gate fails, retain the fixture record but suppress the forecast chip. This is not a system error; it is a deliberate abstention.

## 4. Validation design

### Chronological walk-forward
- Expanding training windows and strictly later test windows.
- All features must have been available by the forecast cutoff.
- Result settlement must occur before a record enters training.
- Use an embargo around test boundaries to prevent delayed data leakage.
- Test windows must be disjoint.
- Tune features, model hyperparameters, ensemble weights and calibration only inside training/validation windows.

### Baselines
Compare each candidate against:
1. competition base rates;
2. a simple Poisson/Dixon–Coles baseline;
3. Elo baseline;
4. de-vigged bookmaker consensus at the same forecast timestamp;
5. the previous candidate model only as a historical benchmark, never as an imported dependency.

### Reported metrics
For 1X2:
- exact outcome accuracy;
- multiclass Brier score;
- log loss;
- ranked probability score;
- calibration by probability bucket and outcome class.

For BTTS and O/U:
- hit rate, precision, recall and coverage;
- binary Brier and log loss;
- calibration curve and reliability table;
- results by line, competition and confidence band.

For betting/value:
- timestamped odds coverage;
- closing-line value using comparable market/line;
- flat-stake net ROI after realistic costs;
- 95% confidence interval using date-clustered bootstrap or another predeclared dependence-aware method;
- drawdown and selection concentration.

### Existing certification thresholds remain mandatory
- At least 1,000 walk-forward settled matches per market.
- At least 300 prospective settled selections.
- At least 90 distinct dates.
- At least 98% timestamped odds coverage for value analysis.
- Net ROI > 0 and lower 95% ROI confidence bound > 0.
- 1X2 beats the bookmaker baseline on Brier and log loss.
- Value betting remains locked until all criteria pass.

For the additional 80% high-confidence target, require at least 300 prospective settled selections **in that specific market/confidence cohort**, plus a 95% confidence interval. Do not call the target attained if the point estimate is 80% but the sample is too small or the lower confidence bound is materially below the agreed precision threshold.

## 5. Data quality policy

- Qualify every provider × competition × season × data-domain independently.
- Keep fixture, player, lineup, injury, event, xG and odds rights separate.
- Every observation stores provider, native IDs, retrieval time, availability time, payload hash, schema version and rights approval reference.
- Missing values remain missing; zero is a real value, not a substitute for missing.
- No fuzzy identity merges; explicit crosswalks only.
- Unzoned local timestamps retain their original precision and are not converted to UTC by guesswork.
- Do not infer a player's availability from absence in a lineup feed.
- Do not infer injury status from a predicted lineup.
- Use only features published before the match forecast cutoff.

## 6. Competition coverage and the 25-fixture objective

- Start with the already qualified EPL scope.
- Expand to other competitions only after fixture identity, results, timestamps, field coverage and rights pass separate acceptance.
- Maintain competition-specific calibration and performance reports.
- Use hierarchical transfer only when the competition relationship and data coverage justify it; never copy EPL calibration into an unrelated league by default.
- Select up to 25 fixtures/day from all qualified competitions, including underdogs.
- Do not use favourite status as a selection filter.
- A high-confidence draw, away win or underdog market remains eligible if the evidence and market price support it.
- If only 6 fixtures pass, publish 6. If none pass, publish no predictions.

## 7. Operational safeguards

- No changes to the legacy prediction system.
- No production ingestion until source reconciliation and isolated database dry-run pass.
- No model training until accepted datasets and rights approvals exist.
- No value-bet publication until certification.
- No Vercel deployment until the quota/build-limit issue is cleared.
- No Telegram schedule activation until the user-authorized release gate is complete.
- Website, report and Telegram must render the same immutable forecast snapshot and version.

## 8. Immediate next engineering tasks

1. Fix the 5Dollar EPL catalogue discovery using documented `country=GB-ENG`, `search=Premier League` and `popular=1` discovery paths; retain strict exact identity matching and emit sanitized catalogue diagnostics if no unique EPL row is found.
2. Rerun paired acquisition; do not accept source download alone as reconciliation.
3. Add an exact team crosswalk and row-level score/kickoff/status reconciliation.
4. Qualify OpenPlay historical player/event/xG data and its CC BY 4.0 attribution requirements.
5. Qualify FPL EPL player snapshots as a limited, undocumented source; keep it optional until terms and schema stability are reviewed.
6. Probe PitchAPI only after provider confirms source lineage, storage, commercial display and model-training rights.
7. Build point-in-time feature snapshots, then candidate score models and market-specific evaluation.


## Low-history team handling

The Poisson strength model and walk-forward runners accept a team with one eligible historical match by default. Team estimates are regularized by the model rather than replaced with a generic fallback probability. A team with no eligible history is not assigned an invented rating: the fixture is abstained. Low-sample form features retain their sample count and low-sample quality state. This expands evidence use without weakening the independent publication, calibration and point-in-time release gates.


## 9. Core audit corrections — 2026-11-11

- The 5Dollar Free account is limited to approximately 90 days of historical results. Its V2 runner now defaults to a 90-day diagnostic window and a 60-day minimum usable span. Shorter chronological folds permit a diagnostic run against the actual entitlement; the per-market 1,000 held-out-match certification threshold is unchanged. A 90-day run is not expected to certify the model by itself.
- The historical runner now emits separate held-out calibration diagnostics for 1X2, BTTS and totals. These are explicitly marked diagnostics-only; no calibration mapping is considered fitted or approved by this report.
- A Poisson model that did not converge cannot emit expected goals, including through direct model calls. Training input order is sorted before optimization for deterministic results.
- Source approval must be active both when the observation is retrieved and at the forecast cutoff. An approval granted after retrieval or expired before retrieval is not applied retroactively without explicit provider terms.
- Player-match statistics whose availability timestamp precedes kickoff are rejected. Observed feature values require positive sample counts and source-observation lineage.
- The Odds API parser requires exact provider event identity, an explicit kickoff timestamp and a provider quote timestamp no later than capture. Binary bookmaker benchmark pairs must sum to one. Normalized quote records validate raw implied probability against decimal price.
- ROI reporting only labels the confidence interval as a date-block bootstrap when the interval was actually computed. Insufficient draws, dates or provenance remain explicitly unavailable.
- Prediction and value-bet release certificates carry their market evidence and verify that result flags match that evidence. A passing flag without the required evidence is rejected.
- These changes improve fail-closed behavior and diagnostic reproducibility. They do not establish live-data coverage, calibration quality, model accuracy, prospective ROI or production readiness.
