from api.dashboard import dashboard
from api.dashboard_data import get_dashboard_data

import pytest


@pytest.fixture(autouse=True)
def isolate_dashboard_data_source(monkeypatch):
    """Keep routing tests deterministic; each test supplies its own report."""
    import api.telegram

    monkeypatch.setattr(api.telegram, "load_dashboard_snapshot", lambda: None)



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
    assert "Model validation" in response.body.decode("utf-8")
    assert "BTTS / totals calibration" in response.body.decode("utf-8")
    assert "Historical source rights" in response.body.decode("utf-8")
    assert "Unresolved historical dates" in response.body.decode("utf-8")
    assert 'data-history-filter="wins"' in response.body.decode("utf-8")
    assert 'data-history-filter="losses"' in response.body.decode("utf-8")
    assert 'id="historyDateSort"' in response.body.decode("utf-8")
    assert "Newest first" in response.body.decode("utf-8")
    assert "Oldest first" in response.body.decode("utf-8")
    assert "match_date" in response.body.decode("utf-8")
    assert "Prospective " in response.body.decode("utf-8")
    assert 'data-view="trackingView"' in response.body.decode("utf-8")
    assert ".sectionview.active{display:block}" in response.body.decode("utf-8")
    assert "CONNECTED · STALE DATA" in response.body.decode("utf-8")
    assert "DATA OFFLINE" in response.body.decode("utf-8")
    assert "multi_source_odds_sync" in response.body.decode("utf-8")
    assert "fixture_phase==='UPCOMING'" in response.body.decode("utf-8")
    assert "fixtures retained without forecasts" in response.body.decode("utf-8")
    assert "Selected fixture sources" in response.body.decode("utf-8")
    assert "fetchDashboardPayload" in response.body.decode("utf-8")
    assert "raw.githubusercontent.com/Nexora-Apparel/veltrix-football/command-data/public-data/dashboard_snapshot.json" in response.body.decode("utf-8")
    assert "fetchWithDeadline" in response.body.decode("utf-8")
    assert "cdn.jsdelivr.net/gh/Nexora-Apparel/veltrix-football@command-data/public-data/dashboard_snapshot.json" in response.body.decode("utf-8")
    assert "api.github.com/repos/Nexora-Apparel/veltrix-football/contents/public-data/dashboard_snapshot.json" in response.body.decode("utf-8")



def test_tracking_history_renderer_is_safe_and_keeps_complete_fixture_history():
    from api.telegram import DASHBOARD_HTML
    import api.telegram

    renderer = DASHBOARD_HTML.split("function renderPaperTracking(d){", 1)[1].split(
        "\nfunction renderStatus(d){", 1
    )[0]
    assert renderer.index("const dayOf=") < renderer.index("const seenFixtures")
    assert "button.dataset.historyFilter" in renderer
    assert "button.dataset.history-filter" not in renderer
    assert '"fixture_id": row.get("fixture_id")' in api.telegram.dashboard_data.__code__.co_consts or (
        '"fixture_id": row.get("fixture_id")' in open("api/telegram.py", encoding="utf-8").read()
    )
    assert 'for row in (ledger.get("scored_matches") or [])[-12:]' not in open(
        "api/telegram.py", encoding="utf-8"
    ).read()


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
        "command_data_publication": "PUBLISHED",
        "primary_provider_request": {"provider": "5DollarFootballAPI", "status": "SUCCESS"},
        "multi_source_odds_sync": {
            "five_dollar": {"status": "AVAILABLE"},
            "the_odds_api": {"status": "AVAILABLE"},
        },
        "fixture_discovery": {
            "primary_provider": "5DollarFootballAPI",
            "the_odds_api": {"fixtures_added": 1},
            "infersports": {"events_received": 5, "fixtures_added": 3},
            "fixture_selection": {"by_source_after_cap": {"InferSports": 3, "The Odds API": 1}},
        },
    })
    payload = get_dashboard_data()
    assert payload["status"] == "OK"
    assert payload["as_of_date"] == "2026-10-27"
    assert payload["predictions"] == []
    assert payload["paper_tracking"]["model_status"] == "PAPER_TRACKING_ONLY"
    assert payload["data_connection"]["status"] == "CONNECTED"
    assert payload["data_connection"]["freshness"] == "STALE"
    assert payload["multi_source_odds_sync"]["five_dollar"]["status"] == "AVAILABLE"
    assert payload["multi_source_odds_sync"]["the_odds_api"]["status"] == "AVAILABLE"
    assert payload["fixture_discovery"]["infersports"]["fixtures_added"] == 3
    assert payload["fixture_discovery"]["fixture_selection"]["by_source_after_cap"]["InferSports"] == 3


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
    assert payload["value_bet_screen"]["status"] == "PAPER_ONLY_CANDIDATES"
    assert payload["value_bet_screen"]["markets"] == ["1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"]
    assert payload["value_validation_certificate"]["status"] == "LOCKED_SOURCE_ATTESTATION_REQUIRED"
    assert payload["value_validation_certificate"]["alerts_enabled"] is False


