from __future__ import annotations

import json

import pytest

from veltrix_v2.reporting.artifact_bundle import (
    build_report_surface_bundle,
    persist_report_surface_bundle,
)
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA


def source_report():
    return {
        "schema": REPORT_SCHEMA,
        "report_id": "veltrix-daily-2026-11-14-r1",
        "as_of_date": "2026-11-14",
        "release_mode": "INTERNAL_SHADOW",
        "status": "SHADOW_ONLY",
        "predictions": [
            {"fixture_id": "fx-1", "publication_status": "SHADOW_ONLY"},
        ],
    }


def test_bundle_binds_website_scheduler_and_telegram_to_same_report():
    bundle = build_report_surface_bundle(source_report())
    assert bundle.canonical_report["report_sha256"] == bundle.scheduled_report["report_sha256"]
    assert bundle.canonical_report["report_sha256"] == bundle.telegram_report["report_sha256"]
    assert bundle.website_projection["report_id"] == bundle.identity.report_id
    assert bundle.website_projection["report_sha256"] == bundle.identity.report_sha256


def test_persisted_surface_files_share_one_canonical_report_hash(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    paths = persist_report_surface_bundle(bundle, tmp_path)
    canonical = json.loads(paths["canonical"].read_text())
    scheduled = json.loads(paths["scheduled"].read_text())
    telegram = json.loads(paths["telegram"].read_text())
    dashboard = json.loads(paths["dashboard"].read_text())
    assert canonical == scheduled == telegram
    assert dashboard["report_id"] == canonical["report_id"]
    assert dashboard["report_sha256"] == canonical["report_sha256"]


def test_persistence_is_idempotent_for_identical_bundle(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    first = persist_report_surface_bundle(bundle, tmp_path)
    second = persist_report_surface_bundle(bundle, tmp_path)
    assert first == second
    assert all(path.exists() for path in first.values())


def test_same_report_id_with_changed_content_cannot_overwrite_artifacts(tmp_path):
    first = build_report_surface_bundle(source_report())
    persist_report_surface_bundle(first, tmp_path)
    changed = source_report()
    changed["predictions"][0]["publication_status"] = "PUBLISHED"
    second = build_report_surface_bundle(changed)
    with pytest.raises(ValueError, match="IMMUTABLE_CONFLICT"):
        persist_report_surface_bundle(second, tmp_path)


def test_bundle_rejects_tampered_prehashed_report():
    report = source_report()
    report["report_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="content hash"):
        build_report_surface_bundle(report)
