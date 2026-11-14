# VELTRIX 2.0 — Competition-level evidence coverage auditor

Date: 2026-11-14

## Purpose

The offline coverage auditor measures how much fixture-level evidence is eligible for use, grouped by competition and data domain. It is a diagnostic report, not a model certification or publication gate.

## Inputs

- Canonical fixture identity and competition.
- Exact timezone-aware kickoff timestamp.
- Evidence domain, provider and source identity.
- Source availability and recording timestamps.
- Raw payload SHA-256.
- Explicit rights approval identity, evidence SHA-256, evaluation timestamp and approval boolean.
- Point-in-time certification boolean.
- An explicit timezone-aware audit cutoff.

The auditor does not fetch providers, read credentials, infer rights, resolve team identity, or promote uncertified records.

## Temporal semantics

- Results evidence may become available at or after the fixture kickoff, but must be available and recorded no later than the audit cutoff.
- Prematch domains (fixtures, form, strength, rest, odds, xG, lineups, injuries and player statistics) must have been available strictly before kickoff.
- All timestamps must be timezone-aware.
- Missing timestamps, naive timestamps, late evidence, invalid hashes, mismatched fixture/competition identity, missing or malformed rights approval evidence, non-boolean approval flags and uncertified observations are rejected.
- Coverage is counted per distinct canonical fixture, not per provider response. Multiple providers corroborating one fixture do not inflate the denominator or numerator.
- Provider provenance is retained as a sorted list for each competition/domain report.

## Report fields

For every competition and requested domain:
- target fixture count
- eligible fixture count
- coverage ratio
- missing fixture IDs
- rejected evidence count
- contributing providers

A 100% ratio means only that every fixture in the supplied scope has at least one eligible record for that domain. It does not establish statistical quality, representative competition coverage, source rights beyond the supplied approval evidence, model performance, or permission to publish.

## Operational constraints

- GOAL API and StrikerAPI remain hard-blocked while credits are exhausted.
- No provider network calls or credit consumption.
- No database writes, migrations, deployment, scheduling, Telegram activation or public predictions.
- The Odds API remains optional and separately gated.
- OpenFootball date-only archives cannot satisfy exact temporal evidence requirements.
- StatsBomb Open Data remains historical research-only pending rights and attribution review.
- Missing xG, lineups, injuries and player statistics remain missing; no synthetic fill or zero imputation.

## Next integration

Build a read-only adapter that converts persisted, provenance-verified capture records into the auditor's typed inputs. The adapter must preserve original timestamps and rights evidence and must not infer point-in-time eligibility from retrieval time.
