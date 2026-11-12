# VELTRIX V2 — Provider rights clarification requests

Date: 2026-11-12
Purpose: resolve provider rights blockers before production collection, training or public display.

## PitchAPI

The technical API exposes football fixtures, results, shots, xG/xGOT, player statistics, events, lineups and advanced team metrics. Its published SDK license is MIT, but the SDK's own PyPI notice says that service data is governed separately by the PitchAPI Terms of Service.

Request written confirmation covering:

1. The legal entity providing the service and the identity of every upstream data provider.
2. Whether PitchAPI has authority to sublicense the underlying event, shot, player, lineup and xG data for commercial use.
3. Whether VELTRIX may collect, cache and retain historical data indefinitely or for a specified period.
4. Whether the data may be used to train, validate, calibrate and benchmark proprietary statistical and machine-learning football prediction models.
5. Whether VELTRIX may publish model-derived probabilities, predictions, match insights, performance statistics and value-bet verdicts on a commercial website and Telegram channel.
6. Whether any raw fields, derived fields, logos, player images or competition marks require separate licenses or attribution.
7. Any competition, territory, rate, retention, sublicensing, deletion or termination restrictions.
8. Whether rights survive cancellation for already collected data and models trained while the subscription was active.

**Approval rule:** no production ingestion, model training, persistent historical storage or public display until written responses explicitly cover the relevant uses and upstream rights.

Official technical documentation: https://pitchapi.dev/
SDK notice: https://pypi.org/project/pitchapi/

## GOAL API

The current Terms expressly state that GOAL API grants no license over underlying sports data and places responsibility for required rights on the customer. Technical access has been verified, but that is not a rights grant.

Request written confirmation covering:

1. The upstream provider(s) and rights holder(s) for each data type and competition.
2. Documentary confirmation that GOAL API is authorized to sublicense the data for VELTRIX's intended uses.
3. Explicit permission for collection, historical storage, model training, evaluation, benchmarking, commercial derivative outputs and public display.
4. Whether permissions cover fixtures, results, team/player statistics, lineups, injuries, transfers, logos, images and other visual assets separately.
5. The competitions and territories covered by each permission.
6. Required attribution, restrictions, retention periods and deletion obligations.
7. Whether existing data and trained models may be retained after subscription cancellation or termination.

**Approval rule:** keep GOAL API excluded from V2 training, persistent history and public display until the upstream chain of rights and required licenses are documented.

Official Terms: https://goal-api.com/terms
Official Privacy: https://goal-api.com/privacy

## Evidence to retain

For each provider response, preserve:
- The provider's legal entity and named upstream rights holders.
- The dated written permission or contract.
- Exact data types, competitions, territories and permitted uses.
- Retention, cancellation and deletion conditions.
- Attribution requirements.
- The internal approval ID and the person/date who reviewed the grant.

A marketing page, API key, successful HTTP response, SDK license or informal statement that the data is "free" is not sufficient evidence of rights.


## StrikerAPI — shot-event upstream rights and account terms

Please confirm in writing:

1. Which upstream source(s) provide the `get_events` shot locations and event records for each competition, including the exact source used for EPL, La Liga, Serie A, Bundesliga, Ligue 1, Argentina, Brazil and NWSL.
2. Whether OWSH Unlimited LLC has authority to sublicense those underlying shot-event records for commercial model training, historical retention, evaluation and commercial display of derived VELTRIX probabilities and insights.
3. Whether any source-specific restrictions attach to ESPN-derived events, shot coordinates, player identities, lineups or match statistics, and how those restrictions are communicated per competition.
4. Whether VELTRIX may retain immutable historical response snapshots and payload hashes after each daily refresh overwrites the provider's current record.
5. Whether the new Terms effective 2026-10-17 apply to this account now or only from 2026-12-16 (if the account was created before 2026-10-17).
6. Confirm that the provider's xG values are not point-in-time safe and that the raw shot-location/event fields may be used to train a separate customer-owned xG model.

The provider's public Terms permit commercial apps, storage and model training, but state that it is not the original producer of sports facts, does not grant league rights and does not publish a per-dataset source list. This request is intended to resolve the remaining upstream chain-of-rights uncertainty.

Official references:
- https://strikerapi.com/terms
- https://strikerapi.com/docs/timing-and-rights

## OpenFootAPI — competition-specific source rights

Please confirm for every competition/source pair VELTRIX intends to consume:

1. The exact upstream rights holder and source licence exposed in `meta.sources` and `/v1/competitions`.
2. Whether that licence permits commercial caching, historical retention, model training, benchmarking, public display and publication of model-derived probabilities/insights.
3. Any attribution, share-alike, redistribution, territory, or retention requirements.
4. Whether the Developer plan's FotMob-sourced xG shot maps are covered by the same per-competition licence metadata and whether VELTRIX may train its own xG model from the shot coordinates and outcomes.
5. Whether rights continue for lawfully retained data and trained models after cancellation, consistent with the current Terms.

Official references:
- https://openfootapi.com/terms
- https://openfootapi.com/docs
- https://openfootapi.com/pricing

## American Soccer Analysis — CC BY-SA 4.0 derivative scope

Please clarify whether training a proprietary prediction model on ASA's CC BY-SA 4.0 data, then publishing only model parameters, probabilities and match insights, is treated as an adaptation subject to share-alike. Also clarify whether the API's underlying data is a database subject to additional rights beyond the copyright licence.

Official references:
- https://app.americansocceranalysis.com/api/v1/__docs__/
- https://creativecommons.org/licenses/by-sa/4.0/

## OpenPlay — upstream data lineage

Please identify the upstream provider(s), contractual rights and sublicensing authority for the event records, shot locations, player/lineup data and xG fields in the v0.1.0 release. Confirm that the CC BY 4.0 declaration applies to every included record and that commercial model training, retention, derivative models and public display are permitted. Please also identify the scope and provenance of the 58 flagged data-issue matches and 39 known gaps.

Official references:
- https://github.com/nlbair/openplay
- https://github.com/nlbair/openplay/releases
