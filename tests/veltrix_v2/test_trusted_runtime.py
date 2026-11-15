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

    raw_reader = build_hash_checked_evidence_reader(
        allowed_hosts=frozenset({"raw.githubusercontent.com"}), session=session
    )
    with pytest.raises(DeploymentVerificationError, match="EVIDENCE_URL_NOT_ALLOWLISTED"):
        raw_reader("https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/main/../other/repo/file.json")
    with pytest.raises(DeploymentVerificationError, match="EVIDENCE_URL_NOT_ALLOWLISTED"):
        raw_reader("https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/main/%2e%2e/other.json")


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
        "rights_evaluated_at": None,
    }


def _rights_bytes():
    now = datetime.now(timezone.utc)
    payload = {
        "schema": "VELTRIX_PROVIDER_RIGHTS_EVIDENCE_V1",
        "evaluated_at": now.isoformat(),
        "approval_id": "approval-5dollar-2026-11",
        "provider_id": "5dollarfootballapi",
        "permitted_scope": "historical-results-and-fixtures",
        "status": "APPROVED",
        "allowed_actions": ["MODEL_TRAINING", "PUBLIC_DISPLAY"],
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
    record["rights_evaluated_at"] = json.loads(raw)["evaluated_at"]
    evaluator = build_provider_rights_evaluator(lambda uri: raw)
    assert evaluator(record) is True

    tampered = dict(record, provider_scope="all-data-redistribution")
    assert evaluator(tampered) is False
    tampered = dict(record, rights_approval_id="other-approval")
    assert evaluator(tampered) is False


@pytest.mark.parametrize("mutation", [
    lambda data: data["allowed_actions"].clear(),
    lambda data: data["entitlement"].update(status="EXPIRED"),
    lambda data: data["entitlement"].update(expires_at="2020-01-01T00:00:00Z"),
    lambda data: data["entitlement"]["quota"].update(remaining=0),
    lambda data: data["terms"].update(status="NOT_ACCEPTED"),
    lambda data: (data.pop("terms_version"), data["terms"].pop("version")),
])
def test_provider_rights_evaluator_denies_missing_or_invalid_permission(mutation):
    raw = json.loads(_rights_bytes())
    mutation(raw)
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    record = _rights_record()
    record["rights_evidence_sha256"] = hashlib.sha256(payload).hexdigest()
    record["rights_evaluated_at"] = json.loads(payload)["evaluated_at"]
    assert build_provider_rights_evaluator(lambda uri: payload)(record) is False


def test_sigstore_verifier_uses_runtime_python_module_and_pinned_workflow_identity(monkeypatch):
    calls = []
    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Mock(returncode=0)
    monkeypatch.setattr("veltrix_v2.reporting.trusted_runtime.subprocess.run", fake_run)
    digest = hashlib.sha256(b"manifest").hexdigest()
    workflow_identity = (
        "https://github.com/Nexora-Apparel/veltrix-football/"
        ".github/workflows/report-certification-attestation.yml@refs/heads/main"
    )
    assert _verify_sigstore_bundle(
        artifact_sha256=digest,
        bundle_bytes=b'{"mediaType":"sigstore"}',
        workflow_identity=workflow_identity,
    ) is True
    command, kwargs = calls[0]
    assert command[:4] == [command[0], "-m", "sigstore", "verify"]
    assert "sha256:" + digest in command
    assert "--repository" in command and "Nexora-Apparel/veltrix-football" in command
    assert "--ref" in command and "refs/heads/main" in command
    assert "--cert-identity" in command and workflow_identity in command
    assert "--cert-oidc-issuer" not in command  # verify github enforces GitHub OIDC issuer itself
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
    assert f"sha256:{digest}" in session.get.call_args.args[0]
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


def test_application_runtime_uses_default_deployment_factory_when_bundle_url_is_set(monkeypatch):
    from veltrix_v2.reporting.runtime import load_runtime_publication_dependencies
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("VELTRIX_V2_EVIDENCE_ALLOWED_HOSTS", "raw.githubusercontent.com,evidence.example")
    dependencies = load_runtime_publication_dependencies({
        "VELTRIX_V2_REPORT_BUNDLE_URL": (
            "https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/"
            "command-data/public-data/v2_report_bundle.json"
        ),
    })
    assert dependencies is not None
    assert callable(dependencies.verifier)
    assert callable(dependencies.bundle_reader)
    assert dependencies.bundle_url.endswith("/command-data/public-data/v2_report_bundle.json")


def test_application_runtime_does_not_construct_trusted_factory_without_credentials(monkeypatch):
    from veltrix_v2.reporting.runtime import load_runtime_publication_dependencies
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(DeploymentVerificationError, match="GITHUB_ATTESTATION_READ_TOKEN_REQUIRED"):
        load_runtime_publication_dependencies({
            "VELTRIX_V2_REPORT_BUNDLE_URL": (
                "https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/"
                "command-data/public-data/v2_report_bundle.json"
            ),
            "VELTRIX_V2_EVIDENCE_ALLOWED_HOSTS": "raw.githubusercontent.com",
        })


def test_attestation_verifier_fetches_and_verifies_candidate_bundle_for_exact_subject(monkeypatch):
    session = Mock()
    session.get.side_effect = [
        Response(payload={"attestations": [
            {"bundle_url": "https://signed-artifacts.blob.core.windows.net/bundle/subject.json?sig=opaque"},
        ]}),
        Response(content=b'{"sigstore":"bundle"}'),
    ]
    verified = []
    def fake_verify(**kwargs):
        verified.append(kwargs)
        return True
    monkeypatch.setattr(
        "veltrix_v2.reporting.trusted_runtime._verify_sigstore_bundle", fake_verify
    )
    manifest = b"report-bound-certification-manifest"
    digest = hashlib.sha256(manifest).hexdigest()
    assert build_github_attestation_verifier(
        token="read-only-attestations-token", session=session
    )(manifest, digest) is True
    assert verified[0]["artifact_sha256"] == digest
    assert f"sha256:{digest}" in session.get.call_args_list[0].args[0]
    assert verified[0]["bundle_bytes"] == b'{"sigstore":"bundle"}'
    assert verified[0]["workflow_identity"].endswith(
        ".github/workflows/report-certification-attestation.yml@refs/heads/main"
    )
    assert session.get.call_count == 2


def test_pre_attestation_verifier_checks_report_binding_and_delegates_all_release_evidence(monkeypatch):
    from veltrix_v2.evaluation.publication_certification import CERTIFICATION_MANIFEST_SCHEMA
    from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity
    import scripts.veltrix_v2.verify_pre_attestation_report as preflight

    report = bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "preflight-test-2026-11-15",
        "as_of_date": "2026-11-15",
        "cutoff_at_utc": "2026-11-15T10:00:00+00:00",
        "release_mode": "RESTRICTED_PUBLIC",
        "predictions": [],
    })
    manifest = {
        "manifest_schema": CERTIFICATION_MANIFEST_SCHEMA,
        "report_id": report["report_id"],
        "report_sha256": report["report_sha256"],
        "status": "CERTIFIED",
        "certifications": [{"status": "CERTIFIED", "blockers": []}],
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    seen = {}

    def fake_authorize(candidate_report, candidate_manifest, attestation, rights, reader):
        seen["report"] = candidate_report
        seen["manifest"] = candidate_manifest
        seen["attestation"] = attestation(candidate_manifest, hashlib.sha256(candidate_manifest).hexdigest())
        seen["rights"] = rights({"rights_evidence_uri": "https://evidence.example/rights.json"})
        seen["evidence"] = reader("https://evidence.example/source.json")
        return True

    monkeypatch.setattr(preflight, "verify_publication_authorization", fake_authorize)
    ok, code = preflight.verify_pre_attestation_report(
        json.dumps(report, sort_keys=True).encode(),
        manifest_bytes,
        lambda uri: b"verified-evidence",
    )
    assert ok is True
    assert code == "PRE_ATTESTATION_RELEASE_EVIDENCE_VERIFIED"
    assert seen["attestation"] is True
    assert seen["rights"] is False  # A real provider-rights record is required.
    assert seen["evidence"] == b"verified-evidence"


def test_pre_attestation_verifier_rejects_report_manifest_hash_mismatch():
    from veltrix_v2.evaluation.publication_certification import CERTIFICATION_MANIFEST_SCHEMA
    from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity
    from scripts.veltrix_v2.verify_pre_attestation_report import verify_pre_attestation_report

    report = bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "preflight-mismatch-2026-11-15",
        "as_of_date": "2026-11-15",
        "cutoff_at_utc": "2026-11-15T10:00:00+00:00",
        "release_mode": "RESTRICTED_PUBLIC",
        "predictions": [],
    })
    manifest = {
        "manifest_schema": CERTIFICATION_MANIFEST_SCHEMA,
        "report_id": report["report_id"],
        "report_sha256": "0" * 64,
        "status": "CERTIFIED",
        "certifications": [{"status": "CERTIFIED", "blockers": []}],
    }
    ok, code = verify_pre_attestation_report(
        json.dumps(report).encode(),
        json.dumps(manifest).encode(),
        lambda uri: b"evidence",
    )
    assert ok is False
    assert code == "REPORT_BOUND_MANIFEST_INVALID"


def test_provider_rights_evaluator_accepts_recent_active_nonexpiring_entitlement():
    raw = json.loads(_rights_bytes())
    raw["entitlement"].pop("expires_at")
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    record = _rights_record()
    record["rights_evidence_sha256"] = hashlib.sha256(payload).hexdigest()
    record["rights_evaluated_at"] = raw["evaluated_at"]
    assert build_provider_rights_evaluator(lambda uri: payload)(record) is True
