# Raw provider evidence retention and key operations

## Current boundary

The acquisition workflow emits three files only:
- Sanitized, hash-verified acquisition report.
- AES-256-GCM encrypted raw-source sidecar.
- Non-sensitive sidecar manifest containing report digest, run/window binding, ciphertext digest and evidence count.

GitHub Actions artifacts are currently retained for 14 days. They are a transport/debugging layer, not the canonical evidence archive. Historical acquisition MUST remain undispatched until durable private retention is provisioned and its restore path is tested.

## Canonical archive target

Use a private object-storage bucket with:
- Public access blocked; no public listing or object URLs.
- Object versioning enabled.
- Server-side encryption enabled in addition to application-level AES-256-GCM.
- Object lock/retention where supported, with an explicit retention period and legal/terms review.
- Access limited to the acquisition workflow identity and designated evidence-review identity.
- No raw provider payload in logs, Git commits, PR diffs, public reports, Telegram, or website responses.

Canonical object key:
`veltrix-football/evidence/v1/{provider}/{competition_key}/{YYYY}/{MM}/{run_id}/{source_id}.json.enc`

The encrypted sidecar may initially be stored as one batch object, with its manifest stored beside it. If split into per-record objects later, preserve the same authenticated batch binding and record coverage manifest.

## Upload protocol (must be implemented before dispatch)

1. Validate the sanitized report and recompute its digest.
2. Decrypt the sidecar in a restricted verification step; validate every raw payload and normalized-record digest and exact record coverage.
3. Upload ciphertext and manifest to the private bucket using a unique immutable object key.
4. Read back the uploaded object and compare its SHA-256 with the manifest.
5. Record object URI, version ID, byte length, digest, run ID, report digest, evidence count and retention expiry in a separate sanitized archive receipt.
6. Mark archive status complete only after read-back verification succeeds.
7. Upload the sanitized report, encrypted sidecar and receipt to the short-lived GitHub artifact for traceability.

No import into Neon, model training, canonical merge, prediction publication or Telegram delivery is part of this process.

## Key management

Required repository secret:
`VELTRIX_RAW_EVIDENCE_ENCRYPTION_KEY`

Generate a fresh 32-byte key and base64-encode it locally:
```sh
python -c "import base64,secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Add the output as the GitHub Actions secret. Never commit it, paste it into chat, include it in logs, or reuse provider/API/signing credentials. Keep a separately controlled recovery copy in an approved password manager or secrets vault. If the key is lost, encrypted evidence is unrecoverable.

Key rotation must be versioned. New evidence uses a new key; old keys remain available only to the restricted decryption identity for the required retention period. Re-encryption, if required, must preserve original ciphertext digest and record a new derivative object with an auditable parent reference. Do not overwrite evidence objects.

## Release gates

- [ ] Repository secret exists and has been tested using a synthetic payload only.
- [ ] Private object storage is provisioned with public access blocked.
- [ ] Workflow upload identity is scoped to the target bucket/prefix only.
- [ ] Upload, read-back digest verification and archive receipt are implemented.
- [ ] Restore/decrypt test succeeds from the canonical archive, not the Actions artifact.
- [ ] Retention duration and deletion procedure are approved.
- [ ] Terms and public attribution requirements remain satisfied.

Until every gate above is verified, the manual historical acquisition workflow must not be dispatched.
