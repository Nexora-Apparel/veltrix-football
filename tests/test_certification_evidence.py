import hashlib
import json
from types import SimpleNamespace

import pytest

from app.certification_evidence import EvidenceIntegrityError, verify_evidence_manifest, verify_github_artifact_attestation


ROLES = (
    "walk_forward_rows", "coverage_audit", "prospective_ledger",
    "odds_snapshots", "settlement_records", "model_manifest",
)


def _bundle(tmp_path):
    artifacts = []
    for role in ROLES:
        path = tmp_path / f"{role}.json"
        path.write_text(json.dumps({"role": role}), encoding="utf-8")
        artifacts.append({
            "role": role,
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "purpose": "VELTRIX_VALUE_CERTIFICATION",
        "artifacts": artifacts,
    }), encoding="utf-8")
    return manifest, artifacts


def test_manifest_verifies_exact_artifact_bytes_but_never_authorizes_release(tmp_path):
    manifest, _ = _bundle(tmp_path)
    result = verify_evidence_manifest(manifest)
    assert result["integrity_status"] == "BYTE_INTEGRITY_VERIFIED"
    assert result["release_authorized"] is False
    assert len(result["verified_artifacts"]) == len(ROLES)


def test_manifest_rejects_altered_artifact_bytes(tmp_path):
    manifest, _ = _bundle(tmp_path)
    (tmp_path / "prospective_ledger.json").write_text('{"settled_bets": 999999}', encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="SHA-256 mismatch"):
        verify_evidence_manifest(manifest)


def test_manifest_rejects_missing_required_role(tmp_path):
    manifest, artifacts = _bundle(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"] = [a for a in payload["artifacts"] if a["role"] != "odds_snapshots"]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="Missing required"):
        verify_evidence_manifest(manifest)


def test_manifest_rejects_path_traversal(tmp_path):
    manifest, _ = _bundle(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"][0]["path"] = "../outside.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="Unsafe artifact path"):
        verify_evidence_manifest(manifest)


def test_manifest_rejects_duplicate_roles(tmp_path):
    manifest, _ = _bundle(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"].append(dict(payload["artifacts"][0], path="duplicate.json"))
    (tmp_path / "duplicate.json").write_text("{}", encoding="utf-8")
    payload["artifacts"][-1]["sha256"] = hashlib.sha256(b"{}").hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="unique"):
        verify_evidence_manifest(manifest)



def test_manifest_rejects_unrecognized_artifact_role(tmp_path):
    manifest, _ = _bundle(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["artifacts"][0]["role"] = "caller_supplied_summary"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="recognized"):
        verify_evidence_manifest(manifest)



def test_github_attestation_requires_pinned_signer_and_exact_manifest_digest(monkeypatch, tmp_path):
    import app.certification_evidence as evidence

    artifact = tmp_path / "manifest.json"
    artifact.write_text('{"evidence": "immutable"}', encoding="utf-8")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    payload = [{
        "verificationResult": {
            "statement": {
                "predicateType": "https://slsa.dev/provenance/v1",
                "subject": [{"digest": {"sha256": digest}}],
            },
            "verifiedTimestamps": [{"timestamp": "2026-11-12T00:00:00Z"}],
            "signature": {"certificate": {"subjectAlternativeName": "trusted-workflow"}},
        }
    }]
    captured = {}
    monkeypatch.setattr(evidence.shutil, "which", lambda name: "/usr/bin/gh")
    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
    monkeypatch.setattr(evidence.subprocess, "run", fake_run)

    result = verify_github_artifact_attestation(artifact, token="test-token")
    assert result["attestation_status"] == "GITHUB_ATTESTATION_VERIFIED"
    assert result["sha256"] == digest
    assert "--signer-workflow" in captured["command"]
    assert "Nexora-Apparel/veltrix-football/.github/workflows/certification-evidence-attestation.yml" in captured["command"]
    assert "--source-ref" in captured["command"]
    assert captured["env"]["GH_TOKEN"] == "test-token"


def test_github_attestation_rejects_wrong_manifest_digest(monkeypatch, tmp_path):
    import app.certification_evidence as evidence

    artifact = tmp_path / "manifest.json"
    artifact.write_text('{"evidence": "immutable"}', encoding="utf-8")
    payload = [{
        "verificationResult": {
            "statement": {
                "predicateType": "https://slsa.dev/provenance/v1",
                "subject": [{"digest": {"sha256": "0" * 64}}],
            },
            "verifiedTimestamps": [{"timestamp": "2026-11-12T00:00:00Z"}],
            "signature": {"certificate": {"subjectAlternativeName": "trusted-workflow"}},
        }
    }]
    monkeypatch.setattr(evidence.shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        evidence.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )
    with pytest.raises(EvidenceIntegrityError, match="exact evidence manifest digest"):
        verify_github_artifact_attestation(artifact, token="test-token")
