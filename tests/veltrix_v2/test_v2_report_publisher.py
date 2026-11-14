from __future__ import annotations

import hashlib
import json
from urllib.error import HTTPError

import pytest

from veltrix_v2.reporting.artifact_bundle import (
    build_report_surface_bundle,
    serialize_portable_report_surface_bundle,
)
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA
from veltrix_v2.reporting.publisher import (
    ExistingContentsFile,
    GitHubContentsApiClient,
    PUBLICATION_BRANCH,
    PUBLICATION_PATH,
    PUBLICATION_REPOSITORY,
    publish_v2_report_bundle,
)


def public_bundle(report_id="public-report-1", as_of_date="2026-11-14", note="first"):
    report = {
        "schema": REPORT_SCHEMA,
        "report_id": report_id,
        "as_of_date": as_of_date,
        "release_mode": "RESTRICTED_PUBLIC",
        "status": "PUBLISHED",
        "note": note,
        "predictions": [{
            "fixture_id": "fixture-1",
            "publication_status": "PUBLISHED",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "certified_markets": ["1X2"],
            "markets": {"1X2": {"home": 0.5, "draw": 0.25, "away": 0.25}},
        }],
    }
    return serialize_portable_report_surface_bundle(build_report_surface_bundle(report))


def authorized(report, identity):
    return report.get("report_sha256") == identity.report_sha256


class FakeContentsClient:
    def __init__(self, existing=None):
        self.existing = existing
        self.get_calls = []
        self.put_calls = []

    def get_file(self, repository, branch, path):
        self.get_calls.append((repository, branch, path))
        return self.existing

    def put_file(self, repository, branch, path, content, *, sha, message):
        self.put_calls.append((repository, branch, path, content, sha, message))
        return "commit-sha-123"


def test_publisher_writes_only_fixed_command_data_bundle_after_authorization():
    raw = public_bundle()
    client = FakeContentsClient()
    result = publish_v2_report_bundle(
        raw, authorization_verifier=authorized, client=client
    )
    assert result.status == "PUBLISHED"
    assert result.repository == PUBLICATION_REPOSITORY
    assert result.branch == PUBLICATION_BRANCH
    assert result.path == PUBLICATION_PATH
    assert result.commit_sha == "commit-sha-123"
    assert client.get_calls == [(PUBLICATION_REPOSITORY, PUBLICATION_BRANCH, PUBLICATION_PATH)]
    assert len(client.put_calls) == 1
    assert client.put_calls[0][3] == raw
    assert client.put_calls[0][4] is None


def test_publisher_requires_verifier_before_any_github_access():
    client = FakeContentsClient()
    with pytest.raises(PermissionError, match="VERIFIER_REQUIRED"):
        publish_v2_report_bundle(
            public_bundle(), authorization_verifier=None, client=client
        )
    assert client.get_calls == []
    assert client.put_calls == []


def test_publisher_rejects_unauthorized_bundle_before_any_github_access():
    client = FakeContentsClient()
    with pytest.raises(PermissionError, match="AUTHORIZATION_NOT_VERIFIED"):
        publish_v2_report_bundle(
            public_bundle(), authorization_verifier=lambda *_: False, client=client
        )
    assert client.get_calls == []
    assert client.put_calls == []


def test_publisher_is_idempotent_for_same_report_identity_and_hash():
    raw = public_bundle()
    client = FakeContentsClient(ExistingContentsFile(raw, "existing-sha"))
    result = publish_v2_report_bundle(
        raw, authorization_verifier=authorized, client=client
    )
    assert result.status == "ALREADY_PUBLISHED"
    assert client.get_calls
    assert client.put_calls == []


def test_publisher_rejects_mutation_under_same_report_id():
    prior = public_bundle(report_id="same-report", note="original")
    changed = public_bundle(report_id="same-report", note="mutated")
    client = FakeContentsClient(ExistingContentsFile(prior, "existing-sha"))
    with pytest.raises(ValueError, match="IMMUTABILITY_CONFLICT"):
        publish_v2_report_bundle(
            changed, authorization_verifier=authorized, client=client
        )
    assert client.put_calls == []


def test_publisher_rejects_stale_report_replacement():
    prior = public_bundle(report_id="newer-report", as_of_date="2026-11-15")
    older = public_bundle(report_id="older-report", as_of_date="2026-11-14")
    client = FakeContentsClient(ExistingContentsFile(prior, "existing-sha"))
    with pytest.raises(ValueError, match="STALE_REPORT"):
        publish_v2_report_bundle(
            older, authorization_verifier=authorized, client=client
        )
    assert client.put_calls == []


