"""Fail-closed publisher for the single V2 report bundle.

The publisher is deliberately transport-injected. It cannot select another
repository, branch or path, and it requires the authoritative publication
verifier before it reads or writes the public command-data branch.
"""
from __future__ import annotations

from dataclasses import dataclass
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
        if not isinstance(existing.content, bytes) or not isinstance(existing.sha, str) or not existing.sha:
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
