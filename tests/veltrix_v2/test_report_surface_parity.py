from __future__ import annotations

from copy import deepcopy

from app import report_artifacts
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity


def make_report():
    return bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "veltrix-2026-11-14-surface-parity",
        "as_of_date": "2026-11-14",
        "release_mode": "INTERNAL_SHADOW",
        "predictions": [],
    })


def make_dashboard(report):
    return {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": report["as_of_date"],
        "report_id": report["report_id"],
        "report_sha256": report["report_sha256"],
        "predictions": [],
    }


def test_v2_report_snapshot_loader_rejects_tampered_report_hash():
    report = make_report()
    tampered = deepcopy(report)
    tampered["predictions"] = [{"fixture_id": "mutated"}]
    assert report_artifacts._parse_snapshot(
        __import__("json").dumps(tampered).encode(), "report"
    ) is None


def test_v2_report_bundle_accepts_matching_website_projection(monkeypatch):
    report = make_report()
    dashboard = make_dashboard(report)
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: {"report": report, "dashboard": dashboard}.get(kind),
    )
    bundle = report_artifacts.load_v2_report_bundle()
    assert bundle is not None
    assert bundle["report"] == report
    assert bundle["dashboard"] == dashboard
    assert bundle["identity"].report_id == report["report_id"]


def test_v2_report_bundle_rejects_dashboard_from_different_report(monkeypatch):
    report = make_report()
    dashboard = make_dashboard(report)
    dashboard["report_sha256"] = "0" * 64
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: {"report": report, "dashboard": dashboard}.get(kind),
    )
    assert report_artifacts.load_v2_report_bundle() is None


def test_dashboard_loader_rejects_report_id_or_hash_drift(monkeypatch):
    report = make_report()
    dashboard = make_dashboard(report)
    dashboard["report_id"] = "different-report"
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: {"report": report, "dashboard": dashboard}.get(kind),
    )
    assert report_artifacts.load_dashboard_snapshot() is None


def test_legacy_dashboard_without_v2_identity_keeps_existing_loader_contract(monkeypatch):
    dashboard = {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": "2026-11-14",
        "predictions": [],
    }
    monkeypatch.setattr(report_artifacts, "_load", lambda kind: dashboard if kind == "dashboard" else None)
    assert report_artifacts.load_dashboard_snapshot() == dashboard
