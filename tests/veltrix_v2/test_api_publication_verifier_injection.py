from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import pytest
import sys
import types

from api import telegram as telegram_api
from veltrix_v2.reporting.artifact_bundle import (
    build_report_surface_bundle,
    serialize_portable_report_surface_bundle,
)
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA


@pytest.fixture(autouse=True)
def reset_api_state():
    telegram_api.app.state._state.clear()


def _portable_bundle_bytes():
    as_of = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
    fixtures = [
        {
            "fixture_id": "fixture-btts",
            "publication_status": "PUBLISHED",
            "certified_markets": ["BTTS"],
            "markets": {"BTTS": {"yes": 0.56, "no": 0.44}},
            "home_team": "Alpha",
            "away_team": "Beta",
            "competition_name": "Example League",
            "kickoff_utc": "2099-11-14T18:00:00+00:00",
            "kickoff_wat": "19:00 WAT",
        },
        {
            "fixture_id": "fixture-1x2",
            "publication_status": "PUBLISHED",
            "certified_markets": ["1X2"],
            "markets": {"1X2": {"home": 0.48, "draw": 0.27, "away": 0.25}},
            "home_team": "Gamma",
            "away_team": "Delta",
            "competition_name": "Example League",
            "kickoff_utc": "2099-11-14T19:00:00+00:00",
            "kickoff_wat": "20:00 WAT",
        },
    ]
    report = {
        "schema": REPORT_SCHEMA,
        "report_id": "test-report",
        "as_of_date": as_of,
        "status": "PUBLISHED",
        "release_mode": "FULL_PUBLIC",
        "generated_at_utc": "2099-11-14T05:00:00Z",
        "published_at_utc": "2099-11-14T05:01:00Z",
        "publication_notice": "Verified V2 test report",
        "command_data_publication": "PUBLISHED",
        "primary_provider_request": {"provider": "5DollarFootballAPI", "status": "SUCCESS"},
        "fixture_discovery": {"retrieved": 2},
        "multi_source_odds_sync": {"status": "NOT_CONFIGURED"},
        "live_odds_sync": {"status": "NOT_CONFIGURED"},
        "historical_data_coverage": {"status": "RESEARCH_ONLY"},
        "fixtures_with_market_odds": 0,
        "model_validation": {"status": "NOT_CERTIFIED"},
        "goal_market_calibration": {"status": "NOT_REPORTED"},
        "predictions": fixtures,
    }
    bundle = build_report_surface_bundle(report)
    return serialize_portable_report_surface_bundle(bundle)


def test_api_has_no_implicit_publication_verifier_or_bundle_reader():
    assert telegram_api._authoritative_publication_verifier() is None
    assert telegram_api._authoritative_report_bundle_reader() is None


def test_api_accepts_only_explicit_callable_publication_and_bundle_dependencies():
    with pytest.raises(TypeError, match="AUTHORITATIVE_PUBLICATION_VERIFIER_REQUIRED"):
        telegram_api.configure_publication_verifier(None)
    with pytest.raises(TypeError, match="AUTHORITATIVE_REPORT_BUNDLE_READER_REQUIRED"):
        telegram_api.configure_report_bundle_reader(None)

    verifier = lambda report, identity: False
    reader = lambda: b"not-a-valid-bundle"
    telegram_api.configure_publication_verifier(verifier)
    telegram_api.configure_report_bundle_reader(reader)
    assert telegram_api._authoritative_publication_verifier() is verifier
    assert telegram_api._authoritative_report_bundle_reader() is reader


def test_report_bundle_url_reader_rejects_non_command_data_sources():
    with pytest.raises(ValueError, match="PORTABLE_REPORT_BUNDLE_URL_NOT_ALLOWLISTED"):
        telegram_api.configure_report_bundle_reader_from_url(
            "https://example.com/report.bundle.json"
        )
    with pytest.raises(ValueError, match="PORTABLE_REPORT_BUNDLE_URL_NOT_ALLOWLISTED"):
        telegram_api.configure_report_bundle_reader_from_url(
            "https://raw.githubusercontent.com/other/repository/main/public-data/bundle.json"
        )


def test_dashboard_api_hides_v2_predictions_without_both_trusted_dependencies():
    calls = []
    telegram_api.configure_report_bundle_reader(lambda: calls.append("read") or _portable_bundle_bytes())
    result = telegram_api.dashboard_data()
    assert result["status"] == "UNAVAILABLE"
    assert result["predictions"] == []
    assert calls == []


def test_dashboard_html_has_no_legacy_static_prediction_fallback_or_experimental_labels():
    html = telegram_api.DASHBOARD_HTML
    assert "/api/dashboard-data" in html
    assert "dashboard_snapshot.json" not in html
    assert "daily_predictions.json" not in html
    assert "paper_tracking_ledger.json" not in html
    assert "raw.githubusercontent.com" not in html
    assert "EXPERIMENTAL" not in html
    assert "experimental_" not in html
    assert "Football data by" in html
    assert "https://5dollarfootballapi.com" in html


