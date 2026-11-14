# VELTRIX 2.0 — Prospective first-observed shadow evidence

Date: 2026-11-14

## Why this mode exists

Some legitimately usable providers expose no trustworthy historical source-publication timestamp or complete revision archive. That prevents their retrospective snapshots from qualifying as point-in-time (PIT) training evidence for chronological walk-forward certification.

However, once the collector retrieves a finished result, that exact result state is demonstrably known to VELTRIX at the retrieval time. That observation can safely support a forecast made **after** the retrieval time, provided the system never backdates it.

This change introduces a separate evidence class for that limited purpose. It does not relax or modify the PIT-certified path.

## Timestamp semantics

For a finished result snapshot:
- `available_at = retrieved_at`: the first time the collector demonstrably observed this response.
- `recorded_at >= retrieved_at`: when the normalized observation was recorded.
- `source_published_at` remains unknown and is not invented.
- A provider's conservative four-day proxy is not relabelled as a publication timestamp.
- The row carries `availability_basis=collector_first_observed_v1`.
- The row always carries `point_in_time_certifiable=false`.

A forecast can use this row only when its prediction cutoff is at or after both the first-observed and recorded timestamps. It cannot be used to reconstruct a historical cutoff before the collector first saw it.

## Separate model/ledger path

The 5Dollar capture adapter's explicit `prospective_observed=True` mode and `CapturedResultEvidence.to_first_observed_match_observation` create a non-PIT MatchObservation from the exact raw response and persisted capture manifest with:
- exact raw-response SHA-256;
- exact retrieval/first-observed time;
- collector item and manifest SHA-256 values;
- provider/source/fixture/team/competition identities;
- rights approval ID;
- an explicit non-PIT flag.

The admission function `admit_prospective_observed_shadow_forecasts`:
- accepts only this exact evidence basis;
- requires manifest and item evidence hashes;
- rechecks STORAGE and MODEL_TRAINING rights at use time;
- checks exact target identity, cutoff, model and feature hashes;
- requires the model output to remain non-publishable;
- writes a `PROSPECTIVE_OBSERVED_ONLY` PaperPrediction with `point_in_time_certifiable=false`.

The paper ledger stores these as `SHADOW_PREDICTION`, distinct from PIT-certified `PREDICTION` events. The hash chain and JSONL persistence remain append-only. This class is not included in historical walk-forward evaluation or PIT certification.

## Settlement boundary

For a `SHADOW_PREDICTION`, the settlement adapter records the collector's exact first-observed result time for both availability and retrieval. It never substitutes the provider's four-day proxy. It still requires the source's conservative settlement-delay boundary to have elapsed before accepting the result; that delay basis is stored separately in the settlement event.

Settlement still requires COLLECTION, STORAGE and BENCHMARKING rights. The current 5DollarFootballAPI approval explicitly includes MODEL_TRAINING but does not include BENCHMARKING. Therefore 5Dollar shadow settlements remain blocked until the separate approval-scope gap is resolved. No rights purpose is inferred from another purpose.

The adapter requires an unambiguous prediction event for the fixture. If multiple model versions exist, the caller must specify the model version.

## What this mode does not do

- It does not mark any observation PIT-certified.
- It does not make historical backtests valid.
- It does not bypass source approval, scope or use-time rights checks.
- It does not authorize public predictions, website display, Telegram delivery, scheduled jobs or value betting.
- It does not solve the 1,000-match walk-forward certification requirement.
- It does not make GOAL API or StrikerAPI necessary; both remain dormant until their monthly credit reset.

## Validation

Offline tests cover first-observed timestamp semantics, non-PIT flag preservation, manifest/item hashes, non-publishable admission, distinct shadow event types, append-only JSONL round-trips, settlement first-observed timing and explicit BENCHMARKING rights enforcement.

No provider requests, database writes, migrations, schedule activation, Telegram activation or deployments are part of this change.
