from __future__ import annotations

from copy import deepcopy

from app import report_artifacts
from veltrix_v2.reporting.artifact_bundle import build_report_surface_bundle, serialize_portable_report_surface_bundle
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity


def make_report():
    return bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "veltrix-2026-11-14-surface-parity",
        "as_of_date": "2026-11-14",
        "release_mode": "RESTRICTED_PUBLIC",
        "predictions": [{
            "fixture_id": "fixture-1",
            "publication_status": "PUBLISHED",
        }],
    })


def make_dashboard(report):
    return {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": report["as_of_date"],
        "report_id": report["report_id"],
        "report_sha256": report["report_sha256"],
        "status": report.get("status"),
        "release_mode": report.get("release_mode"),
        "predictions": report["predictions"],
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
    bundle = report_artifacts.load_v2_report_bundle(lambda report, identity: report.get('release_mode') in {'RESTRICTED_PUBLIC', 'FULL_PUBLIC'})
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
    assert report_artifacts.load_v2_report_bundle(lambda report, identity: True) is None


def test_dashboard_loader_rejects_report_id_or_hash_drift(monkeypatch):
    report = make_report()
    dashboard = make_dashboard(report)
    dashboard["report_id"] = "different-report"
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: {"report": report, "dashboard": dashboard}.get(kind),
    )
    assert report_artifacts.load_dashboard_snapshot(lambda report, identity: True) is None


def test_legacy_dashboard_without_v2_identity_keeps_existing_loader_contract(monkeypatch):
    dashboard = {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": "2026-11-14",
        "predictions": [],
    }
    monkeypatch.setattr(report_artifacts, "_load", lambda kind: dashboard if kind == "dashboard" else None)
    assert report_artifacts.load_dashboard_snapshot() == dashboard


def test_v2_report_bundle_rejects_website_projection_content_drift(monkeypatch):
    report = make_report()
    dashboard = make_dashboard(report)
    dashboard["predictions"] = [{"fixture_id": "unrelated-fixture"}]
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: {"report": report, "dashboard": dashboard}.get(kind),
    )
    assert report_artifacts.load_v2_report_bundle() is None


def test_v2_website_bundle_is_hidden_without_authoritative_verifier(monkeypatch):
    report = make_report()
    dashboard = make_dashboard(report)
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: {"report": report, "dashboard": dashboard}.get(kind),
    )
    assert report_artifacts.load_v2_report_bundle() is None
    assert report_artifacts.load_dashboard_snapshot() is None


def test_v2_website_bundle_rejects_shadow_report_even_if_verifier_denies(monkeypatch):
    report = make_report()
    report["release_mode"] = "INTERNAL_SHADOW"
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    dashboard = make_dashboard(report)
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: {"report": report, "dashboard": dashboard}.get(kind),
    )
    assert report_artifacts.load_v2_report_bundle(
        lambda value, identity: value.get("release_mode") in {"RESTRICTED_PUBLIC", "FULL_PUBLIC"}
    ) is None


def test_v2_latest_report_requires_authoritative_publication_verifier(monkeypatch):
    report = make_report()
    monkeypatch.setattr(report_artifacts, "_load", lambda kind: report if kind == "report" else None)
    assert report_artifacts.load_latest_report() is None
    assert report_artifacts.load_latest_report(
        lambda value, identity: value.get("release_mode") == "RESTRICTED_PUBLIC"
    ) == report


def test_v2_latest_report_rejects_verifier_false_or_non_boolean_truth(monkeypatch):
    report = make_report()
    monkeypatch.setattr(report_artifacts, "_load", lambda kind: report if kind == "report" else None)
    assert report_artifacts.load_latest_report(lambda *_: False) is None
    assert report_artifacts.load_latest_report(lambda *_: 1) is None


def test_public_website_parser_rejects_internal_shadow_report():
    report = make_report()
    report["release_mode"] = "INTERNAL_SHADOW"
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    assert report_artifacts._parse_snapshot(
        __import__("json").dumps(report).encode(), "report"
    ) is None


def test_public_website_parser_rejects_any_unpublished_fixture():
    report = make_report()
    report["predictions"] = [{"publication_status": "SHADOW_ONLY"}]
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    assert report_artifacts._parse_snapshot(
        __import__("json").dumps(report).encode(), "report"
    ) is None


def test_legacy_current_report_is_not_served_as_a_v2_publication(monkeypatch):
    legacy_report = {
        "status": "PUBLISHED",
        "as_of_date": "2026-11-14",
        "predictions": [{"fixture_id": "legacy-fixture"}],
    }
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: legacy_report if kind == "report" else None,
    )
    assert report_artifacts.load_latest_report() is None