def test_dashboard_api_reads_the_authorized_website_surface_from_the_portable_bundle():
    raw = _portable_bundle_bytes()
    telegram_api.configure_publication_verifier(lambda report, identity: True)
    telegram_api.configure_report_bundle_reader(lambda: raw)

    result = telegram_api.dashboard_data()
    assert result["status"] == "OK"
    assert result["fixtures_received"] == 2
    assert result["available_forecasts"] == 2
    assert result["unsupported_fixtures"] == 0
    assert result["fixtures_visible"] == 2
    assert result["model_validation"]["status"] == "NOT_CERTIFIED"
    assert result["report_freshness_note"] == "Verified V2 test report"
    assert result["data_attribution"] == {
        "text": "Football data by 5DollarFootballAPI",
        "url": "https://5dollarfootballapi.com",
    }
    assert result["value_bet_screen"]["status"] == "LOCKED_UNVALIDATED"
    assert result["predictions"][0]["fixture_phase"] == "UPCOMING"
    assert result["predictions"][0]["kickoff_local"] == "19:00 WAT"


def test_website_and_telegram_surfaces_are_loaded_from_the_same_authorized_bundle():
    raw = _portable_bundle_bytes()
    telegram_api.configure_publication_verifier(lambda report, identity: True)
    telegram_api.configure_report_bundle_reader(lambda: raw)

    bundle = telegram_api._load_authorized_v2_report_bundle()
    assert bundle is not None
    assert bundle.website_projection["report_id"] == bundle.telegram_report["report_id"]
    assert bundle.website_projection["report_sha256"] == bundle.telegram_report["report_sha256"]
    assert bundle.telegram_report["predictions"] == bundle.canonical_report["predictions"]


def test_telegram_webhook_routes_commands_only_through_v2_bundle_renderer():
    source = (Path(__file__).resolve().parents[2] / "api" / "telegram.py").read_text(encoding="utf-8")
    assert "from veltrix_v2.reporting.telegram_commands import handle_v2_command" in source
    assert "from app.telegram_commands import handle_command" not in source
    assert "_load_authorized_v2_report_bundle()" in source
    assert "bundle.telegram_report" in source
    assert "load_latest_report" not in source
    assert "handle_v2_command(" in source
    assert "handle_command(" not in source


def test_fixed_current_bundle_pointer_is_an_allowlisted_runtime_source():
    telegram_api.configure_report_bundle_reader_from_url(
        "https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/"
        "command-data/public-data/v2_report_bundle.json"
    )
    assert callable(telegram_api._authoritative_report_bundle_reader())


def test_runtime_configuration_requires_both_factory_and_bundle_url():
    assert telegram_api.configure_v2_publication_from_environment({}) is False
    assert telegram_api.app.state.v2_publication_runtime_status == "UNCONFIGURED"

    assert telegram_api.configure_v2_publication_from_environment({
        "VELTRIX_V2_PUBLICATION_VERIFIER_FACTORY": "veltrix_v2.fake_runtime:build",
    }) is False
    assert telegram_api.app.state.v2_publication_runtime_status == "BLOCKED"


def test_runtime_configuration_loads_one_trusted_factory_and_shared_bundle(monkeypatch):
    module = types.ModuleType("veltrix_v2.fake_runtime")
    verifier = lambda report, identity: False
    module.build = lambda: verifier
    monkeypatch.setitem(sys.modules, "veltrix_v2.fake_runtime", module)
    environment = {
        "VELTRIX_V2_PUBLICATION_VERIFIER_FACTORY": "veltrix_v2.fake_runtime:build",
        "VELTRIX_V2_REPORT_BUNDLE_URL": (
            "https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/"
            "command-data/public-data/v2_report_bundle.json"
        ),
    }
    assert telegram_api.configure_v2_publication_from_environment(environment) is True
    assert telegram_api._authoritative_publication_verifier() is verifier
    assert callable(telegram_api._authoritative_report_bundle_reader())
    assert telegram_api.app.state.v2_publication_runtime_status == "READY"


def test_runtime_factory_must_live_under_veltrix_v2_namespace():
    assert telegram_api.configure_v2_publication_from_environment({
        "VELTRIX_V2_PUBLICATION_VERIFIER_FACTORY": "os:path",
        "VELTRIX_V2_REPORT_BUNDLE_URL": (
            "https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/"
            "command-data/public-data/v2_report_bundle.json"
        ),
    }) is False
    assert telegram_api.app.state.v2_publication_runtime_status == "BLOCKED"


def test_dashboard_hides_predictions_until_prediction_tab_and_reports_paused_schedule():
    html = telegram_api.DASHBOARD_HTML
    dashboard = html.split('<section id="dashboardView"', 1)[1].split("</section>", 1)[0]
    assert "Publication overview" in dashboard
    assert "Predictions are not shown on Dashboard." in dashboard
    assert "Featured prediction" not in dashboard
    assert "Prediction</a>" in html
    assert "06:00 WAT" not in html
    assert "scheduled for 06:00" not in html