def test_dashboard_data_rejects_forged_report_certificate_and_value_screen(monkeypatch):
    from api import telegram

    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2026-10-30",
        "predictions": [],
        "value_validation_certificate": {
            "status": "PARTIALLY_VALIDATED", "approved_markets": ["BTTS"],
            "alerts_enabled": True, "betting_validation": True,
        },
        "value_bet_screen": {
            "status": "CANDIDATES_FOUND", "candidate_count": 999,
            "alerts_enabled": True, "model_validated": True,
        },
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)
    payload = telegram.dashboard_data()
    assert payload["value_validation_certificate"]["status"] == "LOCKED_SOURCE_ATTESTATION_REQUIRED"
    assert payload["value_validation_certificate"]["approved_markets"] == []
    assert payload["value_validation_certificate"]["alerts_enabled"] is False
    assert payload["value_bet_screen"]["status"] == "PAPER_ONLY_CANDIDATES"
    assert payload["value_bet_screen"]["candidate_count"] == 0
    assert payload["value_bet_screen"]["alerts_enabled"] is False



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
    assert payload["available_forecasts"] == 1
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
                "markets": {"h2h": [{"bookmaker": "Example", "outcomes": [{"name": "Home", "price": 2.1}]}]},
            },
        },
        {
            "home_team": "No Quote FC", "away_team": "Guest FC",
            "status": "UNSUPPORTED_COMPETITION",
            "kickoff_local": "2099-05-01T17:00:00+01:00",
        },
        {
            "home_team": "Past FC", "away_team": "Visitor FC",
            "status": "UNSUPPORTED_COMPETITION",
            "kickoff_local": "2020-05-01T15:00:00+01:00",
        },
    ]
    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2099-05-01",
        "predictions": rows,
        "fixtures_received": 3,
        "fixtures_with_market_odds": 0,
        "live_odds_sync": {"fixtures_with_market_odds": 9},
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)

    payload = telegram.dashboard_data()
    assert payload["fixtures_with_market_odds"] == 1
    assert payload["fixtures_visible"] == 3
    assert payload["unsupported_fixtures"] == 2
    assert payload["predictions"][-1]["fixture_phase"] == "KICKOFF_PASSED"
    assert "remains visible" in payload["predictions"][-1]["fixture_visibility_note"]

# Controlled same-day report replay trigger [reuse-report-40175707059].

# Live verification trigger: exercise today's fixture, publication and delivery pipeline.


def test_dashboard_exposes_reused_snapshot_separately_from_successful_publication(monkeypatch):
    from api import telegram

    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2026-11-02",
        "generated_at_utc": "2026-11-02T09:28:34+00:00",
        "command_data_publication": "PUBLISHED",
        "publication_status": "REUSED_SNAPSHOT_NOT_REFRESHED",
        "publication_notice": "A saved same-day snapshot was reused; no fresh fixture retrieval completed.",
        "predictions": [],
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)

    payload = telegram.dashboard_data()
    assert payload["publication_status"] == "PUBLISHED"
    assert payload["report_generation_status"] == "REUSED_SNAPSHOT_NOT_REFRESHED"
    assert "no fresh fixture retrieval" in payload["report_freshness_note"]

# Controlled live report and Telegram end-to-end verification [run-live-verification].


def test_dashboard_exposes_model_validation_evidence(monkeypatch):
    from api import telegram

    validation = {
        "status": "RESEARCH_DIAGNOSTIC_ONLY",
        "dataset": {
            "valid_rows": 238854,
            "competition_count": 38,
            "first_match_date": "2000-07-28",
            "last_match_date": "2026-09-03",
        },
        "historical_1x2": {
            "release_status": "NOT_CERTIFIED_MARKET_OUTPERFORMED_MODELS",
            "full_sample_models": {"elo": {"result_accuracy": 0.4836}},
            "market_comparison_same_fixtures": {"market": {"matches": 235464, "result_accuracy": 0.5011}},
        },
        "rolling_origin_1x2_calibration": {
            "live_poisson": {"status": "ROLLING_ORIGIN_DIAGNOSTIC_ONLY", "calibration_diagnostic_pass": True},
        },
        "rolling_origin_goal_market_calibration": {
            "folds_evaluated": 4,
            "markets": {"btts_yes": {"status": "CALIBRATION_DIAGNOSTIC_PASS"}},
        },
        "release_controls": {"value_betting": "LOCKED_INSUFFICIENT_EVIDENCE"},
    }
    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2026-11-02",
        "predictions": [],
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)
    monkeypatch.setattr(telegram, "load_model_validation_report", lambda: validation)
    payload = telegram.dashboard_data()
    assert payload["model_validation"] == validation


