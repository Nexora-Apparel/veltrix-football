from __future__ import annotations

import json

import pytest

from veltrix_v2.reporting.artifact_bundle import (
    ReportSurfaceBundle,
    build_report_surface_bundle,
    load_authorized_scheduled_report,
    load_report_surface_bundle,
    persist_report_surface_bundle,
)
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, ReportIdentity


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


def test_bundle_reader_verifies_all_four_persisted_surfaces(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    persist_report_surface_bundle(bundle, tmp_path)
    loaded = load_report_surface_bundle(tmp_path, bundle.identity.report_id)
    assert loaded.identity == bundle.identity
    assert loaded.canonical_report == loaded.scheduled_report == loaded.telegram_report
    assert loaded.website_projection["report_sha256"] == loaded.identity.report_sha256


def test_bundle_reader_rejects_tampered_telegram_artifact(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    paths = persist_report_surface_bundle(bundle, tmp_path)
    changed = json.loads(paths["telegram"].read_text())
    changed["predictions"][0]["publication_status"] = "PUBLISHED"
    paths["telegram"].write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="REPORT_BUNDLE_COMMIT_HASH_MISMATCH"):
        load_report_surface_bundle(tmp_path, bundle.identity.report_id)


def test_bundle_reader_rejects_website_projection_content_drift(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    paths = persist_report_surface_bundle(bundle, tmp_path)
    changed = json.loads(paths["dashboard"].read_text())
    changed["predictions"] = [{"fixture_id": "different"}]
    paths["dashboard"].write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="REPORT_BUNDLE_COMMIT_HASH_MISMATCH"):
        load_report_surface_bundle(tmp_path, bundle.identity.report_id)


def test_scheduled_consumer_returns_only_the_authorized_scheduled_copy(tmp_path):
    bundle = build_report_surface_bundle(public_source_report())
    persist_report_surface_bundle(bundle, tmp_path)
    authorized_report = load_authorized_scheduled_report(
        tmp_path,
        bundle.identity.report_id,
        lambda report, identity: report.get("release_mode") == "RESTRICTED_PUBLIC",
    )
    assert authorized_report == bundle.scheduled_report


def test_scheduled_consumer_rejects_missing_or_failed_publication_verifier(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    persist_report_surface_bundle(bundle, tmp_path)
    with pytest.raises(PermissionError, match="NON_PUBLIC_FORECASTS"):
        load_authorized_scheduled_report(
            tmp_path, bundle.identity.report_id, lambda *_: True
        )
    public_bundle = build_report_surface_bundle(public_source_report())
    persist_report_surface_bundle(public_bundle, tmp_path)
    with pytest.raises(PermissionError, match="VERIFIER_REQUIRED"):
        load_authorized_scheduled_report(
            tmp_path, public_bundle.identity.report_id, None
        )
    with pytest.raises(PermissionError, match="AUTHORIZATION_NOT_VERIFIED"):
        load_authorized_scheduled_report(
            tmp_path, public_bundle.identity.report_id, lambda *_: False
        )


def public_source_report():
    return {
        "schema": REPORT_SCHEMA,
        "report_id": "veltrix-daily-2026-11-14-public",
        "as_of_date": "2026-11-14",
        "release_mode": "RESTRICTED_PUBLIC",
        "status": "PUBLISHED",
        "predictions": [
            {"fixture_id": "fx-1", "publication_status": "PUBLISHED", "certified_markets": ["1X2"]},
        ],
    }


def test_persistence_rejects_bundle_identity_drift_before_writing(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    wrong_identity = ReportIdentity(
        report_id="different-report-id",
        as_of_date=bundle.identity.as_of_date,
        report_sha256=bundle.identity.report_sha256,
    )
    invalid = ReportSurfaceBundle(
        bundle.canonical_report,
        bundle.scheduled_report,
        bundle.telegram_report,
        bundle.website_projection,
        wrong_identity,
    )
    with pytest.raises(ValueError, match="REPORT_SURFACE_BUNDLE_IDENTITY_MISMATCH"):
        persist_report_surface_bundle(invalid, tmp_path)
    assert not list(tmp_path.rglob("*.json"))



def test_publication_consumer_rejects_empty_fixture_bundle(tmp_path):
    report = public_source_report()
    report["report_id"] = "veltrix-daily-2026-11-14-empty"
    report["predictions"] = []
    bundle = build_report_surface_bundle(report)
    persist_report_surface_bundle(bundle, tmp_path)
    with pytest.raises(PermissionError, match="NON_PUBLIC_FORECASTS"):
        load_authorized_scheduled_report(
            tmp_path, bundle.identity.report_id, lambda *_: True
        )



def test_bundle_reader_rejects_artifacts_without_final_commit_marker(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    paths = persist_report_surface_bundle(bundle, tmp_path)
    marker = tmp_path / "bundles" / f"{bundle.identity.report_id}.commit.json"
    marker.unlink()
    with pytest.raises(ValueError, match="COMMIT_MARKER_MISSING"):
        load_report_surface_bundle(tmp_path, bundle.identity.report_id)


def test_bundle_reader_rejects_partial_or_replaced_artifact_after_commit(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    paths = persist_report_surface_bundle(bundle, tmp_path)
    paths["scheduled"].unlink()
    with pytest.raises(ValueError, match="REPORT_BUNDLE_ARTIFACT_MISSING:scheduled"):
        load_report_surface_bundle(tmp_path, bundle.identity.report_id)


def test_bundle_reader_checks_commit_marker_artifact_hashes(tmp_path):
    bundle = build_report_surface_bundle(source_report())
    persist_report_surface_bundle(bundle, tmp_path)
    marker = tmp_path / "bundles" / f"{bundle.identity.report_id}.commit.json"
    commit = json.loads(marker.read_text())
    commit["artifacts"]["telegram"] = "0" * 64
    marker.write_text(json.dumps(commit))
    with pytest.raises(ValueError, match="COMMIT_HASH_MISMATCH"):
        load_report_surface_bundle(tmp_path, bundle.identity.report_id)



def test_interrupted_four_surface_write_is_invisible_until_commit_marker(tmp_path, monkeypatch):
    from veltrix_v2.reporting import artifact_bundle

    bundle = build_report_surface_bundle(source_report())
    original_write = artifact_bundle._write_immutable
    writes = {"count": 0}

    def fail_before_dashboard_or_commit(path, payload):
        writes["count"] += 1
        if writes["count"] == 4:
            raise OSError("simulated interruption before final artifact")
        return original_write(path, payload)

    monkeypatch.setattr(artifact_bundle, "_write_immutable", fail_before_dashboard_or_commit)
    with pytest.raises(OSError, match="simulated interruption"):
        persist_report_surface_bundle(bundle, tmp_path)

    with pytest.raises(ValueError, match="COMMIT_MARKER_MISSING"):
        load_report_surface_bundle(tmp_path, bundle.identity.report_id)

    monkeypatch.setattr(artifact_bundle, "_write_immutable", original_write)
    persist_report_surface_bundle(bundle, tmp_path)
    loaded = load_report_surface_bundle(tmp_path, bundle.identity.report_id)
    assert loaded.identity == bundle.identity