def test_legacy_dashboard_with_forecasts_is_not_served_as_current_v2_data(monkeypatch):
    legacy_dashboard = {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": "2026-11-14",
        "predictions": [{"fixture_id": "legacy-fixture"}],
    }
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: legacy_dashboard if kind == "dashboard" else None,
    )
    assert report_artifacts.load_dashboard_snapshot() is None



def test_website_publication_loader_rejects_empty_duplicate_and_oversized_reports(monkeypatch):
    report = make_report()
    dashboard = make_dashboard(report)

    empty = deepcopy(report)
    empty["predictions"] = []
    empty = bind_report_identity({key: value for key, value in empty.items() if key != "report_sha256"})
    monkeypatch.setattr(report_artifacts, "_load", lambda kind: {"report": empty, "dashboard": make_dashboard(empty)}.get(kind))
    assert report_artifacts.load_v2_report_bundle(lambda *_: True) is None

    duplicate = deepcopy(report)
    duplicate["predictions"].append(dict(duplicate["predictions"][0]))
    duplicate = bind_report_identity({key: value for key, value in duplicate.items() if key != "report_sha256"})
    monkeypatch.setattr(report_artifacts, "_load", lambda kind: {"report": duplicate, "dashboard": make_dashboard(duplicate)}.get(kind))
    assert report_artifacts.load_v2_report_bundle(lambda *_: True) is None

    oversized = deepcopy(report)
    oversized["predictions"] = [
        {"fixture_id": f"fixture-{index}", "publication_status": "PUBLISHED"}
        for index in range(26)
    ]
    oversized = bind_report_identity({key: value for key, value in oversized.items() if key != "report_sha256"})
    monkeypatch.setattr(report_artifacts, "_load", lambda kind: {"report": oversized, "dashboard": make_dashboard(oversized)}.get(kind))
    assert report_artifacts.load_v2_report_bundle(lambda *_: True) is None


def test_website_publication_loader_fails_closed_when_verifier_raises(monkeypatch):
    report = make_report()
    dashboard = make_dashboard(report)
    monkeypatch.setattr(
        report_artifacts,
        "_load",
        lambda kind: {"report": report, "dashboard": dashboard}.get(kind),
    )

    def unavailable_verifier(*_):
        raise RuntimeError("trusted evidence store unavailable")

    assert report_artifacts.load_v2_report_bundle(unavailable_verifier) is None
    assert report_artifacts.load_latest_report(unavailable_verifier) is None



def test_website_loader_accepts_same_verified_portable_bundle_for_all_surfaces():
    report = make_report()
    portable = serialize_portable_report_surface_bundle(build_report_surface_bundle(report))
    bundle = report_artifacts.load_v2_portable_report_bundle(
        portable,
        lambda value, identity: value.get("release_mode") == "RESTRICTED_PUBLIC",
    )
    assert bundle is not None
    assert bundle["report"] == report
    assert bundle["dashboard"]["report_id"] == report["report_id"]
    assert bundle["scheduled"] == report
    assert bundle["telegram"] == report


def test_website_portable_bundle_loader_fails_closed_on_bad_bytes_or_missing_verifier():
    assert report_artifacts.load_v2_portable_report_bundle(b"not-json", lambda *_: True) is None
    report = make_report()
    portable = serialize_portable_report_surface_bundle(build_report_surface_bundle(report))
    assert report_artifacts.load_v2_portable_report_bundle(portable, None) is None
    assert report_artifacts.load_v2_portable_report_bundle(portable, lambda *_: False) is None



def test_invalid_portable_artifact_never_falls_back_to_legacy_report(monkeypatch):
    legacy_report = {
        "status": "PUBLISHED",
        "as_of_date": "2026-11-14",
        "predictions": [{"fixture_id": "legacy-fixture"}],
    }
    monkeypatch.setattr(report_artifacts, "_load_portable_bundle_bytes", lambda: b"not-json")
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: legacy_report if kind == "report" else None,
    )
    assert report_artifacts.load_latest_report(lambda *_: True) is None



