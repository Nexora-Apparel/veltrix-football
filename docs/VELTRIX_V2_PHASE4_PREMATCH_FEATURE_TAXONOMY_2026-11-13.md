# VELTRIX FOOTBALL 2.0 — Pre-Match Feature Taxonomy & Eligibility Catalogue

**Assessment date:** 2026-11-13  
**Branch:** `phase4/provider-qualification-20261113`  
**Status:** Feature-design specification only — no model implementation or provider approval  
**Depends on:** Phase 4 provider qualification, point-in-time capture contract and capture validation test specification

## 1. Purpose

Define the candidate feature families the rebuilt engine may consider. This catalogue is deliberately provider-neutral. It defines semantic meaning, minimum source evidence, cutoff behavior and known leakage hazards; it does not claim that any candidate source currently supplies an eligible field.

A feature is not eligible merely because it is available in a historical API response. Each observation must pass rights, identity, source-publication timestamp, raw-provenance and cutoff checks.

## 2. Universal feature rules

- Use only information provably available at the fixture's frozen prediction cutoff.
- Compute rolling features from matches that had both kicked off and reached a reliably published final state before cutoff.
- Exclude the target fixture from every historical aggregation.
- Retain source, provider, competition, season, entity mapping and observation-version provenance for every input.
- Do not infer missing values from current standings, current team names, current injuries or post-match statistics.
- Fit transformations, normalization, feature selection and calibration inside each chronological training fold only.
- Keep missingness explicit; missing is not zero.
- Keep men's, women's, youth, reserve and senior competitions distinct.
- Do not use team names, league tables, season-end rankings or post-match aggregates as a shortcut for unavailable historical snapshots.
- A provider-supplied xG field is not automatically accepted; its definition, model version, timestamp and rights must be qualified.

## 3. Candidate feature catalogue

### F01 — Team result form

Potential fields:
- wins/draws/losses over rolling windows;
- goals for and against;
- points per match;
- home-only and away-only splits;
- opponent-strength-adjusted form, only after a separately validated strength estimator exists.

Eligibility:
- source final-result publication timestamp must be no later than target cutoff;
- fixture must have reached a settled state before cutoff;
- corrections must be versioned and selected as-of cutoff;
- historical 5Dollar result labels may be used as outcome records only when their settlement chronology can be established for the relevant target cutoff.

Leakage risks:
- season-end tables, retrospectively corrected scores, or results from matches played after target cutoff;
- using the Phase 3 four-day availability proxy as if it were a result-publication timestamp.

### F02 — Goal production and prevention

Potential fields:
- goals scored/conceded per match;
- rolling scoring/conceding rates;
- home/away scoring splits;
- clean-sheet and failed-to-score rates;
- goal-difference distributions.

Eligibility:
- derived only from F01-eligible results;
- use a fixed, documented rolling-window definition;
- exclude target fixture and any unsettled match.

Leakage risks:
- using final season totals for an in-progress season;
- incorporating post-cutoff results;
- unversioned result corrections.

### F03 — Shot volume and shot quality

Potential fields:
- shots, shots on target, shots conceded;
- shot location and body-part distributions;
- shot-event-derived chance quality;
- VELTRIX-owned xG model outputs, if independently trained and validated.

Eligibility:
- event data must be available before target cutoff to be used as a pre-match signal; a historical match's shot events are normally generated during that prior match and only become known after the event/match.
- For completed prior matches, event-derived features may be used only after their publication timestamp and settlement/availability are proven before target cutoff.
- Historical Wyscout event data may support offline research/model development within its approved CC BY 4.0 attribution scope, but it is not a current-season live feed.
- A VELTRIX-owned xG model must be trained only on eligible historical shot events and evaluated chronologically; it must not be described as provider-supplied xG.

Leakage risks:
- using post-match xG as if it were known before that match;
- training an xG model on future seasons and applying it to earlier seasons;
- mixing provider xG definitions without calibration/version metadata.

