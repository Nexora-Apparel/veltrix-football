# Settlement Timestamp Source Qualification Adapter

## Purpose

The 5DollarFootballAPI and StrikerAPI fixture payloads currently prove terminal
match status but do not document a wall-clock full-time timestamp. The adapter
in `app/settlement_timestamp_source.py` accepts timestamps only from a
separately qualified source. It does not infer settlement time from kickoff,
match duration, event minutes, odds ticks, provider update time, or retrieval.

## Admission boundary

The adapter requires a source contract with:

- an exact source identifier;
- `qualification_status: qualified`;
- a 64-character qualification digest referring to the independently
  verified qualification record;
- an explicit timestamp field path;
- timestamp semantics exactly `final_whistle`;
- an explicit list of supported competition IDs.

The contract is a consumer of a separately verified qualification registry.
The adapter does not itself authenticate a registry signature. Callers must
verify the registry and bind its admitted contract before calling this module.
A digest provides integrity, not proof of source authenticity or truth.

## Evidence contract

Each candidate binds:

- exact source fixture ID, competition, home/away canonical team IDs and kickoff;
- exact expected fixture identity (no fuzzy name or score-based matching);
- raw source payload and canonical SHA-256;
- timestamp field and declared semantics;
- settlement timestamp with explicit timezone;
- observation and retrieval timestamps, ordered after settlement;
- source qualification digest and a canonical evidence digest.

Naive timestamps, unsupported semantics, unqualified competitions, identity
mismatches, pre-kickoff settlement times, observation/retrieval chronology
violations and tampered evidence are rejected.

## Multi-source reconciliation

When more than one qualified source is available, each source may contribute
one candidate. Duplicate source IDs are rejected. The reconciler rejects
cross-source disagreement greater than the configured tolerance (default 60
seconds). It does not silently average timestamps. Reconciliation output is
still evidence, not automatic dataset admission.

## Current limitation

No timestamp source has been qualified or integrated into the existing
provider dataset bridge. The new module is a fail-closed adapter and synthetic
contract tests only. Existing 5Dollar and StrikerAPI records remain ineligible
for training labels until a real source is qualified and its evidence is
integrated and independently verified. No model training, production import,
prediction publication or Telegram delivery is enabled by this component.
