# Audited provider dataset pipeline

## Purpose

`app.provider_acquisition_dataset_pipeline.assemble_audited_provider_dataset` is the fail-closed orchestration boundary between retained provider acquisition evidence and chronological results-only feature reconstruction.

The pipeline performs two distinct admission stages:

1. **Settlement/provenance eligibility:** every acquisition record is audited through the signed settlement-source registry and provider raw-payload provenance bridge. Rejected records are excluded before dataset assembly.
2. **Canonical team identity eligibility:** both provider team IDs must resolve through the same trusted KMS-signed team crosswalk, scoped by provider and competition. The pair must have active mappings, matching team scope, and distinct canonical IDs. Missing, expired, revoked or scope-incompatible identities are rejected before reconstruction.
3. **Canonical season isolation:** every target's exact (provider, competition, source_season) identity must resolve through the trusted KMS-signed season registry at that target's feature cutoff. Every historical candidate is resolved against that same registry and cutoff; only rows with the target's canonical season ID may enter reconstruction. Unmapped, expired, revoked, out-of-scope or retrospectively issued mappings cannot qualify a target. Original provider season labels remain bound to raw source evidence.
4. **Feature-source qualification:** every feature cell must resolve to a KMS-signed source qualification that explicitly allows the feature and competition. The source registry is verified at the feature's own prediction cutoff, so a qualification issued later cannot retroactively qualify historical data. The snapshot retains the registry digest, signer ARN, timestamp semantics and evidence digests.
5. **Point-in-time feature eligibility:** only settlement-, team-identity- and season-admitted records are passed to chronological results reconstruction. Historical and target fixtures use canonical team IDs and the target's exact canonical season only. Targets lacking sufficient pre-kickoff history or valid feature snapshots remain in the adapter's withheld report.

The sanitized audit report is hash-verified before its decisions are used. The pipeline joins admitted identities back to the exact original acquisition records; it never substitutes the audit's sanitized summaries for the retained raw-evidence records.

## Offline command

```bash
export VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON='{"trusted_keys":[{"key_arn":"arn:aws:kms:REGION:ACCOUNT:key/KEY_ID","region":"REGION"}]}'

python scripts/assemble_audited_provider_dataset.py \
  --records retained_acquisition_records.json \
  --settlement-packages settlement_timestamp_packages.json \\
  --team-crosswalk-registry signed_canonical_team_crosswalk.json \\
  --team-crosswalk-as-of 2026-11-11T00:00:00Z \\
  --season-crosswalk-registry signed_canonical_season_crosswalk.json \\
  --season-crosswalk-as-of 2026-11-11T00:00:00Z \\
  --feature-source-qualification-registry signed_feature_source_registry.json \\
  --split-policy chronological_split_policy.json \
  --output audited_dataset_report.json
```

The trust JSON is an out-of-band allowlist. A signing key ARN embedded in any signed registry is not trusted unless it appears in this environment-provided allowlist. The command uses KMS only to verify signed settlement-source, canonical team, canonical season and feature-source registries. It makes no provider HTTP requests.

Inputs:
- `records`: array of normalized provider acquisition records retaining their raw source-evidence payloads.
- `settlement-packages`: object keyed by exact `provider:source_id`, containing signed settlement registry, source contract, fixture identity, timestamp payload and timestamp evidence.
- `team-crosswalk-registry`: KMS-signed canonical identity registry. Exact `(provider, competition, source_team_id)` mappings bind canonical team IDs and explicit men's/women's/reserve/youth scope.
- `team-crosswalk-as-of`: timezone-aware timestamp used by the coverage report; each acquired record is independently resolved at its own provider retrieval timestamp and revalidated at each target's feature cutoff.
- `season-crosswalk-registry`: KMS-signed exact provider/competition/source-season to canonical-season mappings.
- `season-crosswalk-as-of`: timezone-aware timestamp used by the coverage report. The reconstruction adapter independently re-verifies the same registry at every target's own feature cutoff and filters all historical rows to the target's canonical season.
- `feature-source-qualification-registry`: KMS-signed source contracts that bind exact feature names and competition scope to reviewed timestamp semantics and evidence digests. Each target snapshot verifies the registry at its own feature cutoff; coverage reporting verifies the same registry digest against every snapshot.
- `split-policy`: explicit chronological train/validation/test policy accepted by the existing dataset adapter.

Output:
- Per-record settlement eligibility decisions and rejection reasons.
- Feature snapshot and withheld counts, including point-in-time reconstruction reasons.
- Dataset and source-evidence manifests when eligible snapshots exist.
- Separate team identity evidence: original provider IDs, canonical IDs, team scope, signed registry digest, signer ARN and verification timestamp. Raw provider payloads and their original provider-ID normalization remain unchanged and independently hash-verifiable.
- Canonical season identity evidence embedded in each feature snapshot: provider, competition, original source-season label, canonical season ID, signed registry digest, signer ARN, verification timestamp, review evidence digests and reviewer.
- Per-feature source qualification evidence: registry digest, signer ARN, verification timestamp, observation/availability timestamp semantics and qualification evidence digests.
- A canonical pipeline report digest.

## Safety boundaries

This pipeline does not train models, import into a database, publish predictions, enable value betting, dispatch Telegram messages, or schedule acquisition. `dataset_assembled=true` means only that a chronological dataset artifact was assembled; it is not model-training authorization or release certification.

No record is eligible merely because a provider says `finished`. Settlement admission requires the separately qualified, signed final-whistle evidence contract. Historical feature reconstruction also requires point-in-time availability; downloading a finished match today does not establish that its data was available before a historical fixture's kickoff.

## Current qualification state

The orchestration and tests are software implementation. No production settlement source is currently qualified, no real historical dataset has passed this pipeline, and no model accuracy or market certification is claimed.