### F04 — Possession, passing and pressing indicators

Potential fields:
- possession share;
- pass completion and progressive passing;
- PPDA or other pressing proxies;
- defensive actions and recoveries;
- territory/field-tilt indicators, if definitions are stable.

Eligibility:
- require exact metric definition, units, collection methodology, source version and publication timestamp;
- use prior completed matches only;
- provider-specific PPDA definitions must remain separate until comparability is demonstrated.

Leakage risks:
- treating different providers' metrics as identical;
- using final match statistics for the target fixture;
- assuming post-match metrics existed at kickoff.

### F05 — Lineup and player availability

Potential fields:
- confirmed starting XI and formation;
- bench depth and substitutions availability;
- player minutes/load in prior matches;
- injuries, suspensions and return status;
- goalkeeper/defender/attacker availability indicators.

Eligibility:
- confirmed lineup must have a source publication timestamp before cutoff; a lineup published after cutoff is ineligible even if before kickoff.
- injury status must preserve first publication and subsequent revision history.
- distinguish confirmed, probable, doubtful, unavailable and unknown; do not collapse to a binary flag without a documented mapping.
- player-to-team registration and transfer validity must be versioned as-of cutoff.

Leakage risks:
- using final official lineups for a cutoff that predates lineup publication;
- retroactively applying current injury pages to old fixtures;
- treating absence from a lineup as proof of injury;
- using post-match minutes or substitutions as pre-match availability.

### F06 — Rest, schedule congestion and travel

Potential fields:
- days/hours since previous completed match;
- matches played in rolling 7/14/30-day windows;
- travel distance between prior venue and target venue;
- timezone changes and sequence of away fixtures;
- extra time and prior match duration, if available before cutoff.

Eligibility:
- previous match must be completed and known before cutoff;
- venue coordinates, fixture schedule and kickoff revisions must be versioned;
- travel estimate must be reproducible from the route/distance method and the known schedule at cutoff;
- do not assume team travel occurred at a particular time unless sourced.

Leakage risks:
- using rescheduled kickoff times not known at the historical cutoff;
- using actual travel information collected after the event;
- treating scheduled rest as actual rest without evidence.

### F07 — Bookmaker market information

Potential fields:
- timestamped 1X2, totals and BTTS prices;
- overround/de-vigged probabilities;
- line movement from earlier eligible snapshots;
- bookmaker consensus and dispersion;
- market availability and quote freshness.

Eligibility:
- quote timestamp must be proven no later than cutoff;
- retain bookmaker, market, line, selection, quote state, timestamp and raw provenance;
- historical snapshots from The Odds API are sampled observations, not continuous tick history;
- opening/closing labels must be defined relative to the captured timeline, never inferred from current endpoint values.

Leakage risks:
- using closing odds after the target cutoff;
- treating retrieval time or kickoff time as quote time;
- dropping missing bookmakers/markets from coverage denominator;
- training on bookmaker prices that are themselves unavailable at the declared decision time.

Policy:
- odds may be used as a benchmark or as a separately evaluated feature family; do not let the model's use of odds invalidate a claimed comparison against the same odds baseline. Report both market-informed and non-market model variants.

### F08 — Competition and match context

Potential fields:
- competition identity and tier;
- season phase and matchweek;
- neutral venue indicator;
- cup/league/knockout context;
- promotion/relegation or group-stage status where verified.

Eligibility:
- competition metadata must be valid for the target fixture and versioned if corrected;
- context must be known at cutoff;
- identity mapping must preserve gender/age/reserve distinctions.

Leakage risks:
- inferring team strength from final league position;
- using post-season qualification outcomes;
- applying current competition names/IDs to historical records without a versioned crosswalk.

### F09 — Weather and pitch context

Potential fields:
- forecast temperature, precipitation, wind and humidity;
- forecast pitch condition or venue surface, if sourced;
- forecast lead time and provider confidence.

