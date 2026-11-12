"""Verify byte-level integrity and trusted GitHub provenance for VELTRIX evidence.

Manifest hashes and Sigstore attestations establish artifact identity and signer
provenance. Raw-row recomputation and source-rights checks remain separate
mandatory gates; this module never issues a release certificate.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST_SCHEMA_VERSION = 1
REQUIRED_ROLES = {
    "walk_forward_rows",
    "coverage_audit",
    "prospective_ledger",
    "odds_snapshots",
    "settlement_records",
    "source_responses",
    "model_manifest",
}


class EvidenceIntegrityError(ValueError):
    """Raised when an evidence bundle is incomplete or its bytes do not match."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_evidence_manifest(manifest_path: str | Path) -> dict[str, Any]:
    """Verify a manifest and every referenced artifact without trusting summaries.

    Artifact paths are relative to the manifest directory. Absolute paths,
    traversal, symlinks, duplicate roles, duplicate paths and malformed hashes
    are rejected. A successful result means only that the listed bytes match
    their declared hashes; it is not a market certification.
    """
    manifest_file = Path(manifest_path).resolve(strict=True)
    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceIntegrityError("Manifest is unreadable or invalid JSON.") from exc

    if not isinstance(manifest, dict) or manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise EvidenceIntegrityError("Unsupported evidence manifest schema.")
    if manifest.get("purpose") != "VELTRIX_VALUE_CERTIFICATION":
        raise EvidenceIntegrityError("Manifest purpose is not value certification.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise EvidenceIntegrityError("Manifest artifacts must be a list.")

    seen_roles: set[str] = set()
    seen_paths: set[str] = set()
    verified: list[dict[str, Any]] = []
    root = manifest_file.parent

    for item in artifacts:
        if not isinstance(item, dict):
            raise EvidenceIntegrityError("Every artifact entry must be an object.")
        role, relative = item.get("role"), item.get("path")
        expected = item.get("sha256")
        if not isinstance(role, str) or role not in REQUIRED_ROLES or role in seen_roles:
            raise EvidenceIntegrityError("Artifact roles must be recognized, non-empty and unique.")
        if not isinstance(relative, str) or not relative:
            raise EvidenceIntegrityError(f"Artifact path missing for role {role}.")
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
            raise EvidenceIntegrityError(f"Unsafe artifact path for role {role}.")
        if relative in seen_paths:
            raise EvidenceIntegrityError("Artifact paths must be unique.")
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise EvidenceIntegrityError(f"Invalid SHA-256 for role {role}.")

        candidate = root.joinpath(*pure.parts)
        cursor = root
        for part in pure.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise EvidenceIntegrityError(f"Symlink artifact paths are forbidden: {role}.")
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError) as exc:
            raise EvidenceIntegrityError(f"Artifact missing or outside manifest root: {role}.") from exc
        if not resolved.is_file():
            raise EvidenceIntegrityError(f"Artifact is not a regular file: {role}.")
        actual = sha256_file(resolved)
        if actual != expected:
            raise EvidenceIntegrityError(f"SHA-256 mismatch for role {role}.")

        seen_roles.add(role)
        seen_paths.add(relative)
        verified.append({"role": role, "path": relative, "sha256": actual, "bytes": resolved.stat().st_size})

    missing = sorted(REQUIRED_ROLES - seen_roles)
    if missing:
        raise EvidenceIntegrityError("Missing required evidence roles: " + ", ".join(missing))
    if seen_roles != REQUIRED_ROLES:
        raise EvidenceIntegrityError("Evidence manifest must contain exactly the required artifact roles.")

    return {
        "integrity_status": "BYTE_INTEGRITY_VERIFIED",
        "release_authorized": False,
        "verified_artifacts": verified,
        "missing_raw_recomputation_gates": [
            "walk-forward metrics recomputed from fixture-level rows",
            "prospective ROI and date-clustered confidence interval recomputed from settled selections",
            "timestamped odds coverage recomputed from quote-level snapshots",
            "point-in-time feature and settlement provenance verified",
            "model and calibration version consistency verified",
            "same-fixture full and recent-holdout bookmaker benchmark recomputed",
        ],
        "note": "Byte integrity is necessary but not sufficient for certification.",
    }



def verify_github_artifact_attestation(
    artifact_path: str | Path,
    *,
    repository: str = "Nexora-Apparel/veltrix-football",
    signer_workflow: str = "Nexora-Apparel/veltrix-football/.github/workflows/certification-evidence-attestation.yml",
    token: str | None = None,
) -> dict[str, Any]:
    """Verify a GitHub/Sigstore SLSA attestation from the pinned main-branch workflow.

    The GitHub CLI verifies the cryptographic signature, OIDC issuer, repository
    identity, signer workflow and source ref. The returned subject digest is
    additionally matched to the exact local manifest bytes.
    """
    path = Path(artifact_path).resolve(strict=True)
    gh = shutil.which("gh")
    if not gh:
        raise EvidenceIntegrityError("GitHub CLI is required to verify signed artifact attestations.")
    env = os.environ.copy()
    credential = token or env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if not credential:
        raise EvidenceIntegrityError("GH_TOKEN/GITHUB_TOKEN is required for online attestation verification.")
    env["GH_TOKEN"] = credential
    command = [
        gh, "attestation", "verify", str(path),
        "--repo", repository,
        "--signer-repo", repository,
        "--signer-workflow", signer_workflow,
        "--source-ref", "refs/heads/main",
        "--deny-self-hosted-runners",
        "--predicate-type", "https://slsa.dev/provenance/v1",
        "--format", "json",
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=90, check=False, env=env
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceIntegrityError("GitHub artifact attestation verification could not run.") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "no verifier detail").strip()
        raise EvidenceIntegrityError("GitHub artifact attestation verification failed: " + detail[:500])
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceIntegrityError("GitHub attestation verifier returned invalid JSON.") from exc
    if not isinstance(payload, list):
        raise EvidenceIntegrityError("GitHub attestation verifier returned an unexpected result.")
    expected_digest = sha256_file(path)
    for item in payload:
        if not isinstance(item, dict):
            continue
        verification = item.get("verificationResult") or {}
        statement = verification.get("statement") or {}
        if statement.get("predicateType") != "https://slsa.dev/provenance/v1":
            continue
        subjects = statement.get("subject") or []
        digest_matches = any(
            isinstance(subject, dict)
            and str(((subject.get("digest") or {}).get("sha256") or "")).lower() == expected_digest
            for subject in subjects
        )
        timestamps = verification.get("verifiedTimestamps") or []
        certificate = ((verification.get("signature") or {}).get("certificate") or {})
        if digest_matches and timestamps and certificate:
            return {
                "attestation_status": "GITHUB_ATTESTATION_VERIFIED",
                "sha256": expected_digest,
                "repository": repository,
                "signer_workflow": signer_workflow,
                "source_ref": "refs/heads/main",
                "verified_timestamp_count": len(timestamps),
            }
    raise EvidenceIntegrityError("No verified attestation matched the exact evidence manifest digest.")
