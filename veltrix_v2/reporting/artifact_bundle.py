"""Build and persist one immutable V2 report bundle for every delivery surface."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from veltrix_v2.reporting.report_identity import (
    REPORT_SCHEMA,
    ReportIdentity,
    assert_report_surface_bundle,
    bind_report_identity,
    verify_report_identity,
)


@dataclass(frozen=True, slots=True)
class ReportSurfaceBundle:
    canonical_report: dict[str, Any]
    scheduled_report: dict[str, Any]
    telegram_report: dict[str, Any]
    website_projection: dict[str, Any]
    identity: ReportIdentity


PORTABLE_BUNDLE_SCHEMA = "VELTRIX_PORTABLE_REPORT_SURFACE_BUNDLE_V1"
_SURFACE_NAMES = ("canonical", "scheduled", "telegram", "dashboard")


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def serialize_portable_report_surface_bundle(bundle: ReportSurfaceBundle) -> bytes:
    """Serialize all four delivery surfaces into one hash-bound portable artifact."""
    identity = assert_report_surface_bundle(
        bundle.canonical_report,
        bundle.scheduled_report,
        bundle.telegram_report,
        bundle.website_projection,
    )
    if identity != bundle.identity:
        raise ValueError("REPORT_SURFACE_BUNDLE_IDENTITY_MISMATCH")
    surfaces = {
        "canonical": bundle.canonical_report,
        "scheduled": bundle.scheduled_report,
        "telegram": bundle.telegram_report,
        "dashboard": bundle.website_projection,
    }
    surface_hashes = {
        name: hashlib.sha256(_canonical_json_bytes(value)).hexdigest()
        for name, value in surfaces.items()
    }
    envelope = {
        "schema": PORTABLE_BUNDLE_SCHEMA,
        "report_id": identity.report_id,
        "report_sha256": identity.report_sha256,
        "surface_sha256": surface_hashes,
        "surfaces": surfaces,
    }
    raw = json.dumps(
        envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(raw) > 32_000_000:
        raise ValueError("PORTABLE_REPORT_BUNDLE_TOO_LARGE")
    return raw


def parse_portable_report_surface_bundle(raw: bytes) -> ReportSurfaceBundle:
    """Parse one portable artifact and verify all four surface hashes and identities."""
    if not isinstance(raw, bytes) or not raw or len(raw) > 32_000_000:
        raise ValueError("PORTABLE_REPORT_BUNDLE_BYTES_INVALID")
    envelope = json.loads(raw.decode("utf-8"))
    if (
        not isinstance(envelope, dict)
        or envelope.get("schema") != PORTABLE_BUNDLE_SCHEMA
        or not isinstance(envelope.get("surfaces"), dict)
        or set(envelope["surfaces"]) != set(_SURFACE_NAMES)
        or not isinstance(envelope.get("surface_sha256"), dict)
        or set(envelope["surface_sha256"]) != set(_SURFACE_NAMES)
    ):
        raise ValueError("PORTABLE_REPORT_BUNDLE_SCHEMA_INVALID")
    for name in _SURFACE_NAMES:
        surface = envelope["surfaces"][name]
        expected = envelope["surface_sha256"][name]
        if not isinstance(surface, dict) or not isinstance(expected, str):
            raise ValueError("PORTABLE_REPORT_BUNDLE_SURFACE_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("PORTABLE_REPORT_BUNDLE_SURFACE_HASH_INVALID")
        if hashlib.sha256(_canonical_json_bytes(surface)).hexdigest() != expected:
            raise ValueError("PORTABLE_REPORT_BUNDLE_SURFACE_HASH_MISMATCH")
    surfaces = envelope["surfaces"]
    identity = assert_report_surface_bundle(
        surfaces["canonical"],
        surfaces["scheduled"],
        surfaces["telegram"],
        surfaces["dashboard"],
    )
    if (
        envelope.get("report_id") != identity.report_id
        or envelope.get("report_sha256") != identity.report_sha256
    ):
        raise ValueError("PORTABLE_REPORT_BUNDLE_IDENTITY_MISMATCH")
    return ReportSurfaceBundle(
        surfaces["canonical"],
        surfaces["scheduled"],
        surfaces["telegram"],
        surfaces["dashboard"],
        identity,
    )


def build_report_surface_bundle(report: Mapping[str, Any]) -> ReportSurfaceBundle:
    """Bind all surfaces to the same report bytes and identity."""
    if report.get("schema") != REPORT_SCHEMA:
        raise ValueError("V2_REPORT_SCHEMA_REQUIRED")
    if "report_sha256" in report:
        canonical = dict(report)
        identity = verify_report_identity(canonical)
    else:
        canonical = bind_report_identity(report)
        identity = verify_report_identity(canonical)
    if not isinstance(canonical.get("predictions"), list):
        raise ValueError("V2_REPORT_PREDICTIONS_LIST_REQUIRED")

    scheduled = json.loads(json.dumps(canonical, ensure_ascii=False, allow_nan=False))
    telegram = json.loads(json.dumps(canonical, ensure_ascii=False, allow_nan=False))
    dashboard = {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": identity.as_of_date,
        "report_id": identity.report_id,
        "report_sha256": identity.report_sha256,
        "status": canonical.get("status"),
        "release_mode": canonical.get("release_mode"),
        "predictions": json.loads(json.dumps(canonical["predictions"], ensure_ascii=False, allow_nan=False)),
    }
    assert_report_surface_bundle(canonical, scheduled, telegram, dashboard)
    return ReportSurfaceBundle(canonical, scheduled, telegram, dashboard, identity)


def _write_immutable(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("REPORT_ARTIFACT_IMMUTABLE_CONFLICT")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            for directory in (path.parent, path.parent.parent):
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ValueError("REPORT_ARTIFACT_IMMUTABLE_CONFLICT")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_report_surface_bundle(
    output_dir: str | Path, report_id: str
) -> ReportSurfaceBundle:
    """Read and verify all four immutable artifacts from a previously built bundle."""
    if not isinstance(report_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", report_id):
        raise ValueError("REPORT_ID_NOT_SAFE_FOR_ARTIFACT_PATH")
    root = Path(output_dir)
    paths = {
        "canonical": root / "reports" / f"{report_id}.json",
        "scheduled": root / "scheduled" / f"{report_id}.json",
        "telegram": root / "telegram" / f"{report_id}.json",
        "dashboard": root / "dashboard" / f"{report_id}.json",
    }
    commit_path = root / "bundles" / f"{report_id}.commit.json"
    try:
        commit_raw = commit_path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError("REPORT_BUNDLE_COMMIT_MARKER_MISSING") from exc
    if len(commit_raw) > 32_000:
        raise ValueError("REPORT_BUNDLE_COMMIT_MARKER_TOO_LARGE")
    commit = json.loads(commit_raw.decode("utf-8"))
    if (
        not isinstance(commit, dict)
        or commit.get("schema") != "VELTRIX_REPORT_BUNDLE_COMMIT_V1"
        or commit.get("report_id") != report_id
        or not isinstance(commit.get("artifacts"), dict)
        or set(commit.get("artifacts", {})) != set(paths)
    ):
        raise ValueError("REPORT_BUNDLE_COMMIT_MARKER_INVALID")

    payloads: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise ValueError(f"REPORT_BUNDLE_ARTIFACT_MISSING:{name}") from exc
        expected_hash = commit["artifacts"].get(name)
        if (
            not isinstance(expected_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            or hashlib.sha256(raw).hexdigest() != expected_hash
        ):
            raise ValueError("REPORT_BUNDLE_COMMIT_HASH_MISMATCH")
        if len(raw) > 8_000_000:
            raise ValueError("REPORT_ARTIFACT_TOO_LARGE")
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("REPORT_ARTIFACT_MUST_BE_OBJECT")
        payloads[name] = value
    identity = assert_report_surface_bundle(
        payloads["canonical"],
        payloads["scheduled"],
        payloads["telegram"],
        payloads["dashboard"],
    )
    if identity.report_id != report_id:
        raise ValueError("REPORT_ARTIFACT_PATH_IDENTITY_MISMATCH")
    if commit.get("report_sha256") != identity.report_sha256:
        raise ValueError("REPORT_BUNDLE_COMMIT_IDENTITY_MISMATCH")
    return ReportSurfaceBundle(
        payloads["canonical"],
        payloads["scheduled"],
        payloads["telegram"],
        payloads["dashboard"],
        identity,
    )


def load_authorized_report_surface_bundle(
    output_dir: str | Path,
    report_id: str,
    authorization_verifier,
) -> ReportSurfaceBundle:
    """Load the four-surface bundle only when a trusted verifier authorizes publication."""
    bundle = load_report_surface_bundle(output_dir, report_id)
    report = bundle.canonical_report
    predictions = report.get("predictions")
    if (
        report.get("release_mode") not in {"RESTRICTED_PUBLIC", "FULL_PUBLIC"}
        or not isinstance(predictions, list)
        or not predictions
        or any(
            not isinstance(fixture, dict)
            or fixture.get("publication_status") != "PUBLISHED"
            for fixture in predictions
        )
    ):
        raise PermissionError("REPORT_BUNDLE_CONTAINS_NON_PUBLIC_FORECASTS")
    if not callable(authorization_verifier):
        raise PermissionError("AUTHORITATIVE_PUBLICATION_VERIFIER_REQUIRED")
    if authorization_verifier(report, bundle.identity) is not True:
        raise PermissionError("AUTHORITATIVE_PUBLICATION_AUTHORIZATION_NOT_VERIFIED")
    return bundle


def load_authorized_scheduled_report(
    output_dir: str | Path,
    report_id: str,
    authorization_verifier,
) -> dict[str, Any]:
    """Return the scheduled copy only after the complete bundle passes publication gates."""
    return load_authorized_report_surface_bundle(
        output_dir, report_id, authorization_verifier
    ).scheduled_report


def persist_report_surface_bundle(
    bundle: ReportSurfaceBundle, output_dir: str | Path
) -> dict[str, Path]:
    """Write immutable canonical/scheduled/Telegram artifacts and dashboard projection."""
    identity = bundle.identity
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", identity.report_id):
        raise ValueError("REPORT_ID_NOT_SAFE_FOR_ARTIFACT_PATH")
    verified_identity = assert_report_surface_bundle(
        bundle.canonical_report,
        bundle.scheduled_report,
        bundle.telegram_report,
        bundle.website_projection,
    )
    if verified_identity != identity:
        raise ValueError("REPORT_SURFACE_BUNDLE_IDENTITY_MISMATCH")
    root = Path(output_dir)
    report_bytes = (
        json.dumps(bundle.canonical_report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    scheduled_bytes = (
        json.dumps(bundle.scheduled_report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    telegram_bytes = (
        json.dumps(bundle.telegram_report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    dashboard_bytes = (
        json.dumps(bundle.website_projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    paths = {
        "canonical": root / "reports" / f"{identity.report_id}.json",
        "scheduled": root / "scheduled" / f"{identity.report_id}.json",
        "telegram": root / "telegram" / f"{identity.report_id}.json",
        "dashboard": root / "dashboard" / f"{identity.report_id}.json",
    }
    for key, payload in (
        ("canonical", report_bytes),
        ("scheduled", scheduled_bytes),
        ("telegram", telegram_bytes),
        ("dashboard", dashboard_bytes),
    ):
        _write_immutable(paths[key], payload)
    commit = {
        "schema": "VELTRIX_REPORT_BUNDLE_COMMIT_V1",
        "report_id": identity.report_id,
        "report_sha256": identity.report_sha256,
        "artifacts": {
            key: hashlib.sha256(payload).hexdigest()
            for key, payload in (
                ("canonical", report_bytes),
                ("scheduled", scheduled_bytes),
                ("telegram", telegram_bytes),
                ("dashboard", dashboard_bytes),
            )
        },
    }
    commit_bytes = (
        json.dumps(commit, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    _write_immutable(
        root / "bundles" / f"{identity.report_id}.commit.json",
        commit_bytes,
    )
    verified = load_report_surface_bundle(root, identity.report_id)
    if verified.identity != identity:
        raise ValueError("PERSISTED_REPORT_BUNDLE_IDENTITY_MISMATCH")
    return {
        **paths,
        "commit_marker": root / "bundles" / f"{identity.report_id}.commit.json",
    }
