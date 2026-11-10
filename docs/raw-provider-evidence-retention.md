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

The job also targets the protected GitHub Environment `historical-acquisition`. Before merging or dispatching, configure that environment with required reviewer approval and deployment-branch restrictions allowing only `main`. Store the acquisition-only secrets in that environment under these exact names: `VELTRIX_HISTORICAL_FIVEDOLLAR_API_KEY`, `VELTRIX_HISTORICAL_QUALIFICATION_ATTESTATION_KEY`, `VELTRIX_HISTORICAL_RAW_EVIDENCE_ENCRYPTION_KEY`, `VELTRIX_HISTORICAL_ARCHIVE_ENDPOINT_URL`, `VELTRIX_HISTORICAL_ARCHIVE_BUCKET`, `VELTRIX_HISTORICAL_ARCHIVE_ACCESS_KEY_ID`, and `VELTRIX_HISTORICAL_ARCHIVE_SECRET_ACCESS_KEY`. The workflow maps those environment secrets to the runtime variable names expected by the scripts. Do not copy these credentials into repository-level secrets. The receipt-signing KMS key ARN, KMS region, KMS role ARN and trusted-key registry are non-secret GitHub Environment variables: `VELTRIX_EVIDENCE_RECEIPT_KMS_KEY_ARN`, `VELTRIX_EVIDENCE_RECEIPT_KMS_REGION`, `VELTRIX_EVIDENCE_RECEIPT_KMS_ROLE_ARN`, and `VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON`. The registry is an explicit JSON object mapping every trusted full key ARN to its region; receipt contents cannot extend this allowlist.

## Canonical private archive

The archive endpoint must use HTTPS and must not embed access credentials in its URL. Both archive and restore clients reject plaintext HTTP, non-HTTPS schemes, and user-info credentials before creating the S3 client.

Use a private S3-compatible bucket with:
- Public access blocked; no public listing or object URLs.
- Object versioning enabled.
- Server-side encryption enabled in addition to application-level AES-256-GCM.
- Object lock/retention where supported, with an explicit retention period and legal/terms review.
- Access limited to the acquisition workflow identity and designated evidence-review identity.
- No raw provider payload in logs, Git commits, PR diffs, public reports, Telegram, or website responses.

For run ID `{run_id}` under prefix `veltrix-football/evidence/v2`, the archive writes:
- `reports/{run_id}.json`
- `encrypted/{run_id}.enc`
- `manifests/{run_id}.json`
- `receipts/{run_id}.json`

The receipt is the commit marker. It is written only after all three data objects have been uploaded and read back with matching SHA-256 digests. Retries may reuse existing objects only when the downloaded bytes match the expected digest; conflicting objects fail closed.

**Receipt authenticity:** receipts use schema `veltrix-evidence-archive-receipt-v2`. The canonical receipt payload (all receipt fields except the signature envelope) is SHA-256 hashed and signed with AWS KMS `ECDSA_SHA_256` using an asymmetric `ECC_NIST_P256` key configured for `SIGN_VERIFY`. The signature envelope records the algorithm, digest message type, exact KMS key ARN and base64 signature. Restore verifies the signature with a KMS client selected only from the out-of-band ARN-to-region allowlist before it trusts the receipt inventory or downloads archive objects. Unknown receipt key ARNs are rejected before any KMS call. The current signing key must also be present in the registry. A v1 unsigned receipt is rejected by the v2 restore path; no silent downgrade is allowed. The signing key is independent of the AES-256-GCM encryption key. The workflow obtains short-lived KMS credentials through GitHub OIDC using a role whose trust policy is restricted to this repository's `historical-acquisition` environment. Grant `kms:Sign` only on the current signing key and `kms:Verify` only on the exact keys in the trusted registry. During rotation, old keys remain Verify-only; do not grant Sign on retired keys. Do not grant it KMS key administration, S3 access or unrelated AWS permissions. This establishes receipt authenticity relative to the configured KMS trust anchor, but does not prove a human authorized the acquisition or provide a non-repudiable identity for the workflow operator.

## Upload and restore protocol

