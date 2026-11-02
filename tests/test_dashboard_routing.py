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
    assert 'id="valueValidation"' in response.body.decode("utf-8")
    assert "Value validation" in response.body.decode("utf-8")
    assert "Prospective " in response.body.decode("utf-8")
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
            "markets": ["1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"],
            "candidate_count": 0,
        },
    }
    monkeypatch.setattr(telegram, "load_latest_report", lambda: report)
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)
    payload = telegram.dashboard_data()
    assert payload["value_bet_screen"]["status"] == "DISABLED_UNVALIDATED"
    assert payload["value_bet_screen"]["markets"] == ["1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"]
    assert payload["value_validation_certificate"]["status"] == "LOCKED_INSUFFICIENT_EVIDENCE"
    assert payload["value_validation_certificate"]["alerts_enabled"] is False


def test_dashboard_data_exposes_published_validation_certificate(monkeypatch):
    from api import telegram

    certificate = {
        "status": "PARTIALLY_VALIDATED",
        "approved_markets": ["BTTS"],
        "alerts_enabled": True,
        "market_diagnostics": {"BTTS": {"status": "PASS"}},
    }
    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2026-10-30",
        "predictions": [],
        "value_validation_certificate": certificate,
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)
    payload = telegram.dashboard_data()
    assert payload["value_validation_certificate"] == certificate



def test_dashboard_exposes_calibration_coverage_and_versioned_value_ledger(monkeypatch):
    from api import telegram

    calibration = {
        "status": "NO_COMPATIBLE_FORECASTS",
        "compatible_forecasts": 0,
        "applied_forecasts": 0,
        "markets": [],
    }
    ledger = {
        "model_status": "PAPER_TRACKING_ONLY",
        "evaluated_report_dates": 4,
        "value_market_metrics_by_market": {"1x2": {"settled_bets": 2}},
        "value_validation_markets_by_model_version": {"experimental_recent_goals_poisson": {"1X2": {"settled_bets": 2}}},
        "value_validation_markets_by_calibration_version": {},
        "value_model_versions": ["experimental_recent_goals_poisson"],
        "calibration_versions": [],
        "scored_matches": [],
    }
    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2026-10-30",
        "predictions": [],
        "goal_market_calibration": calibration,
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: ledger)
    payload = telegram.dashboard_data()
    assert payload["goal_market_calibration"] == calibration
    assert payload["paper_tracking"]["value_market_metrics_by_market"] == {"1x2": {"settled_bets": 2}}
    assert payload["paper_tracking"]["value_model_versions"] == ["experimental_recent_goals_poisson"]
    assert payload["paper_tracking"]["value_validation_markets_by_model_version"]["experimental_recent_goals_poisson"]["1X2"]["settled_bets"] == 2


def test_dashboard_keeps_future_unsupported_fixtures_visible(monkeypatch):
    from api import telegram

    rows = [
        {
            "home_team": "Supported FC", "away_team": "Visitor FC",
            "status": "EXPERIMENTAL_ONLY", "kickoff_local": "2099-05-01T15:00:00+01:00",
            "probabilities": {"home_win": 0.4, "draw": 0.3, "away_win": 0.3},
        },
        {
            "home_team": "Unsupported FC", "away_team": "Guest FC",
            "status": "UNSUPPORTED_COMPETITION", "kickoff_local": "2099-05-01T17:00:00+01:00",
        },
        {
            "home_team": "History Gap FC", "away_team": "No Data FC",
            "status": "INSUFFICIENT_HISTORY", "kickoff_local": "2099-05-01T19:00:00+01:00",
        },
    ]
    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2099-05-01",
        "predictions": rows,
        "fixtures_received": 3,
        "fixtures_with_market_odds": 0,
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)

    payload = telegram.dashboard_data()
    assert payload["fixtures_visible"] == 3
    assert payload["experimental_forecasts"] == 1
    assert payload["unsupported_fixtures"] == 2
    assert [row["status"] for row in payload["predictions"]] == [
        "EXPERIMENTAL_ONLY", "UNSUPPORTED_COMPETITION", "INSUFFICIENT_HISTORY"
    ]
    assert "probabilities" not in payload["predictions"][1]
    assert "probabilities" not in payload["predictions"][2]


def test_dashboard_market_odds_count_uses_actual_fixture_quote_rows(monkeypatch):
    from api import telegram

    rows = [
        {
            "home_team": "Quoted FC", "away_team": "Visitor FC",
            "status": "EXPERIMENTAL_ONLY",
            "kickoff_local": "2099-05-01T15:00:00+01:00",
            "the_odds_api_market_odds": {
                "markets": {"h2h": [{"bookmaker": "Example", "outcomes": []}]},
            },
        },
        {
            "home_team": "No Quote FC", "away_team": "Guest FC",
            "status": "UNSUPPORTED_COMPETITION",
            "kickoff_local": "2099-05-01T17:00:00+01:00",
        },
    ]
    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2099-05-01",
        "predictions": rows,
        "fixtures_received": 2,
        "fixtures_with_market_odds": 0,
        "live_odds_sync": {"fixtures_with_market_odds": 9},
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)

    payload = telegram.dashboard_data()
    assert payload["fixtures_with_market_odds"] == 1
    assert payload["fixtures_visible"] == 2
