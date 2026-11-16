# VELTRIX V2 deployment trust verifier

## Runtime configuration

The website and Telegram application use the same deployment factory:

- `VELTRIX_V2_REPORT_BUNDLE_URL`: HTTPS URL to the exact canonical GitHub raw file `command-data/public-data/v2_report_bundle.json`.
- Optional `GH_TOKEN` (or `GITHUB_TOKEN`): a GitHub token with `attestations:read` permission. The repository is public, so the verifier can query public attestations without a token; configure a token only if higher API rate limits are needed.
- Optional `VELTRIX_V2_EVIDENCE_ALLOWED_HOSTS`: comma-separated exact hostnames permitted for certification evidence retrieval. Defaults to `raw.githubusercontent.com`; add another exact host only when an approved evidence object is stored there.
- Optional `VELTRIX_V2_PUBLICATION_VERIFIER_FACTORY`: defaults to `veltrix_v2.reporting.trusted_runtime:build_deployment_publication_verifier_factory` when a bundle URL is configured.

The verifier runs in the Python application process. It does not require the GitHub CLI. It retrieves attestation bundles from the GitHub repository attestations API and verifies each candidate using the `sigstore` Python package. The verifier pins repository, workflow identity, workflow name, `workflow_dispatch` trigger and `refs/heads/main` source ref. The GitHub API response is only a discovery mechanism; it is not treated as proof.

## Report-bound certification manifest

The verifier loads:

`reports/certification/publication-manifests/{report_id}.json`

from the repository's `main` branch. The manifest must have schema `VELTRIX_V2_CERTIFICATION_MANIFEST_V1`, status `CERTIFIED`, the exact report ID and exact canonical report SHA-256, and non-empty certification records. The attestation subject digest is the SHA-256 of the exact manifest bytes. The manifest's certification records are then checked against the report's published fixtures and markets.

The dedicated workflow `.github/workflows/report-certification-attestation.yml` is dispatchable only on `main`. Before signing, it runs `scripts/veltrix_v2/verify_pre_attestation_report.py`, which checks the report-bound manifest, every market gate, all evidence hashes, provider-rights approval, terms and active entitlement. Only after that complete preflight passes does it create a GitHub artifact attestation for the exact manifest bytes. The pre-attestation verifier's local digest callback is used only to validate the bytes being signed; deployed consumers never use that callback and require the independently verifiable Sigstore attestation. It never creates a manifest or fabricates a certification.

## Provider-rights evidence schema

Every certification record carries `provider_id` and `provider_scope`, in addition to `rights_approval_id`, `rights_evidence_uri` and `rights_evidence_sha256`. The rights evidence object is JSON with schema `VELTRIX_PROVIDER_RIGHTS_EVIDENCE_V1` and must contain:

- `approval_id`, `provider_id`, `permitted_scope`, `status: APPROVED`, `evaluated_at`
- `provider_id` must equal a registered provider `source_id`; unregistered providers and providers in `SUSPENDED_CREDITS` state are rejected even if a rights object claims approval
- `allowed_actions` containing all three explicit uses: `MODEL_TRAINING`, `PUBLIC_DISPLAY` and `PREDICTION_PUBLICATION`
- `terms_version` and `terms: {status: ACCEPTED, version, checked_at}`
- `entitlement: {status: ACTIVE, checked_at, quota: {remaining}}`; `expires_at` is optional because some provider plans do not expose an account expiry, but if present it must be timezone-aware and in the future

The evidence hash must match the exact retrieved bytes. The rights evaluation timestamp must exactly match the certification record. Entitlement and rights checks must be no more than 24 hours old, terms checks no more than 365 days old, timestamps must be timezone-aware, and quota remaining must be a positive integer. The approval ID, provider identity and scope must exactly match the certification record.

Evidence URLs must use HTTPS, an exact configured hostname, no credentials, query string, fragment, nonstandard port or redirect. The initial production allowlist supports repository-pinned raw GitHub paths under `raw.githubusercontent.com/Nexora-Apparel/veltrix-football/main/`; move evidence into that immutable repository path or add a separately reviewed exact host adapter before using another object store. Bodies are size-limited. This prevents arbitrary URL retrieval and hash substitution.

## Canonical bundle generation

Run `scripts/veltrix_v2/build_verified_public_bundle.py --report reports/{report_id}.json` only after the report-specific manifest exists and its GitHub attestation is available. The script:

1. Loads the deployment verifier.
2. Verifies report identity, report-bound manifest, attestation, certification metrics, rights and evidence hashes.
3. Builds all website, scheduled, Telegram and dashboard surfaces from one report identity.
4. Serializes and reparses the exact portable bytes.
5. Re-runs publication authorization against the parsed canonical report.
6. Writes `command-data/public-data/v2_report_bundle.json` immutably and verifies its persisted SHA-256.

A denial writes no bundle. Existing non-identical canonical bytes cause an immutable-conflict error.

## Current qualification boundary

A green code test is not evidence of market certification. No attestation, certification manifest or canonical public bundle may be fabricated to make the workflow green. The provider-rights document and underlying model evidence must be real, hash-checked and independently reviewable. A report that does not meet all market gates remains unpublished.
