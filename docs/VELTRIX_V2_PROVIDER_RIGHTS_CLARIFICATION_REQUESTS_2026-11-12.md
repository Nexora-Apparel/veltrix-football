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
