"""Fail-closed publisher for the single V2 report bundle.

The publisher is deliberately transport-injected. It cannot select another
repository, branch or path, and it requires the authoritative publication
verifier before it reads or writes the public command-data branch.
"""
from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from typing import Protocol

from veltrix_v2.reporting.artifact_bundle import (
    load_authorized_portable_report_surface_bundle,
    parse_portable_report_surface_bundle,
)


PUBLICATION_REPOSITORY = "Nexora-Apparel/veltrix-football"
PUBLICATION_BRANCH = "command-data"
PUBLICATION_PATH = "public-data/v2_report_bundle.json"


@dataclass(frozen=True, slots=True)
class ExistingContentsFile:
    content: bytes
    sha: str


class GitHubContentsClient(Protocol):
    def get_file(self, repository: str, branch: str, path: str) -> ExistingContentsFile | None:
        ...

    def put_file(
        self,
        repository: str,
        branch: str,
        path: str,
        content: bytes,
        *,
        sha: str | None,
        message: str,
    ) -> str:
        ...


class GitHubContentsApiClient:
    """Concrete Contents API client pinned to the single V2 publication target."""

    def __init__(self, token: str, *, opener=None):
        if not isinstance(token, str) or not token.strip():
            raise ValueError("GITHUB_PUBLICATION_TOKEN_REQUIRED")
        self._token = token.strip()
        self._opener = opener or urlopen

    def _assert_target(self, repository: str, branch: str, path: str) -> None:
        if (
            repository != PUBLICATION_REPOSITORY
            or branch != PUBLICATION_BRANCH
            or path != PUBLICATION_PATH
        ):
            raise PermissionError("GITHUB_PUBLICATION_TARGET_NOT_ALLOWLISTED")

    def _request(self, method: str, url: str, body: dict | None = None) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Veltrix-V2-Report-Publisher",
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"GITHUB_CONTENTS_API_HTTP_{exc.code}") from None
        except (URLError, OSError, TimeoutError, json.JSONDecodeError):
            raise RuntimeError("GITHUB_CONTENTS_API_REQUEST_FAILED") from None
        if not isinstance(payload, dict):
            raise RuntimeError("GITHUB_CONTENTS_API_RESPONSE_INVALID")
        return payload

    def get_file(self, repository: str, branch: str, path: str) -> ExistingContentsFile | None:
        self._assert_target(repository, branch, path)
        encoded_path = quote(path, safe="/")
        url = (
            f"https://api.github.com/repos/{repository}/contents/{encoded_path}"
            f"?ref={quote(branch, safe='')}"
        )
        try:
            metadata = self._request("GET", url)
        except RuntimeError as exc:
            if str(exc) == "GITHUB_CONTENTS_API_HTTP_404":
                return None
            raise
        sha = metadata.get("sha")
        if not isinstance(sha, str) or not sha:
            raise RuntimeError("GITHUB_EXISTING_FILE_SHA_MISSING")
        raw_url = f"https://raw.githubusercontent.com/{repository}/{branch}/{encoded_path}"
        try:
            request = Request(raw_url, headers={
                "User-Agent": "Veltrix-V2-Report-Publisher",
                "Cache-Control": "no-cache",
            })
            with self._opener(request, timeout=20) as response:
                content = response.read(8_000_001)
        except (HTTPError, URLError, OSError, TimeoutError):
            raise RuntimeError("GITHUB_EXISTING_BUNDLE_READ_FAILED") from None
        if not content or len(content) > 8_000_000:
            raise RuntimeError("GITHUB_EXISTING_BUNDLE_SIZE_INVALID")
        blob_sha = hashlib.sha1(
            b"blob " + str(len(content)).encode("ascii") + b"\\0" + content
        ).hexdigest()
        if blob_sha != sha:
            raise RuntimeError("GITHUB_EXISTING_BUNDLE_SHA_MISMATCH")
        return ExistingContentsFile(content=content, sha=sha)

    def put_file(
        self,
        repository: str,
        branch: str,
        path: str,
        content: bytes,
        *,
        sha: str | None,
        message: str,
    ) -> str:
        self._assert_target(repository, branch, path)
        if not isinstance(content, bytes) or not content or len(content) > 8_000_000:
            raise ValueError("GITHUB_PUBLICATION_CONTENT_INVALID")
        if sha is not None and (not isinstance(sha, str) or not sha):
            raise ValueError("GITHUB_PUBLICATION_EXISTING_SHA_INVALID")
        body = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": branch,
        }
        if sha is not None:
            body["sha"] = sha
        encoded_path = quote(path, safe="/")
        url = f"https://api.github.com/repos/{repository}/contents/{encoded_path}"
        payload = self._request("PUT", url, body)
        commit_sha = ((payload.get("commit") or {}).get("sha"))
        if not isinstance(commit_sha, str) or not commit_sha:
            raise RuntimeError("GITHUB_PUBLICATION_COMMIT_SHA_MISSING")
        return commit_sha