Eligibility:
- use only forecast vintages actually issued before cutoff, not observed post-match weather;
- preserve forecast issue time, valid time, location, provider and model version;
- weather observation after kickoff is retrospective and ineligible.

Leakage risks:
- using observed weather instead of forecast;
- using the latest revised forecast for a historical date;
- assuming pitch condition without evidence.

### F10 — Team/player ratings and latent strength

Potential fields:
- Elo-like ratings;
- attack/defence strength;
- player availability-adjusted strength;
- competition-adjusted team ratings.

Eligibility:
- ratings must be recomputed sequentially using only eligible information known before each target cutoff;
- initialization, update cadence, home advantage, promotion handling and uncertainty must be documented;
- no rating may be trained using future-season outcomes and then backfilled into earlier dates.

Leakage risks:
- full-sample fitted ratings;
- retrospective team-strength values;
- random train/test split;
- unversioned changes to rating methodology.

## 4. Prohibited or quarantined feature inputs

The following must not enter a pre-match feature matrix unless independently reconstructed from timestamped, eligible source observations:
- final score, final match result, post-match xG, final shots, final possession, final PPDA or post-match player ratings for the target fixture;
- final league tables, final season rankings or end-of-season statistics;
- current injury/lineup pages used to infer historical availability;
- closing odds when the prediction cutoff precedes closing;
- future fixture outcomes, future transfers or future team identity mappings;
- Phase 3's four-day finished-status availability proxy as a source publication timestamp;
- any record with unknown or untrusted source-publication time;
- legacy model probabilities, priors, calibration outputs, feature weights or decision rules.

## 5. Feature lineage requirements

Every derived feature must carry:
- canonical feature name and semantic version;
- exact source observation IDs and raw response hashes;
- source publication timestamp bounds;
- target fixture and prediction cutoff;
- transformation code commit and dependency-lock hash;
- parameters/window definition;
- missingness reason and imputation state (if imputation is later approved);
- feature value, unit and computation timestamp;
- feature-set manifest hash.

A derived feature must be reproducible from its referenced observations. A feature without complete lineage is ineligible.

## 6. Initial conservative feature slate

No feature is approved for model training yet. After provider and endpoint qualification, the first low-complexity candidate slate should be considered in this order:
1. Results-derived rolling form and goal rates from verified pre-cutoff settled matches.
2. Schedule/rest features from versioned fixture and kickoff records.
3. Timestamped bookmaker market snapshots, evaluated as a separate market-informed variant.
4. Shot-event-derived team metrics from rights-cleared historical events, with temporal model fitting.
5. Lineup/player availability only after genuine publication-history evidence is secured.
6. xG, PPDA, weather and travel only after definitions, coverage and timestamp provenance are proven.

Start with a small, auditable feature set. Add complexity only when it improves out-of-sample performance on chronological folds and maintains complete lineage.

## 7. Feature-family approval matrix

A family can move to implementation only when all rows below are evidenced:

| Gate | Required evidence |
|---|---|
| Rights | Collection, retention and model-training permission for exact source/field/competition scope |
| Coverage | Measured fixture/season/field coverage and missingness |
| Timestamp | Source publication/snapshot timestamp or documented availability guarantee |
| Identity | Stable entity mapping with ambiguity rate reported |
| Semantics | Field definition, units, methodology and revision behavior |
| Provenance | Raw bytes, hashes, request and immutable version linkage |
| Temporal test | Adversarial cutoff tests and as-of selector pass |
| Reproducibility | Same input evidence produces same feature value and feature-set hash |

Unknown evidence is a fail-closed block, not a partial pass.

## 8. Explicit non-goals

This catalogue does not authorize provider purchases, new ingestion, migrations, model training, production deployment, prediction publication, Telegram activation, schedule changes or value betting. It does not approve any feature family today. It is a semantic design contract for later implementation once exact source endpoints and rights are qualified.
