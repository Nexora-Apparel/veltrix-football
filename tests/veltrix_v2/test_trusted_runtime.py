from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from unittest.mock import Mock

import pytest

from veltrix_v2.reporting.trusted_runtime import (
    DeploymentVerificationError,
    _verify_sigstore_bundle,
    build_github_attestation_verifier,
    build_hash_checked_evidence_reader,
    build_provider_rights_evaluator,
)


class Response:
    def __init__(self, status=200, content=b"", headers=None, payload=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}
        self._payload = payload

    def iter_content(self, chunk_size):
        yield self.content

    def json(self):
        return self._payload

    def close(self):
        pass


def test_evidence_reader_requires_exact_allowlisted_https_host_and_rejects_redirects():
    session = Mock()
    session.get.return_value = Response(302, headers={"Location": "https://evil.example/data"})
    reader = build_hash_checked_evidence_reader(
        allowed_hosts=frozenset({"evidence.example"}), session=session
    )
    with pytest.raises(DeploymentVerificationError, match="EVIDENCE_FETCH_FAILED"):
        reader("https://evidence.example/rights.json")
    assert session.get.call_args.kwargs["allow_redirects"] is False

    with pytest.raises(DeploymentVerificationError, match="EVIDENCE_URL_NOT_ALLOWLISTED"):
        reader("https://evil.example/rights.json")
    with pytest.raises(DeploymentVerificationError, match="EVIDENCE_URL_NOT_ALLOWLISTED"):
        reader("https://evidence.example/rights.json?token=secret")


def test_evidence_reader_enforces_body_size_limit():
    session = Mock()
    session.get.return_value = Response(
        200, b"x" * (8_000_000 + 1), {"Content-Length": str(8_000_001)}
    )
    reader = build_hash_checked_evidence_reader(
        allowed_hosts=frozenset({"evidence.example"}), session=session
    )
    with pytest.raises(DeploymentVerificationError, match="EVIDENCE_SIZE_INVALID"):
        reader("https://evidence.example/large.bin")


def _rights_record():
    return {
        "rights_approval_id": "approval-5dollar-2026-11",
        "provider_id": "5dollarfootballapi",
        "provider_scope": "historical-results-and-fixtures",
        "rights_evidence_uri": "https://evidence.example/rights.json",
    }


def _rights_bytes():
    now = datetime.now(timezone.utc)
    payload = {
        "schema": "VELTRIX_PROVIDER_RIGHTS_EVIDENCE_V1",
        "approval_id": "approval-5dollar-2026-11",
        "provider_id": "5dollarfootballapi",
        "permitted_scope": "historical-results-and-fixtures",
        "status": "APPROVED",
        "allowed_actions": ["PREDICTION_PUBLICATION"],
        "terms_version": "2026-11",
        "terms": {
            "status": "ACCEPTED",
            "version": "2026-11",
            "checked_at": (now - timedelta(hours=1)).isoformat(),
        },
        "entitlement": {
            "status": "ACTIVE",
            "checked_at": (now - timedelta(minutes=10)).isoformat(),
            "expires_at": (now + timedelta(days=2)).isoformat(),
            "quota": {"remaining": 12},
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def test_provider_rights_evaluator_checks_provider_scope_terms_entitlement_and_quota():
    raw = _rights_bytes()
    record = _rights_record()
    record["rights_evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    evaluator = build_provider_rights_evaluator(lambda uri: raw)
    assert evaluator(record) is True

    tampered = dict(record, provider_scope="all-data-redistribution")
    assert evaluator(tampered) is False
    tampered = dict(record, rights_approval_id="other-approval")
    assert evaluator(tampered) is False


@pytest.mark.parametrize("mutation", [
    lambda data: data["allowed_actions"].clear(),
    lambda data: data["entitlement"].update(status="EXPIRED"),
    lambda data: data["entitlement"]["quota"].update(remaining=0),
    lambda data: data["terms"].update(status="NOT_ACCEPTED"),
])
def test_provider_rights_evaluator_denies_missing_or_invalid_permission(mutation):
    raw = json.loads(_rights_bytes())
    mutation(raw)
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    record = _rights_record()
    record["rights_evidence_sha256"] = hashlib.sha256(payload).hexdigest()
    assert build_provider_rights_evaluator(lambda uri: payload)(record) is False


def test_sigstore_verifier_uses_runtime_python_module_and_pinned_workflow_identity(monkeypatch):
    calls = []
    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Mock(returncode=0)
    monkeypatch.setattr("veltrix_v2.reporting.trusted_runtime.subprocess.run", fake_run)
    digest = hashlib.sha256(b"manifest").hexdigest()
    assert _verify_sigstore_bundle(
        artifact_sha256=digest,
        bundle_bytes=b'{"mediaType":"sigstore"}',
        workflow_identity=(
            "https://github.com/Nexora-Apparel/veltrix-football/"
            ".github/workflows/report-certification-attestation.yml@refs/heads/main"
        ),
    ) is True
    command, kwargs = calls[0]
    assert command[:4] == [command[0], "-m", "sigstore", "verify"]
    assert "sha256:" + digest in command
    assert "--repository" in command and "Nexora-Apparel/veltrix-football" in command
    assert "--ref" in command and "refs/heads/main" in command
    assert "--cert-identity" in command and workflow_identity in command
    assert kwargs["timeout"] == 90


def test_attestation_lookup_uses_exact_digest_and_rejects_untrusted_bundle_hosts(monkeypatch):
    session = Mock()
    session.get.side_effect = [
        Response(payload={"attestations": [
            {"bundle_url": "https://evil.example/forged.json"},
        ]}),
    ]
    verifier = build_github_attestation_verifier(token="test-token", session=session)
    manifest = b"bound report manifest"
    digest = hashlib.sha256(manifest).hexdigest()
    assert verifier(manifest, digest) is False
    assert digest in session.get.call_args.args[0]
    assert session.get.call_args.kwargs["allow_redirects"] is False


def test_attestation_verifier_rejects_manifest_digest_mismatch():
    session = Mock()
    verifier = build_github_attestation_verifier(token="test-token", session=session)
    assert verifier(b"manifest", "0" * 64) is False
    session.get.assert_not_called()


def test_deployment_factory_requires_attestation_credentials_and_host_allowlist():
    from veltrix_v2.reporting.trusted_runtime import build_deployment_publication_verifier
    with pytest.raises(DeploymentVerificationError, match="GITHUB_ATTESTATION_READ_TOKEN_REQUIRED"):
        build_deployment_publication_verifier({})
    with pytest.raises(DeploymentVerificationError, match="EVIDENCE_HOST_ALLOWLIST_REQUIRED"):
        build_deployment_publication_verifier({"GH_TOKEN": "token"})