@dataclass(frozen=True, slots=True)
class PublicationResult:
    status: str
    report_id: str
    report_sha256: str
    repository: str = PUBLICATION_REPOSITORY
    branch: str = PUBLICATION_BRANCH
    path: str = PUBLICATION_PATH
    commit_sha: str | None = None


def publish_v2_report_bundle(
    portable_bundle_bytes: bytes,
    *,
    authorization_verifier,
    client: GitHubContentsClient,
) -> PublicationResult:
    """Publish one fully authorized immutable report bundle to command-data."""
    if not isinstance(portable_bundle_bytes, bytes) or not portable_bundle_bytes or len(portable_bundle_bytes) > 8_000_000:
        raise ValueError("PORTABLE_REPORT_BUNDLE_SIZE_OR_TYPE_INVALID")
    if not callable(authorization_verifier):
        raise PermissionError("AUTHORITATIVE_PUBLICATION_VERIFIER_REQUIRED")
    if client is None or not callable(getattr(client, "get_file", None)) or not callable(
        getattr(client, "put_file", None)
    ):
        raise ValueError("GITHUB_CONTENTS_CLIENT_REQUIRED")

    incoming = load_authorized_portable_report_surface_bundle(
        portable_bundle_bytes, authorization_verifier
    )
    identity = incoming.identity

    existing = client.get_file(
        PUBLICATION_REPOSITORY, PUBLICATION_BRANCH, PUBLICATION_PATH
    )
    existing_sha = None
    if existing is not None:
        if (
            not isinstance(existing.content, bytes)
            or not existing.content
            or len(existing.content) > 8_000_000
            or not isinstance(existing.sha, str)
            or not existing.sha
        ):
            raise ValueError("EXISTING_REPORT_BUNDLE_METADATA_INVALID")
        try:
            prior = parse_portable_report_surface_bundle(existing.content)
        except Exception:
            raise ValueError("EXISTING_REPORT_BUNDLE_INVALID; refusing to overwrite") from None
        prior_identity = prior.identity
        if prior_identity.report_id == identity.report_id:
            if prior_identity.report_sha256 == identity.report_sha256:
                return PublicationResult(
                    "ALREADY_PUBLISHED",
                    identity.report_id,
                    identity.report_sha256,
                )
            raise ValueError("REPORT_ID_IMMUTABILITY_CONFLICT")
        if prior_identity.as_of_date > identity.as_of_date:
            raise ValueError("STALE_REPORT_CANNOT_REPLACE_NEWER_PUBLICATION")
        existing_sha = existing.sha

    commit_sha = client.put_file(
        PUBLICATION_REPOSITORY,
        PUBLICATION_BRANCH,
        PUBLICATION_PATH,
        portable_bundle_bytes,
        sha=existing_sha,
        message=f"Publish certified VELTRIX V2 report {identity.report_id}",
    )
    if not isinstance(commit_sha, str) or not commit_sha.strip():
        raise RuntimeError("GITHUB_PUBLICATION_COMMIT_SHA_MISSING")
    return PublicationResult(
        "PUBLISHED",
        identity.report_id,
        identity.report_sha256,
        commit_sha=commit_sha,
    )
