from __future__ import annotations

import pytest

from scripts.veltrix_v2.verify_portable_report_bundle import verify
from veltrix_v2.reporting.artifact_bundle import (
    build_report_surface_bundle,
    serialize_portable_report_surface_bundle,
)
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA


def source_report():
    return {
        "schema": REPORT_SCHEMA,
        "report_id": "portable-cli-2026-11-14",
        "as_of_date": "2026-11-14",
        "release_mode": "INTERNAL_SHADOW",
        "predictions": [{"fixture_id": "fixture-1", "publication_status": "SHADOW_ONLY"}],
    }


def test_portable_bundle_cli_verifies_all_surfaces_without_side_effects(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    path = tmp_path / "portable.bundle.json"
    path.write_bytes(serialize_portable_report_surface_bundle(bundle))
    result = verify(path)
    assert result["status"] == "PORTABLE_REPORT_SURFACE_BUNDLE_VERIFIED"
    assert result["report_id"] == bundle.identity.report_id
    assert result["surfaces_verified"] == ["canonical", "scheduled", "telegram", "website"]
    assert result["side_effects"] == {
        "provider_requests": 0,
        "database_writes": 0,
        "telegram_messages": 0,
        "schedule_activation": 0,
        "publications": 0,
    }


def test_portable_bundle_cli_rejects_tampered_or_missing_files(tmp_path):
    path = tmp_path / "invalid.bundle.json"
    path.write_bytes(b"not-json")
    with pytest.raises(ValueError):
        verify(path)
    with pytest.raises(FileNotFoundError):
        verify(tmp_path / "missing.bundle.json")
