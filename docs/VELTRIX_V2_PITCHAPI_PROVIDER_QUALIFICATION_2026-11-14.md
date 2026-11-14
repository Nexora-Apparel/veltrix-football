# VELTRIX 2.0 — PitchAPI provider qualification

Date: 2026-11-14
Review scope: official public documentation only. No account or API key created; no endpoint, quota or authentication request made.

## Executive decision

PitchAPI is a high-value **conditional candidate**, not an approved provider.

Its official reference describes:
- Upcoming and played fixtures via date and league endpoints.
- Match, shot, event, lineup, team-stat and player-stat endpoints.
- Shot-level xG and xGOT, plus advanced team/player metrics including PPDA.
- Predicted lineups before kickoff, with an explicit `confirmed` flag.
- A provider-claimed 77-league catalogue and no-cost/no-paid-tier model, with a fair-use burst guard rather than a published daily request allowance.

Official documentation:
https://pitchapi.dev/
https://pypi.org/project/pitchapi/

The free-access and coverage claims are provider statements, not independently verified VELTRIX coverage. The SDK's MIT license covers SDK code only; it does not grant rights to the data returned by the service.

**Blocking issue:** the public documentation reviewed did not expose a clear data-use license or terms covering commercial/public display, retention, redistribution, or model training. Until these terms are obtained and reviewed, collection remains disabled. No account or key has been created.

## Data capability and limits

| Domain | Documented capability | VELTRIX assessment |
|---|---|---|
| Fixtures | Date and league schedules, including `status=upcoming` | Conditional candidate |
| Results | Finished match score and status | Conditional candidate |
| Expected goals | Shot-level xG, xGOT and aggregate team/player xG | Conditional candidate; provider model is not VELTRIX's own model |
| Lineups | Predicted lineup up to 48h pre-kickoff in supported competitions; confirmed status near kickoff | Conditional; require `confirmed=true` for confirmed-lineup features |
| Player stats | Match-level player data and advanced metrics | Conditional; coverage and provenance still need verification |
| Injuries | No injury endpoint identified in the public API reference | Not verified |
| Odds | No odds endpoint documented | Unavailable in reviewed API |
| Historical PIT evidence | History back to 2021 is claimed, but no complete immutable revision archive or per-record publication timestamps were documented | Not certifiable from historical bulk retrieval |

## Temporal and model-integrity rules

1. RFC 3339 UTC timestamps in the API are not automatically publication timestamps. Keep kickoff, retrieval, recording, provider update and source publication distinct.
2. Do not use fixture `time_utc` as source publication time.
3. Do not backdate historical data fetched today into prior point-in-time observations.
4. Predicted lineups must be stored with `confirmed=false`, the exact retrieval/recording clocks and the prediction label. They cannot be relabelled as confirmed.
5. Confirmed lineups require `confirmed=true` and capture before kickoff; if fetched after kickoff, they are historical outcomes, not pre-match features.
6. Treat provider xG as a separate provider model output. Do not blend it silently with xG from another source or treat it as a ground-truth label without model provenance and calibration checks.
7. Missing analytics (including matches for which the provider did not generate advanced metrics) remain missing. The provider documents `ANALYTICS_UNAVAILABLE` as a normal outcome for some matches.
8. Provider IDs are opaque. Resolve fixture/team/competition identities using evidence-backed crosswalks; do not parse IDs or match by name alone.

## Free access and request policy

The official docs state that the service has one no-cost plan, a 77-league catalogue and no daily request allowance, with an unadvertised fair-use burst guard that returns 429 and `Retry-After`. VELTRIX must still use bounded concurrency, caching, request logging and exponential backoff. No broad scan is approved by this review.

## Rights and security gate

Before dispatch:
- Obtain and retain the current terms/data license or written permission covering VELTRIX's public football analytics/prediction product.
- Verify permission for collection, caching, long-term storage, feature engineering, model training, derived predictions, public display and Telegram distribution.
- Confirm retention, deletion, attribution and redistribution restrictions.
- Confirm source provenance for xG and advanced metrics, including model/version or documented methodology.
- Verify competition coverage and per-competition lineup/analytics availability using a single bounded request only after authorization.
- Store any key in GitHub Actions/Vercel secret storage, never in source code, PR text or chat.

The API key is documented as a bearer credential in the `X-API-KEY` header. Do not expose it to browser/mobile clients or public repositories.

## Decision

- Registry state: `OPTIONAL_GATED`.
- `collection_allowed=false`.
- Fixture/results/xG/lineup/player-stat capabilities: `CONDITIONAL`.
- Injury capability: `NOT_VERIFIED`.
- Odds capability: `UNAVAILABLE`.
- No network adapter, API call, key creation, database import, schedule or production integration in this change.

PitchAPI could materially improve VELTRIX's xG and lineup coverage if rights and provenance are resolved. It is not yet a data dependency and must not be counted toward certified coverage.