def test_dashboard_reports_offline_when_no_published_snapshot_exists(monkeypatch):
    from api import telegram

    monkeypatch.setattr(telegram, "load_latest_report", lambda: None)
    payload = telegram.dashboard_data()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["warning"] == "No published report could be loaded."
    assert payload["predictions"] == []



def test_dashboard_data_optional_snapshots_cannot_break_core_report(monkeypatch):
    from api import telegram

    report = {
        "as_of_date": "2099-05-01",
        "predictions": [{
            "home_team": "Always Visible FC",
            "away_team": "Guest FC",
            "status": "UNSUPPORTED_COMPETITION",
            "kickoff_local": "2099-05-01T15:00:00+01:00",
        }],
        "fixtures_received": 1,
        "command_data_publication": "PUBLISHED",
    }

    monkeypatch.setattr(telegram, "load_latest_report", lambda: report)

    def optional_failure():
        raise TimeoutError("optional snapshot timed out")

    monkeypatch.setattr(telegram, "load_paper_ledger", optional_failure)
    monkeypatch.setattr(telegram, "load_model_validation_report", optional_failure)

    payload = telegram.dashboard_data()
    assert payload["status"] == "OK"
    assert payload["fixtures_visible"] == 1
    assert payload["predictions"][0]["home_team"] == "Always Visible FC"
    assert payload["paper_tracking"] is None
    assert payload["model_validation"]["status"] == "NOT_REPORTED"


def test_vercel_skips_command_data_snapshot_deployments_without_blocking_main():
    import json
    from pathlib import Path

    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    command = config["ignoreCommand"]
    assert 'VERCEL_GIT_COMMIT_REF' in command
    assert 'command-data' in command
    assert 'exit 0' in command
    assert 'exit 1' in command


def test_dashboard_api_deduplicates_paper_tracking_rows_by_fixture_id(monkeypatch):
    from api import telegram

    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": "2099-05-01",
        "predictions": [],
        "fixtures_received": 0,
    })
    monkeypatch.setattr(telegram, "load_model_validation_report", lambda: None)
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: {
        "model_status": "PAPER_TRACKING_ONLY",
        "scored_matches": [
            {
                "fixture_id": 9001, "home_team": "Alpha", "away_team": "Beta",
                "report_date": "2099-04-30", "model": "experimental_recent_goals_poisson",
            },
            {
                "fixture_id": 9001, "home_team": "Alpha", "away_team": "Beta",
                "report_date": "2099-04-30", "model": "experimental_elo_global_fallback",
            },
        ],
    })

    payload = telegram.dashboard_data()
    tracking = payload["paper_tracking"]
    assert tracking["scored_matches_model_rows"] == 2
    assert tracking["scored_matches_unique_fixtures"] == 1
    assert len(tracking["scored_matches"]) == 1
    assert tracking["scored_matches"][0]["model"] == "experimental_recent_goals_poisson"



def test_dashboard_prediction_rows_strip_forged_value_candidates(monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from api import telegram

    kickoff = (datetime.now(ZoneInfo("Africa/Lagos")) + timedelta(hours=3)).isoformat()
    monkeypatch.setattr(telegram, "load_latest_report", lambda: {
        "as_of_date": datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat(),
        "predictions": [{
            "fixture_id": "fixture-1", "home_team": "Home", "away_team": "Away",
            "kickoff_local": kickoff,
            "value_bet_screen": {
                "status": "CANDIDATES_FOUND", "candidate_count": 1,
                "markets": {"1X2": {
                    "candidates": [{"selection": "home", "decimal_odds": 9.0}],
                    "paper_candidates": [{"selection": "away", "decimal_odds": 8.0}],
                }},
            },
        }],
        "value_validation_certificate": {
            "status": "VALIDATED", "approved_markets": ["1X2"],
            "betting_validation": True, "alerts_enabled": True,
        },
    })
    monkeypatch.setattr(telegram, "load_paper_ledger", lambda: None)
    payload = telegram.dashboard_data()
    assert len(payload["predictions"]) == 1
    screen = payload["predictions"][0]["value_bet_screen"]
    assert screen["candidate_count"] == 0
    assert screen["markets"]["1X2"]["candidates"] == []
    assert screen["markets"]["1X2"]["paper_candidates"] == []
    assert payload["value_validation_certificate"]["alerts_enabled"] is False
