# Raw provider evidence retention and key operations

## Data boundary

Each acquisition run produces:
- A sanitized, hash-verified report. Raw provider rows are never serialized into it.
- An AES-256-GCM encrypted sidecar covering every input observation, including accepted and quarantined rows.
- A plaintext-safe manifest binding the sidecar to the report digest, run ID, date window, ciphertext digest, and accepted/quarantined/total counts.
- A sanitized archive receipt written only after private object upload and read-back verification.

Quarantine is an evidence-retention outcome, not an acceptance outcome. A rejected batch may be archived so its original source observations remain auditable. The workflow then fails its final acceptance gate. Such a batch is never eligible for import, canonical merge, training, prediction publication, or Telegram delivery.

GitHub Actions artifacts are a short-lived traceability layer, not the canonical archive. They contain only the sanitized report, manifest, and receipt; the encrypted sidecar is kept in private object storage.

## Workflow dispatch trust boundary

The acquisition workflow must run only from the repository default branch (`main`). GitHub allows `workflow_dispatch` to target a selected branch; a branch-level dispatch guard is therefore required so an unreviewed feature branch cannot execute a workflow with provider, encryption, or archive credentials. The acquisition implementation itself is checked out by immutable commit SHA. Do not remove the default-branch guard or replace the pinned implementation with an unreviewed branch reference.

The job also targets the protected GitHub Environment `historical-acquisition`. Before merging or dispatching, configure that environment with required reviewer approval and deployment-branch restrictions allowing only `main`. Store the acquisition-only secrets in that environment under these exact names: `VELTRIX_HISTORICAL_FIVEDOLLAR_API_KEY`, `VELTRIX_HISTORICAL_QUALIFICATION_ATTESTATION_KEY`, `VELTRIX_HISTORICAL_RAW_EVIDENCE_ENCRYPTION_KEY`, `VELTRIX_HISTORICAL_ARCHIVE_ENDPOINT_URL`, `VELTRIX_HISTORICAL_ARCHIVE_BUCKET`, `VELTRIX_HISTORICAL_ARCHIVE_ACCESS_KEY_ID`, and `VELTRIX_HISTORICAL_ARCHIVE_SECRET_ACCESS_KEY`. The workflow maps those environment secrets to the runtime variable names expected by the scripts. Do not copy these credentials into repository-level secrets.

## Canonical private archive

The archive endpoint must use HTTPS and must not embed access credentials in its URL. Both archive and restore clients reject plaintext HTTP, non-HTTPS schemes, and user-info credentials before creating the S3 client.

Use a private S3-compatible bucket with:
- Public access blocked; no public listing or object URLs.
- Object versioning enabled.
- Server-side encryption enabled in addition to application-level AES-256-GCM.
- Object lock/retention where supported, with an explicit retention period and legal/terms review.
- Access limited to the acquisition workflow identity and designated evidence-review identity.
- No raw provider payload in logs, Git commits, PR diffs, public reports, Telegram, or website responses.

For run ID `{run_id}` under prefix `veltrix-football/evidence/v1`, the archive writes:
- `reports/{run_id}.json`
- `encrypted/{run_id}.enc`
- `manifests/{run_id}.json`
- `receipts/{run_id}.json`

The receipt is the commit marker. It is written only after all three data objects have been uploaded and read back with matching SHA-256 digests. Retries may reuse existing objects only when the downloaded bytes match the expected digest; conflicting objects fail closed.

**Receipt trust limitation:** the receipt is not independently digitally signed in this version. Its `readback_verified` assertion is trusted only because the archive writer runs under the protected `historical-acquisition` environment and the bucket write identity is tightly scoped. SHA-256 checks detect object-byte changes, and AES-256-GCM authenticates encrypted evidence, but those controls do not independently establish the identity of the actor who wrote the receipt. Do not describe this as non-repudiable chain-of-custody. If that assurance is required, add a separately governed signing identity (for example, a KMS-backed signature) and verify it during restore.

## Upload and restore protocol

1. Validate the sanitized report structure, digest, five-competition scope, date window, and request accounting.
2. Build an encrypted evidence entry for each input index. Accepted entries bind raw payloads to normalized records; quarantined entries bind raw payloads to the quarantine reason and sanitized source summary.
3. Verify the sidecar cryptographically against the report and manifest.
4. Upload report, encrypted sidecar, and manifest to the private bucket.
5. Read back every object and compare byte length and SHA-256.
6. Write the receipt last, then read it back. A receipt is not emitted before the archive commit marker is verified.
7. Restore with `scripts/restore_encrypted_source_evidence.py --run-id RUN_ID`. The restore command verifies the receipt inventory, exact object keys, object lengths and digests, report/manifest binding, AES-GCM authentication, and full accepted/quarantined input coverage before publishing any local output. It stages all three verified files in a temporary sibling directory and publishes the complete restore with a same-filesystem directory rename; an existing destination is rejected rather than merged or overwritten.

The archive and restore scripts are covered by secret-free fake-object-storage tests. Those tests do not substitute for a real provider provisioning and restore test.

## Key management

Required repository secret:
`VELTRIX_RAW_EVIDENCE_ENCRYPTION_KEY`

Generate a fresh 32-byte key and base64-encode it locally:
```sh
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Add the output as a GitHub Actions secret. Never commit it, paste it into chat, include it in logs, or reuse provider/API/signing credentials. Keep a separately controlled recovery copy in an approved password manager or secrets vault. If the key is lost, encrypted evidence is unrecoverable.

Key rotation must be versioned. New evidence uses a new key; old keys remain available only to the restricted decryption identity for the required retention period. Re-encryption, if required, must preserve original ciphertext digest and record a new derivative object with an auditable parent reference. Do not overwrite evidence objects.

## Release gates

- [ ] Repository encryption key and archive credentials are configured and tested using synthetic data only.
- [ ] Private object storage is provisioned with public access blocked.
- [ ] Workflow upload identity is scoped to the target bucket/prefix only.
- [ ] Bucket versioning, server-side encryption, retention, and recovery access are verified.
- [ ] A real upload/read-back/restore/decrypt test succeeds from canonical storage, not from a GitHub artifact.
- [ ] Retention duration and deletion procedure are approved.
- [ ] Terms and public attribution requirements remain satisfied.
- [ ] Historical batch acceptance gates are met independently of evidence archival.

Until every gate above is verified, the manual historical acquisition workflow must not be dispatched. A successful CI run proves only the synthetic test suite; it does not prove real storage provisioning or authorize acquisition.