def test_publisher_rejects_corrupt_existing_bundle_without_overwrite():
    client = FakeContentsClient(ExistingContentsFile(b"{}", "existing-sha"))
    with pytest.raises(ValueError, match="EXISTING_REPORT_BUNDLE_INVALID"):
        publish_v2_report_bundle(
            public_bundle(), authorization_verifier=authorized, client=client
        )
    assert client.put_calls == []


def test_publisher_updates_existing_file_with_optimistic_sha():
    prior = public_bundle(report_id="previous-report", as_of_date="2026-11-13")
    current = public_bundle(report_id="current-report", as_of_date="2026-11-14")
    client = FakeContentsClient(ExistingContentsFile(prior, "existing-sha"))
    result = publish_v2_report_bundle(
        current, authorization_verifier=authorized, client=client
    )
    assert result.status == "PUBLISHED"
    assert client.put_calls[0][4] == "existing-sha"



def test_publisher_rejects_bundle_larger_than_website_limit_before_github_access():
    client = FakeContentsClient()
    with pytest.raises(ValueError, match="SIZE_OR_TYPE_INVALID"):
        publish_v2_report_bundle(
            b"x" * 8_000_001,
            authorization_verifier=authorized,
            client=client,
        )
    assert client.get_calls == []
    assert client.put_calls == []



class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return self.body


def github_blob_sha(content):
    return hashlib.sha1(
        b"blob " + str(len(content)).encode("ascii") + bytes([0]) + content
    ).hexdigest()


def test_github_contents_client_reads_exact_allowlisted_blob_and_verifies_sha():
    raw = public_bundle()
    sha = github_blob_sha(raw)
    calls = []

    def opener(request, timeout):
        calls.append(request)
        if "api.github.com" in request.full_url:
            return FakeResponse(json.dumps({"sha": sha}).encode())
        return FakeResponse(raw)

    client = GitHubContentsApiClient("test-token", opener=opener)
    existing = client.get_file(PUBLICATION_REPOSITORY, PUBLICATION_BRANCH, PUBLICATION_PATH)
    assert existing == ExistingContentsFile(content=raw, sha=sha)
    assert len(calls) == 2
    assert "api.github.com" in calls[0].full_url
    assert "raw.githubusercontent.com" in calls[1].full_url


def test_github_contents_client_rejects_stale_or_tampered_raw_blob():
    raw = public_bundle()
    wrong_sha = "0" * 40

    def opener(request, timeout):
        if "api.github.com" in request.full_url:
            return FakeResponse(json.dumps({"sha": wrong_sha}).encode())
        return FakeResponse(raw)

    client = GitHubContentsApiClient("test-token", opener=opener)
    with pytest.raises(RuntimeError, match="BUNDLE_SHA_MISMATCH"):
        client.get_file(PUBLICATION_REPOSITORY, PUBLICATION_BRANCH, PUBLICATION_PATH)


def test_github_contents_client_pins_target_and_puts_with_optimistic_sha():
    raw = public_bundle()
    calls = []

    def opener(request, timeout):
        calls.append(request)
        return FakeResponse(json.dumps({"commit": {"sha": "commit-sha"}}).encode())

    client = GitHubContentsApiClient("test-token", opener=opener)
    with pytest.raises(PermissionError, match="TARGET_NOT_ALLOWLISTED"):
        client.get_file(PUBLICATION_REPOSITORY, "main", PUBLICATION_PATH)
    assert calls == []

    commit = client.put_file(
        PUBLICATION_REPOSITORY,
        PUBLICATION_BRANCH,
        PUBLICATION_PATH,
        raw,
        sha="expected-existing-sha",
        message="test publish",
    )
    assert commit == "commit-sha"
    payload = json.loads(calls[0].data)
    assert payload["branch"] == PUBLICATION_BRANCH
    assert payload["sha"] == "expected-existing-sha"
    assert payload["content"]


def test_github_contents_client_requires_token():
    with pytest.raises(ValueError, match="TOKEN_REQUIRED"):
        GitHubContentsApiClient("")



def test_github_contents_client_treats_only_http_404_as_missing_file():
    def opener(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", {}, None)

    client = GitHubContentsApiClient("test-token", opener=opener)
    assert client.get_file(PUBLICATION_REPOSITORY, PUBLICATION_BRANCH, PUBLICATION_PATH) is None