def test_portable_bundle_fetch_cache_is_scoped_to_repository_and_branch(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self, size=-1):
            return self.payload if size < 0 else self.payload[:size]

    report = make_report()
    payload = serialize_portable_report_surface_bundle(build_report_surface_bundle(report))
    calls = []
    monkeypatch.setattr(
        report_artifacts,
        "urlopen",
        lambda request, timeout: (calls.append((request.full_url, timeout)) or Response(payload)),
    )
    monkeypatch.setenv("VELTRIX_DATA_REPOSITORY", "Nexora-Apparel/veltrix-football")
    monkeypatch.setenv("VELTRIX_DATA_BRANCH", "command-data")
    report_artifacts._portable_bundle_cache.clear()
    assert report_artifacts._load_portable_bundle_bytes() == payload
    assert report_artifacts._load_portable_bundle_bytes() == payload
    assert len(calls) == 1

    monkeypatch.setenv("VELTRIX_DATA_BRANCH", "another-data-branch")
    assert report_artifacts._load_portable_bundle_bytes() == payload
    assert len(calls) == 2


def test_portable_bundle_fetch_rejects_oversized_remote_artifact(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self, size=-1):
            return b"x" * size

    monkeypatch.setattr(report_artifacts, "urlopen", lambda *_args, **_kwargs: Response())
    monkeypatch.setenv("VELTRIX_DATA_REPOSITORY", "Nexora-Apparel/veltrix-football")
    monkeypatch.setenv("VELTRIX_DATA_BRANCH", "command-data")
    report_artifacts._portable_bundle_cache.clear()
    assert report_artifacts._load_portable_bundle_bytes() is None



def test_portable_v2_dashboard_takes_precedence_over_archived_legacy_snapshot(monkeypatch):
    report = make_report()
    portable = serialize_portable_report_surface_bundle(build_report_surface_bundle(report))
    legacy_dashboard = {
        "snapshot_schema": "VELTRIX_DASHBOARD_V1",
        "as_of_date": "2026-11-13",
        "predictions": [{"fixture_id": "legacy-fixture"}],
    }
    monkeypatch.setattr(report_artifacts, "_load_portable_bundle_bytes", lambda: portable)
    monkeypatch.setattr(report_artifacts, "_load", lambda kind: legacy_dashboard if kind == "dashboard" else None)
    dashboard = report_artifacts.load_dashboard_snapshot(
        lambda value, identity: value.get("release_mode") == "RESTRICTED_PUBLIC"
    )
    assert dashboard is not None
    assert dashboard["report_id"] == report["report_id"]
    assert dashboard["predictions"] == report["predictions"]



def test_latest_website_report_prefers_verified_portable_bundle_over_legacy_report(monkeypatch):
    report = make_report()
    portable = serialize_portable_report_surface_bundle(build_report_surface_bundle(report))
    legacy_report = {
        "status": "PUBLISHED",
        "as_of_date": "2026-11-13",
        "predictions": [{"fixture_id": "legacy-fixture"}],
    }
    monkeypatch.setattr(report_artifacts, "_load_portable_bundle_bytes", lambda: portable)
    monkeypatch.setattr(
        report_artifacts, "_load",
        lambda kind: legacy_report if kind == "report" else None,
    )
    loaded = report_artifacts.load_latest_report(
        lambda value, identity: value.get("release_mode") == "RESTRICTED_PUBLIC"
    )
    assert loaded == report


def test_website_report_bundle_prefers_portable_envelope_and_returns_all_surfaces(monkeypatch):
    report = make_report()
    portable = serialize_portable_report_surface_bundle(build_report_surface_bundle(report))
    monkeypatch.setattr(report_artifacts, "_load_portable_bundle_bytes", lambda: portable)
    monkeypatch.setattr(report_artifacts, "_load", lambda *_: None)
    bundle = report_artifacts.load_v2_report_bundle(
        lambda value, identity: value.get("release_mode") == "RESTRICTED_PUBLIC"
    )
    assert bundle is not None
    assert bundle["report"] == report
    assert bundle["scheduled"] == report
    assert bundle["telegram"] == report
    assert bundle["dashboard"]["report_id"] == report["report_id"]



def test_portable_bundle_fetch_fails_closed_on_unexpected_transport_error(monkeypatch):
    def broken_transport(*_args, **_kwargs):
        raise RuntimeError("transport adapter failed")

    monkeypatch.setattr(report_artifacts, "urlopen", broken_transport)
    monkeypatch.setenv("VELTRIX_DATA_REPOSITORY", "Nexora-Apparel/veltrix-football")
    monkeypatch.setenv("VELTRIX_DATA_BRANCH", "command-data")
    report_artifacts._portable_bundle_cache.clear()
    assert report_artifacts._load_portable_bundle_bytes() is None
