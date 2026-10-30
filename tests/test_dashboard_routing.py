from api.dashboard import dashboard
from api.dashboard_data import get_dashboard_data


def test_dashboard_root_handler_returns_html():
    response = dashboard()
    assert response.status_code == 200
    assert "VELTRIX FOOTBALL" in response.body.decode("utf-8")
    assert "Command Centre" in response.body.decode("utf-8")
    assert "their coverage is not assumed complete" in response.body.decode("utf-8")
    assert "Football data by" in response.body.decode("utf-8")
    assert "BTTS Yes" in response.body.decode("utf-8")
    assert "The Odds API" in response.body.decode("utf-8")
    assert 'id="trackingView"' in response.body.decode("utf-8")
    assert 'data-view="trackingView"' in response.body.decode("utf-8")
    assert ".sectionview.active{display:block}" in response.body.decode("utf-8")


def test_dashboard_data_handler_returns_json(monkeypatch):
    import api.telegram

    monkeypatch.setattr(api.telegram, "load_paper_ledger", lambda: {
        "model_status": "PAPER_TRACKING_ONLY",
        "evaluated_report_dates": 2,
        "cumulative_metrics_by_model": {},
        "scored_matches": [],
    })
    monkeypatch.setattr(api.telegram, "load_latest_report", lambda: {
        "as_of_date": "2026-10-27",
        "generated_at_utc": "2026-10-27T04:00:00+00:00",
        "predictions": [],
        "fixtures_received": 0,
        "fixtures_with_market_odds": 0,
    })
    payload = get_dashboard_data()
    assert payload["status"] == "OK"
    assert payload["as_of_date"] == "2026-10-27"
    assert payload["predictions"] == []
    assert payload["paper_tracking"]["model_status"] == "PAPER_TRACKING_ONLY"


def test_dashboard_data_exposes_value_screen_status_and_market_coverage(monkeypatch):
    """Release gate for visible all-market value coverage without live picks and explicit corrected-report resend."""
    from api import telegram

    report = {
        "as_of_date": "2026-10-30",
        "generated_at_utc": "2026-10-30T12:00:00+00:00",
        "command_data_publication": "PUBLISHED",
        "predictions": [],
        "value_bet_screen": {
            "status": "DISABLED_UNVALIDATED",
            "model_validated": False,
            "markets": ["1X2", "BTTS", "OVER_UNDER_2_5"],
            "candidate_count": 0,
        },
    }
    monkeypatch.setattr(telegram, "load_latest_report", lambda: report)
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)
    payload = telegram.dashboard_data()
    assert payload["value_bet_screen"]["status"] == "DISABLED_UNVALIDATED"
    assert payload["value_bet_screen"]["markets"] == ["1X2", "BTTS", "OVER_UNDER_2_5"]
