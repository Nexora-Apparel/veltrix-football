# Prospective Result Collector

**Status:** Implemented as a pure, network-free adapter. No polling or persistence is enabled.

## Scope

The collector accepts already-retrieved 5Dollar fixture rows for exactly the five signed, qualified competition IDs:
- Italy Serie A: `3405541143`
- France Ligue 1: `3614399544`
- England Premier League: `4160026622`
- Spain La Liga: `4212821298`
- Germany Bundesliga I: `686337048`

It accepts only `scheduled` and `finished` states. Unexpected statuses, cross-competition rows, invalid IDs and duplicate IDs are rejected with sanitized reasons.

## Safety boundary

`app/prospective_result_collector.py` has no HTTP client, network import, filesystem access, database connector, scheduler or retry loop. The caller must retrieve the response under a separately reserved request budget and supply the VELTRIX observation time, endpoint and run ID.

Each accepted row is converted into the append-only result availability observation contract. The raw payload is retained and hashed by that contract. The collector's output explicitly reports:
- `provider_requests_made = 0`
- `database_writes = 0`
- `imports = 0`
- `settlement_timestamps_created = 0`

`merge_collected_observations` validates provider, competition and run binding before appending to an in-memory ledger. Repeated appends are idempotent through the ledger's observation IDs.

## Important temporal semantics

The observation timestamp is when VELTRIX observed a response. A `finished` status means the provider exposed a terminal result at that observation time. It does not establish the actual final-whistle time and must never be used as a settlement timestamp.

No retrospective availability is reconstructed. Only observations captured prospectively from the moment the collector is operational can establish prospective availability history.

## Not yet implemented

- Provider polling / scheduling.
- Durable storage or database migration.
- Cross-run quota reservation and settlement integration.
- Poll cadence selection and backoff.
- Missed-poll and outage interval records.
- Provider correction/revision reconciliation.
- Retention and provider-rights review.

Those require a separate operational design and explicit approval. This commit does not make a provider request or change production state.