1. Validate the sanitized report structure, digest, five-competition scope, date window, and request accounting.
2. Build an encrypted evidence entry for each input index. Accepted entries bind raw payloads to normalized records; quarantined entries bind raw payloads to the quarantine reason and sanitized source summary.
3. Verify the sidecar cryptographically against the report and manifest.
4. Upload report, encrypted sidecar, and manifest to the private bucket.
5. Read back every object and compare byte length and SHA-256.
6. Write the receipt last, then read it back. A receipt is not emitted before the archive commit marker is verified.
7. Restore with `scripts/restore_encrypted_source_evidence.py --run-id RUN_ID`. The restore command first verifies the v2 receipt signature against the configured trusted-key registry. The single-key ARN/region variables remain a compatibility fallback when no registry is configured. Only then does it verify the receipt inventory, exact object keys, object lengths and digests, report/manifest binding, AES-GCM authentication, and full accepted/quarantined input coverage before publishing any local output. It stages all three verified files in a temporary sibling directory and publishes the complete restore with a same-filesystem directory rename; an existing destination is rejected rather than merged or overwritten.

The archive and restore scripts are covered by secret-free fake-object-storage and fake-KMS tests. Those tests validate the signing contract and tamper rejection but do not substitute for a real KMS key, IAM/OIDC trust policy, private bucket, or provider provisioning and restore test.

## Key management

Required GitHub Environment secret:
`VELTRIX_HISTORICAL_RAW_EVIDENCE_ENCRYPTION_KEY` (mapped to `VELTRIX_RAW_EVIDENCE_ENCRYPTION_KEY` at runtime).

Generate a fresh 32-byte key and base64-encode it locally:
```sh
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Add the output as a GitHub Actions secret. Never commit it, paste it into chat, include it in logs, or reuse provider/API/signing credentials. Keep a separately controlled recovery copy in an approved password manager or secrets vault. If the key is lost, encrypted evidence is unrecoverable.

Receipt signing key: create a dedicated asymmetric KMS key with key spec `ECC_NIST_P256` and key usage `SIGN_VERIFY`. Record its exact key ARN and region in the GitHub Environment variables listed above. Configure `VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON` as a JSON object mapping all retained signing key ARNs to their exact AWS regions. Configure the KMS role trust policy for GitHub's OIDC provider with audience `sts.amazonaws.com` and subject `repo:Nexora-Apparel/veltrix-football:environment:historical-acquisition`. Restrict `kms:Sign` to the current key and `kms:Verify` to the explicit registry keys only. The acquisition workflow pins `aws-actions/configure-aws-credentials` to a full commit SHA and requests only the OIDC token needed to assume this role. Restore operators must independently obtain a role/session authorized for `kms:Verify` and configure the same trusted key ARN; never accept a key ARN supplied only by the untrusted receipt.

Key rotation must be versioned. New evidence uses a new encryption key; old keys remain available only to the restricted decryption identity for the required retention period. Receipt signing key rotation uses the explicit `VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON` registry. Add the new key while retaining the old key, grant Verify on both and Sign only on the new current key. Do not silently replace the registry, disable the old key before retention expires, or re-sign old receipts. Re-encryption, if required, must preserve original ciphertext digest and record a new derivative object with an auditable parent reference. Do not overwrite evidence objects.

## Release gates

- [ ] Environment encryption key and archive credentials are configured and tested using synthetic data only.
- [ ] Dedicated KMS `ECC_NIST_P256` signing key and restricted OIDC role are provisioned; key policy and OIDC trust subject are independently verified.
- [ ] Private object storage is provisioned with public access blocked.
- [ ] Workflow upload identity is scoped to the target bucket/prefix only.
- [ ] KMS role is scoped to `kms:Sign` on the current key and `kms:Verify` on only the explicit trusted-key registry entries.
- [ ] Bucket versioning, server-side encryption, retention, and recovery access are verified.
- [ ] A real upload/read-back/restore/decrypt test succeeds from canonical storage, not from a GitHub artifact.
- [ ] Retention duration and deletion procedure are approved.
- [ ] Terms and public attribution requirements remain satisfied.
- [ ] Historical batch acceptance gates are met independently of evidence archival.

Until every gate above is verified, the manual historical acquisition workflow must not be dispatched. A successful CI run proves only the synthetic test suite; it does not prove real storage provisioning or authorize acquisition.
