from __future__ import annotations

import pytest

from scripts.veltrix_v2.verify_report_surface_bundle import verify
from veltrix_v2.reporting.artifact_bundle import build_report_surface_bundle, persist_report_surface_bundle
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA


def source_report():
    return {
        "schema": REPORT_SCHEMA,
        "report_id": "verify-bundle-2026-11-14",
        "as_of_date": "2026-11-14",
        "release_mode": "INTERNAL_SHADOW",
        "status": "SHADOW_ONLY",
        "predictions": [],
    }


def test_cli_verifier_confirms_all_surfaces_without_side_effects(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    persist_report_surface_bundle(bundle, tmp_path)
    result = verify(tmp_path, bundle.identity.report_id)
    assert result["status"] == "REPORT_SURFACE_BUNDLE_VERIFIED"
    assert result["surfaces_verified"] == ["canonical", "scheduled", "telegram", "website"]
    assert result["side_effects"] == {
        "provider_requests": 0,
        "database_writes": 0,
        "telegram_messages": 0,
        "schedule_activation": 0,
        "publications": 0,
    }


def test_cli_verifier_fails_closed_when_surface_is_missing(tmp_path):
    with pytest.raises(ValueError, match="REPORT_BUNDLE_COMMIT_MARKER_MISSING"):
        verify(tmp_path, "missing-report")
