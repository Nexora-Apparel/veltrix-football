"""Deployment-native V2 publication verifier.

This adapter runs inside the Python application runtime. It does not depend on
GitHub CLI: GitHub's attestations API supplies Sigstore bundles and sigstore-
python verifies their signature, transparency proof, workflow identity and ref.
All missing configuration and all evidence failures deny publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping
from urllib.parse import urlsplit

import requests

from veltrix_v2.evaluation.publication_certification import (
    CERTIFICATION_MANIFEST_SCHEMA,
    build_publication_verifier,
    verify_publication_authorization,
)
from veltrix_v2.reporting.report_identity import ReportIdentity, verify_report_identity


REPOSITORY = "Nexora-Apparel/veltrix-football"
WORKFLOW_PATH = ".github/workflows/report-certification-attestation.yml"
WORKFLOW_NAME = "VELTRIX Report Certification Attestation"
OIDC_ISSUER = "https://token.actions.githubusercontent.com"
RAW_HOST = "raw.githubusercontent.com"
MAX_EVIDENCE_BYTES = 8_000_000
MAX_ATTESTATION_BYTES = 4_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9._-]{1,160}$")


class DeploymentVerificationError(RuntimeError):
    """A deployment trust dependency is missing or cannot be verified."""


def _strict_json(raw: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("NONFINITE_JSON_VALUE:" + value)

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)


def _allowed_hosts(environ: Mapping[str, str]) -> frozenset[str]:
    raw = environ.get("VELTRIX_V2_EVIDENCE_ALLOWED_HOSTS", "")
    hosts = frozenset(part.strip().lower().rstrip(".") for part in raw.split(",") if part.strip())
    if not hosts or any(not re.fullmatch(r"[a-z0-9.-]+", host) for host in hosts):
        raise DeploymentVerificationError("EVIDENCE_HOST_ALLOWLIST_REQUIRED")
    return hosts


def _validate_https_url(url: str, hosts: frozenset[str]) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or host not in hosts
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
        or (
            host == RAW_HOST
            and not parsed.path.startswith(f"/{REPOSITORY}/main/")
        )
    ):
        raise DeploymentVerificationError("EVIDENCE_URL_NOT_ALLOWLISTED")
    return url


def build_hash_checked_evidence_reader(
    *, allowed_hosts: frozenset[str], session: requests.Session | None = None
):
    """Read only explicitly allowlisted HTTPS objects; redirects are never followed."""
    client = session or requests.Session()

    def read(uri: str) -> bytes:
        url = _validate_https_url(uri, allowed_hosts)
        response = client.get(
            url,
            headers={"Accept": "application/octet-stream", "User-Agent": "VELTRIX-FOOTBALL/2.0"},
            timeout=(3.05, 10),
            allow_redirects=False,
            stream=True,
        )
        try:
            if response.status_code != 200:
                raise DeploymentVerificationError("EVIDENCE_FETCH_FAILED")
            declared = response.headers.get("Content-Length")
            if declared and (not declared.isdigit() or int(declared) > MAX_EVIDENCE_BYTES):
                raise DeploymentVerificationError("EVIDENCE_SIZE_INVALID")
            chunks = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_EVIDENCE_BYTES:
                    raise DeploymentVerificationError("EVIDENCE_SIZE_INVALID")
                chunks.append(chunk)
            raw = b"".join(chunks)
            if not raw:
                raise DeploymentVerificationError("EVIDENCE_EMPTY")
            return raw
        finally:
            response.close()

    return read


def build_provider_rights_evaluator(evidence_reader):
    """Validate provider identity, entitlement, scope, terms and remaining quota.

    Rights evidence schema:
      VELTRIX_PROVIDER_RIGHTS_EVIDENCE_V1
    It must identify the provider and approval referenced by the certification
    record and explicitly allow PREDICTION_PUBLICATION for the recorded scope.
    """
    def verify(record: Mapping[str, Any]) -> bool:
        try:
            uri = record.get("rights_evidence_uri")
            expected = record.get("rights_evidence_sha256")
            if not isinstance(uri, str) or not isinstance(expected, str) or not _SHA256.fullmatch(expected):
                return False
            raw = evidence_reader(uri)
            if hashlib.sha256(raw).hexdigest() != expected:
                return False
            evidence = _strict_json(raw)
            if not isinstance(evidence, dict) or evidence.get("schema") != "VELTRIX_PROVIDER_RIGHTS_EVIDENCE_V1":
                return False
            provider_id = record.get("provider_id")
            scope = record.get("provider_scope")
            if (
                not isinstance(provider_id, str) or not provider_id.strip()
                or not isinstance(scope, str) or not scope.strip()
                or evidence.get("provider_id") != provider_id
                or evidence.get("approval_id") != record.get("rights_approval_id")
                or evidence.get("permitted_scope") != scope
                or evidence.get("status") != "APPROVED"
            ):
                return False
            actions = evidence.get("allowed_actions")
            if not isinstance(actions, list) or "PREDICTION_PUBLICATION" not in actions:
                return False
            entitlement = evidence.get("entitlement")
            terms = evidence.get("terms")
            if not isinstance(entitlement, dict) or not isinstance(terms, dict):
                return False
            if entitlement.get("status") != "ACTIVE" or terms.get("status") != "ACCEPTED":
                return False
            if terms.get("version") != evidence.get("terms_version"):
                return False
            checked_at = entitlement.get("checked_at")
            expires_at = entitlement.get("expires_at")
            terms_checked_at = terms.get("checked_at")
            evaluated_at = evidence.get("evaluated_at")
            record_evaluated_at = record.get("rights_evaluated_at")
            now = datetime.now(timezone.utc)
            def parse(value):
                if not isinstance(value, str):
                    return None
                try:
                    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
                return result if result.tzinfo and result.utcoffset() is not None else None
            checked, expires, terms_checked, evaluated, record_evaluated = map(
                parse, (checked_at, expires_at, terms_checked_at, evaluated_at, record_evaluated_at)
            )
            if (
                checked is None or expires is None or terms_checked is None
                or evaluated is None or record_evaluated is None
                or evaluated != record_evaluated
                or checked > now or terms_checked > now or evaluated > now or expires <= now
                or (now - checked).total_seconds() > 24 * 60 * 60
                or (now - evaluated).total_seconds() > 24 * 60 * 60
                or (now - terms_checked).total_seconds() > 365 * 24 * 60 * 60
            ):
                return False
            quota = entitlement.get("quota")
            if not isinstance(quota, dict):
                return False
            remaining = quota.get("remaining")
            if not isinstance(remaining, int) or isinstance(remaining, bool) or remaining < 1:
                return False
            return True
        except Exception:
            return False

    return verify


def _verify_sigstore_bundle(
    *, artifact_sha256: str, bundle_bytes: bytes, workflow_identity: str,
    repository: str = REPOSITORY,
) -> bool:
    """Verify GitHub OIDC identity and Rekor/Sigstore proofs using sigstore-python."""
    if not _SHA256.fullmatch(artifact_sha256) or not bundle_bytes or len(bundle_bytes) > MAX_ATTESTATION_BYTES:
        return False
    try:
        with tempfile.NamedTemporaryFile(suffix=".sigstore.json") as bundle_file:
            bundle_file.write(bundle_bytes)
            bundle_file.flush()
            command = [
                sys.executable, "-m", "sigstore", "verify", "github",
                "sha256:" + artifact_sha256,
                "--bundle", bundle_file.name,
                "--cert-identity", workflow_identity,
                "--cert-oidc-issuer", OIDC_ISSUER,
                "--repository", repository,
                "--ref", "refs/heads/main",
                "--trigger", "workflow_dispatch",
                "--name", WORKFLOW_NAME,
            ]
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=90, check=False,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def build_github_attestation_verifier(
    *, token: str, session: requests.Session | None = None
):
    """Resolve attestations by exact subject digest and verify every candidate."""
    if not token:
        raise DeploymentVerificationError("GITHUB_ATTESTATION_READ_TOKEN_REQUIRED")
    client = session or requests.Session()
    workflow_identity = f"https://github.com/{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/main"

    def verify(manifest_bytes: bytes, digest: str) -> bool:
        if not isinstance(manifest_bytes, bytes) or hashlib.sha256(manifest_bytes).hexdigest() != digest:
            return False
        url = f"https://api.github.com/repos/{REPOSITORY}/attestations/{digest}"
        try:
            response = client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2026-03-10",
                },
                timeout=(3.05, 10),
                allow_redirects=False,
            )
            if response.status_code != 200:
                return False
            payload = response.json()
            attestations = payload.get("attestations") if isinstance(payload, dict) else None
            if not isinstance(attestations, list):
                return False
            for item in attestations:
                bundle_url = item.get("bundle_url") if isinstance(item, dict) else None
                parsed = urlsplit(bundle_url or "")
                host = (parsed.hostname or "").lower()
                if parsed.scheme != "https" or not host.endswith(".blob.core.windows.net") or parsed.username or parsed.password:
                    continue
                bundle_response = client.get(
                    bundle_url,
                    headers={"Accept": "application/json"},
                    timeout=(3.05, 10),
                    allow_redirects=False,
                    stream=True,
                )
                try:
                    if bundle_response.status_code != 200:
                        continue
                    declared = bundle_response.headers.get("Content-Length")
                    if declared and (not declared.isdigit() or int(declared) > MAX_ATTESTATION_BYTES):
                        continue
                    chunks = []
                    size = 0
                    for chunk in bundle_response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        size += len(chunk)
                        if size > MAX_ATTESTATION_BYTES:
                            chunks = []
                            break
                        chunks.append(chunk)
                    if not chunks:
                        continue
                    raw = b"".join(chunks)
                    if _verify_sigstore_bundle(
                        artifact_sha256=digest,
                        bundle_bytes=raw,
                        workflow_identity=workflow_identity,
                    ):
                        return True
                finally:
                    bundle_response.close()
            return False
        except Exception:
            return False
        finally:
            if "response" in locals():
                response.close()

    return verify


def build_deployment_publication_verifier(
    environ: Mapping[str, str] | None = None,
    *,
    session: requests.Session | None = None,
):
    """Create the real deployment verifier factory used by website and Telegram."""
    env = os.environ if environ is None else environ
    token = env.get("GH_TOKEN") or env.get("GITHUB_TOKEN")
    if not token:
        raise DeploymentVerificationError("GITHUB_ATTESTATION_READ_TOKEN_REQUIRED")
    hosts = _allowed_hosts(env)
    client = session or requests.Session()
    evidence_reader = build_hash_checked_evidence_reader(allowed_hosts=hosts, session=client)
    attestation_verifier = build_github_attestation_verifier(token=token, session=client)
    rights_verifier = build_provider_rights_evaluator(evidence_reader)

    def verifier(report: Mapping[str, Any], identity: ReportIdentity) -> bool:
        try:
            if verify_report_identity(report) != identity:
                return False
            if not _SAFE_REPORT_ID.fullmatch(identity.report_id):
                return False
            manifest_url = (
                "https://raw.githubusercontent.com/" + REPOSITORY
                + "/main/reports/certification/publication-manifests/"
                + identity.report_id + ".json"
            )
            if RAW_HOST not in hosts:
                return False
            manifest_bytes = evidence_reader(manifest_url)
            manifest = _strict_json(manifest_bytes)
            if (
                not isinstance(manifest, dict)
                or manifest.get("manifest_schema") != CERTIFICATION_MANIFEST_SCHEMA
                or manifest.get("report_id") != identity.report_id
                or manifest.get("report_sha256") != identity.report_sha256
                or manifest.get("status") != "CERTIFIED"
                or not isinstance(manifest.get("certifications"), list)
                or not manifest.get("certifications")
            ):
                return False
            return verify_publication_authorization(
                report, manifest_bytes, attestation_verifier, rights_verifier, evidence_reader
            )
        except Exception:
            return False

    return verifier


def build_deployment_publication_verifier_factory():
    """Import-string factory for runtime.py; all credentials come from deployment env."""
    return build_deployment_publication_verifier()
