"""Immutable report identity shared by website, scheduler and Telegram adapters.

This module does not publish predictions or authorize delivery. It binds each
surface to the same canonical report bytes and fails closed on identity drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from typing import Any, Iterable, Mapping


REPORT_SCHEMA = "VELTRIX_V2_DAILY_REPORT_V1"
_HASH_FIELD = "report_sha256"


def canonical_report_bytes(report: Mapping[str, Any]) -> bytes:
    """Serialize a report deterministically, excluding its self-referential hash."""
    if not isinstance(report, Mapping):
        raise TypeError("report must be a mapping")
    payload = {key: value for key, value in report.items() if key != _HASH_FIELD}
    try:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("report contains non-canonical JSON values") from exc


@dataclass(frozen=True, slots=True)
class ReportIdentity:
    report_id: str
    as_of_date: str
    report_sha256: str
    schema: str = REPORT_SCHEMA

    def __post_init__(self) -> None:
        if not self.report_id or self.report_id.strip() != self.report_id:
            raise ValueError("report_id must be a non-empty canonical string")
        try:
            parsed = date.fromisoformat(self.as_of_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("as_of_date must be an ISO calendar date") from exc
        if parsed.isoformat() != self.as_of_date:
            raise ValueError("as_of_date must use YYYY-MM-DD")
        if self.schema != REPORT_SCHEMA:
            raise ValueError("unsupported report schema")
        if len(self.report_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.report_sha256
        ):
            raise ValueError("report_sha256 must be lowercase SHA-256 hex")


def create_report_identity(report: Mapping[str, Any]) -> ReportIdentity:
    """Create a stable identity from a complete, versioned report document."""
    if report.get("schema") != REPORT_SCHEMA:
        raise ValueError("report schema is missing or unsupported")
    report_id = report.get("report_id")
    as_of_date = report.get("as_of_date")
    if not isinstance(report_id, str) or not isinstance(as_of_date, str):
        raise ValueError("report_id and as_of_date are required strings")
    digest = hashlib.sha256(canonical_report_bytes(report)).hexdigest()
    return ReportIdentity(report_id, as_of_date, digest)


def verify_report_identity(report: Mapping[str, Any]) -> ReportIdentity:
    """Verify the embedded report hash and return its immutable identity."""
    identity = create_report_identity(report)
    supplied = report.get(_HASH_FIELD)
    if supplied != identity.report_sha256:
        raise ValueError("report content hash does not match canonical report bytes")
    return identity


def bind_report_identity(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached JSON-compatible report with its canonical hash attached."""
    payload = json.loads(canonical_report_bytes(report).decode("utf-8"))
    identity = create_report_identity(payload)
    payload[_HASH_FIELD] = identity.report_sha256
    return payload


def assert_same_report(reports: Iterable[Mapping[str, Any]]) -> ReportIdentity:
    """Require website, scheduled and Telegram report copies to be identical."""
    identities = [verify_report_identity(report) for report in reports]
    if not identities:
        raise ValueError("at least one report surface is required")
    first = identities[0]
    if any(identity != first for identity in identities[1:]):
        raise ValueError("report surfaces do not reference the same immutable report")
    return first


def delivery_idempotency_key(identity: ReportIdentity, destination: str) -> str:
    """Bind a delivery attempt to report identity and exact destination."""
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("destination must be explicit")
    material = f"{identity.report_id}\n{identity.report_sha256}\n{destination}".encode()
    return hashlib.sha256(material).hexdigest()


def assert_report_surface_bundle(
    canonical_report: Mapping[str, Any],
    scheduled_report: Mapping[str, Any],
    telegram_report: Mapping[str, Any],
    website_projection: Mapping[str, Any],
) -> ReportIdentity:
    """Verify scheduler and Telegram use the canonical report and website projection."""
    identity = assert_same_report(
        [canonical_report, scheduled_report, telegram_report]
    )
    if (
        website_projection.get("report_id") != identity.report_id
        or website_projection.get("report_sha256") != identity.report_sha256
        or website_projection.get("as_of_date") != identity.as_of_date
    ):
        raise ValueError("WEBSITE_REPORT_PROJECTION_IDENTITY_MISMATCH")
    return identity
