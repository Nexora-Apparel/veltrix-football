"""Build and persist one immutable V2 report bundle for every delivery surface."""
from __future__ import annotations

from dataclasses import dataclass
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
    payloads: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        raw = path.read_bytes()
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
    return ReportSurfaceBundle(
        payloads["canonical"],
        payloads["scheduled"],
        payloads["telegram"],
        payloads["dashboard"],
        identity,
    )


def persist_report_surface_bundle(
    bundle: ReportSurfaceBundle, output_dir: str | Path
) -> dict[str, Path]:
    """Write immutable canonical/scheduled/Telegram artifacts and dashboard projection."""
    identity = bundle.identity
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,160}", identity.report_id):
        raise ValueError("REPORT_ID_NOT_SAFE_FOR_ARTIFACT_PATH")
    assert_report_surface_bundle(
        bundle.canonical_report,
        bundle.scheduled_report,
        bundle.telegram_report,
        bundle.website_projection,
    )
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
    verified = load_report_surface_bundle(root, identity.report_id)
    if verified.identity != identity:
        raise ValueError("PERSISTED_REPORT_BUNDLE_IDENTITY_MISMATCH")
    return paths
