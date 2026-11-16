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
- Non-commercial source rights are registered in the project-wide and source-specific approval records. Model training may proceed only with datasets that pass schema, provenance, temporal-eligibility, competition-coverage and leakage controls.
- No value-bet publication until certification.
- No Vercel deployment until the quota/build-limit issue is cleared.
- No Telegram schedule activation until the user-authorized release gate is complete.
- Website, report and Telegram must render the same immutable forecast snapshot and version.

## 8. Immediate next engineering tasks

1. Fix the 5Dollar EPL catalogue discovery using documented `country=GB-ENG`, `search=Premier League` and `popular=1` discovery paths; retain strict exact identity matching and emit sanitized catalogue diagnostics if no unique EPL row is found.
2. Rerun paired acquisition; do not accept source download alone as reconciliation.
3. Add an exact team crosswalk and row-level score/kickoff/status reconciliation.
4. OpenPlay historical player/event/xG structure, hashes, rights and staging persistence are qualified. Continue competition-season coverage checks, feature extraction and temporal-eligibility tests; preserve CC BY 4.0 attribution and the source xG model ID.
5. Qualify FPL EPL player snapshots as a limited, undocumented source; keep it optional until terms and schema stability are reviewed.
6. Probe PitchAPI for endpoint access, actual upstream lineage, field coverage, timestamp semantics and schema stability. The project-wide authorization covers non-commercial use; monetisation remains prohibited.
7. Build point-in-time feature snapshots, then candidate score models and market-specific evaluation.


## 9. Personal-use scope and independent control domains (2026-11-15)

VELTRIX FOOTBALL is a personal-use project. Commercial monetisation assumptions are excluded from architecture, model development and release criteria. Do not require invoices, billing documents, business registration, commercial subscription proof, a revenue plan or advertising evidence to collect data, build models, run evaluation, certify a market or publish an integrity-verified personal report.

Keep these controls independent:

- **MODEL_QUALITY_GATES:** point-in-time provenance, data completeness, leakage prevention, chronological walk-forward evaluation, prospective settlements, calibration, benchmark performance, confidence intervals and market-specific certification.
- **PROVIDER_USAGE_GUARDS:** provider terms, endpoint entitlement, request/rate limits, current observable quota and bounded request/credit caps. A provider-specific usage guard may defer that provider request, but must not block independent work using 5DollarFootballAPI or another authorized source.
- **PUBLICATION_INTEGRITY_GATES:** exact report identity/hash, fixture/team/competition identity, cutoff-before-kickoff chronology, eligible evidence, authoritative certification, same-bundle website/report/Telegram parity, duplicate prevention, idempotent delivery and reconciliation of uncertain outcomes.

5DollarFootballAPI is the primary source. The Odds API is supplementary and should be queried only where bookmaker/market coverage, source quote timestamps, odds baselines or closing-line evidence add measurable analytical value. Do not treat odds-provider availability as a prerequisite for every prediction; only markets and analyses that require odds data should depend on it.

Provider terms and data rights remain binding regardless of personal use. However, billing paperwork and commercial subscription evidence are not model-quality, certification or publication-integrity requirements.
