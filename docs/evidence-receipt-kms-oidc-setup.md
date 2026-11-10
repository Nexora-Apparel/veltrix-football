# Receipt-signing KMS and GitHub OIDC setup

This runbook provisions the signing trust anchor for archive receipt schema v2. It does not create the S3 bucket, configure the GitHub Environment, or dispatch acquisition. Use a dedicated AWS account/region approved for evidence retention. Replace every placeholder locally; never commit account IDs, role ARNs, key ARNs, credentials, or private material.

## 1. Create the asymmetric signing key

Create a dedicated KMS asymmetric key with:
- Key spec: ECC_NIST_P256
- Key usage: SIGN_VERIFY
- Origin: AWS_KMS
- Region: the region configured in VELTRIX_EVIDENCE_RECEIPT_KMS_REGION

Example (run from an authorized administrator workstation):

```sh
aws kms create-key \
  --description "VELTRIX Football evidence archive receipt signing" \
  --key-spec ECC_NIST_P256 \
  --key-usage SIGN_VERIFY \
  --origin AWS_KMS \
  --region <AWS_REGION>
```

Record the returned KeyId and ARN in the approved secrets/configuration vault. The runtime must use the full key ARN, not an alias. Do not export private key material; KMS retains it.

## 2. Create the GitHub OIDC role trust policy

Ensure the AWS account has the GitHub Actions OIDC provider for `https://token.actions.githubusercontent.com`, with audience `sts.amazonaws.com`. If it does not exist, an AWS administrator must register it before role creation.

Trust policy template (replace AWS_ACCOUNT_ID):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubVeltrixHistoricalAcquisitionEnvironmentOnly",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:Nexora-Apparel/veltrix-football:environment:historical-acquisition"
        }
      }
    }
  ]
}
```

The subject condition deliberately binds the role to the named GitHub Environment. Do not broaden it to all branches, pull requests, or the whole repository. The workflow job must retain its main-branch guard and protected environment.

## 3. Restrict the role permissions

Attach only this permission policy to the OIDC role (replace REGION, AWS_ACCOUNT_ID and KEY_ID):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SignAndVerifyVeltrixEvidenceReceiptsOnly",
      "Effect": "Allow",
      "Action": [
        "kms:Sign",
        "kms:Verify"
      ],
      "Resource": "arn:aws:kms:<REGION>:<AWS_ACCOUNT_ID>:key/<KEY_ID>"
    }
  ]
}
```

Do not grant this role KMS administration, key deletion, key policy changes, S3 access, IAM administration, or unrelated AWS actions. The S3-compatible archive credentials remain separate environment secrets and are not passed to KMS.

The KMS key policy must also permit this role to use Sign and Verify. Keep key administration limited to a separate administrator identity. Do not let the workflow role administer its own trust anchor.

## 4. Configure GitHub Environment variables

In repository Settings → Environments → historical-acquisition, configure these non-secret variables:

| Variable | Value |
|---|---|
| VELTRIX_EVIDENCE_RECEIPT_KMS_KEY_ARN | Full KMS key ARN |
| VELTRIX_EVIDENCE_RECEIPT_KMS_REGION | KMS key region |
| VELTRIX_EVIDENCE_RECEIPT_KMS_ROLE_ARN | OIDC role ARN |

Keep required reviewers enabled and deployment branches restricted to main. The workflow requests the OIDC token only for the protected environment job. The pinned configure-aws-credentials action assumes the role and supplies short-lived AWS credentials to boto3.

## 5. Validate without provider acquisition

Before any real historical acquisition:
1. Confirm the key is enabled, asymmetric, ECC_NIST_P256, and SIGN_VERIFY.
2. Confirm the role trust policy's exact audience and environment subject.
3. Confirm the role can call Sign and Verify only on the dedicated key.
4. Run a synthetic canonical-receipt sign/verify test using the real KMS key and the same KMS API parameters as the application: ECDSA_SHA_256 with MessageType DIGEST and a SHA-256 digest.
5. Verify a changed receipt fails signature verification.
6. Confirm an untrusted key ARN, disabled key, wrong region, missing OIDC permission, or denied KMS action fails closed.
7. Independently verify the KMS CloudTrail events and role session identity.

The repository CI uses a fake KMS implementation and does not validate AWS IAM, OIDC, key policy, CloudTrail, or real KMS cryptography.

## 6. Key rotation and retained receipts

Asymmetric KMS signing keys are not rotated by symmetric-key automatic rotation. For rotation, create a new dedicated signing key and update the trusted-key configuration only through a reviewed change. Retained receipts signed by the old key still require verification against that old key. Do not disable or schedule deletion of an old signing key while receipts signed by it remain within retention.

The current restore CLI trusts one exact KMS key ARN. Therefore, do not rotate the configured ARN while retained v2 receipts signed by the old key still need restore. Before the first rotation, implement and test an explicit allowlisted key registry mapping receipt key ARN to KMS region; never trust arbitrary key ARNs supplied by receipts.

## Security boundary

A valid signature proves that the canonical receipt payload was signed by the configured KMS key and has not changed since signing. It does not prove that the source data is true, that a human approved the acquisition, or that the workflow operator is non-repudiably identified. Keep reviewer approval, GitHub audit logs, AWS CloudTrail, storage versioning, and object-retention controls as separate controls.
