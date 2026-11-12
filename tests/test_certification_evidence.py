import hashlib
import json

import pytest

from app.certification_evidence import EvidenceIntegrityError, verify_evidence_manifest


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
