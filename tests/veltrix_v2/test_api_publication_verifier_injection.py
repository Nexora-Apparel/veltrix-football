from __future__ import annotations

import pytest

from api import telegram as telegram_api


def test_api_has_no_implicit_publication_verifier(monkeypatch):
    monkeypatch.setattr(telegram_api.app.state, "_state", {}, raising=False)
    assert telegram_api._authoritative_publication_verifier() is None


def test_api_accepts_only_explicit_callable_publication_verifier(monkeypatch):
    monkeypatch.setattr(telegram_api.app.state, "_state", {}, raising=False)
    with pytest.raises(TypeError, match="AUTHORITATIVE_PUBLICATION_VERIFIER_REQUIRED"):
        telegram_api.configure_publication_verifier(None)

    verifier = lambda report, identity: False
    telegram_api.configure_publication_verifier(verifier)
    assert telegram_api._authoritative_publication_verifier() is verifier



def test_dashboard_api_hides_v2_predictions_without_trusted_verifier(monkeypatch):
    monkeypatch.setattr(telegram_api, "_authoritative_publication_verifier", lambda: None)
    monkeypatch.setattr(telegram_api, "load_dashboard_snapshot", lambda verifier=None: None)
    monkeypatch.setattr(telegram_api, "load_latest_report", lambda verifier=None: None)
    result = telegram_api.dashboard_data()
    assert result["status"] == "UNAVAILABLE"
    assert result["predictions"] == []



def test_dashboard_html_has_no_legacy_static_prediction_fallback_or_experimental_labels():
    html = telegram_api.DASHBOARD_HTML
    assert "/api/dashboard-data" in html
    assert "dashboard_snapshot.json" not in html
    assert "daily_predictions.json" not in html
    assert "paper_tracking_ledger.json" not in html
    assert "raw.githubusercontent.com" not in html
    assert "EXPERIMENTAL" not in html
    assert "experimental_" not in html



def test_dashboard_api_counts_only_explicitly_certified_v2_markets(monkeypatch):
    monkeypatch.setattr(telegram_api, "_authoritative_publication_verifier", lambda: (lambda *_: True))
    fixture_rows = [
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
    monkeypatch.setattr(
        telegram_api,
        "load_dashboard_snapshot",
        lambda verifier=None: {
            "snapshot_schema": "VELTRIX_DASHBOARD_V1",
            "as_of_date": telegram_api.datetime.now(telegram_api.ZoneInfo("Africa/Lagos")).date().isoformat(),
            "report_id": "test-report",
            "report_sha256": "a" * 64,
            "predictions": fixture_rows,
        },
    )
    monkeypatch.setattr(telegram_api, "load_latest_report", lambda verifier=None: None)

    result = telegram_api.dashboard_data()
    assert result["status"] == "OK"
    assert result["fixtures_received"] == 2
    assert result["available_forecasts"] == 2
    assert result["unsupported_fixtures"] == 0
    assert result["fixtures_visible"] == 2
    assert result["value_bet_screen"]["status"] == "LOCKED_UNVALIDATED"
    assert result["predictions"][0]["fixture_phase"] == "UPCOMING"
    assert result["predictions"][0]["kickoff_local"] == "19:00 WAT"



def test_telegram_webhook_routes_commands_only_through_v2_renderer():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "api" / "telegram.py").read_text(encoding="utf-8")
    assert "from veltrix_v2.reporting.telegram_commands import handle_v2_command" in source
    assert "from app.telegram_commands import handle_command" not in source
    assert "handle_v2_command(" in source
    assert "handle_command(" not in source
