from __future__ import annotations

import requests
import pytest

from scripts.send_telegram_report import MAX_MESSAGE_LENGTH, format_report, send_message


def sample_report():
    return {
        "as_of_date": "2026-10-23",
        "timezone": "Africa/Lagos",
        "same_day_only": True,
        "predictions": [{
            "status": "EXPERIMENTAL_ONLY",
            "home_team": "Alpha FC",
            "away_team": "Beta FC",
            "league": "Example League",
            "kickoff_local": "2026-10-23T17:00:00+01:00",
            "probabilities": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
            "expected_goals": {"home": 1.4, "away": 0.8},
        }],
    }


def test_telegram_report_is_organized_and_explicitly_experimental():
    message = format_report(sample_report())
    assert "⚽ VELTRIX FOOTBALL" in message
    assert "DAILY MATCH ANALYTICS" in message
    assert "2026-10-23" in message
    assert "EXPERIMENTAL MODEL — NOT VALIDATED FOR BETTING" in message
    assert "MATCH FORECASTS: 1" in message
    assert "Alpha FC vs Beta FC" in message
    assert "Example League" in message
    assert "Kickoff: 17:00 WAT" in message
    assert "Home  50%" in message
    assert "Draw  25%" in message
    assert "Away  25%" in message
    assert "Expected goals: 1.40 - 0.80" in message
    assert "Standard 10.00-odds slips: DISABLED." in message
    assert "Value slips (50.00–100.00 odds): DISABLED." in message
    assert "historical market benchmark" in message
    assert "not betting tips" in message


def test_telegram_report_handles_no_usable_predictions():
    report = sample_report()
    report["predictions"] = []
    message = format_report(report)
    assert "NO USABLE EXPERIMENTAL FORECASTS TODAY." in message
    assert "No picks are being forced." in message
    assert "MATCH FORECASTS: 0" in message


def test_telegram_report_counts_fixtures_with_insufficient_history():
    report = sample_report()
    report["predictions"].append({
        "status": "INSUFFICIENT_HISTORY",
        "home_team": "Unknown FC",
        "away_team": "Mystery FC",
    })
    assert "1 fixture(s) withheld: insufficient historical team data." in format_report(report)


def test_telegram_report_truncates_only_between_fixture_blocks():
    report = sample_report()
    report["predictions"] = [
        {
            **sample_report()["predictions"][0],
            "home_team": f"Home Club {i:02d} " + ("A" * 30),
            "away_team": f"Away Club {i:02d} " + ("B" * 30),
        }
        for i in range(80)
    ]
    message = format_report(report)
    assert len(message) <= MAX_MESSAGE_LENGTH
    assert "additional fixture(s) omitted" in message
    assert message.count("Expected goals:") == message.count(
        "Status: experimental estimate only"
    )


def test_telegram_send_requires_credentials():
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        send_message("", "", "test")


def test_telegram_network_errors_do_not_echo_token(monkeypatch):
    token = "123456:TOP_SECRET_TEST_TOKEN"

    def fail_request(*args, **kwargs):
        raise requests.ConnectionError(f"connection failed for https://api.telegram.org/bot{token}/sendMessage")

    monkeypatch.setattr("scripts.send_telegram_report.requests.post", fail_request)
    with pytest.raises(RuntimeError) as error:
        send_message(token, "12345", "hello")
    assert token not in str(error.value)
    assert "ConnectionError" in str(error.value)


def test_telegram_report_converts_utc_kickoff_to_lagos_time():
    report = sample_report()
    report["predictions"][0]["kickoff_local"] = "2026-10-23T16:00:00Z"
    assert "Kickoff: 17:00 WAT" in format_report(report)



def test_telegram_report_discloses_non_automatic_name_match_suggestions():
    report = sample_report()
    report["predictions"].append({
        "status": "INSUFFICIENT_HISTORY",
        "home_team": "Alph FC",
        "away_team": "Mystery FC",
        "team_name_match_suggestions": {"home": ["Alpha FC"]},
    })
    message = format_report(report)
    assert "possible team-name variants to review" in message
    assert "suggestions only and are never auto-matched" in message



def test_telegram_report_shows_fixture_filter_counts_when_available():
    report = sample_report()
    report.update({
        "fixtures_received": 100,
        "future_fixtures_considered": 12,
        "past_kickoffs_excluded": 3,
        "fixtures_excluded_other_date_or_status": 85,
    })
    message = format_report(report)
    assert "API fixtures received: 100" in message
    assert "Today/future fixtures considered: 12" in message
    assert "Past kickoffs excluded: 3" in message
    assert "Other dates/status excluded: 85" in message



def test_telegram_report_includes_cumulative_paper_metrics_by_model():
    ledger = {
        "last_attempt": {"status": "EVALUATED", "report_date": "2026-10-23"},
        "cumulative_metrics_by_model": {
            "experimental_recent_goals_poisson": {
                "matches": 12,
                "result_accuracy": 0.5,
                "brier_score": 0.62,
                "log_loss": 1.04,
            }
        },
    }
    message = format_report(sample_report(), ledger)
    assert "PAPER TRACKING — CUMULATIVE" in message
    assert "Latest evaluation status: EVALUATED" in message
    assert "12 scored" in message
    assert "accuracy 50.0%" in message
    assert "Brier 0.620 | log loss 1.040" in message
    assert "not proof of profitability" in message



def test_telegram_report_shows_elo_alternative_when_available():
    report = sample_report()
    report["predictions"][0]["elo_model"] = "experimental_elo_by_competition"
    report["predictions"][0]["elo_history"] = {"scope": "COMPETITION", "division_code": "E0"}
    report["predictions"][0]["elo_probabilities"] = {
        "home_win": 0.6, "draw": 0.25, "away_win": 0.15,
    }
    message = format_report(report)
    assert "ELO ALTERNATIVE (EXPERIMENTAL)" in message
    assert "Competition history: E0" in message
    assert "Home  60%" in message
    assert "Draw  25%" in message
    assert "Away  15%" in message



def test_telegram_report_labels_elo_primary_and_poisson_auxiliary():
    report = sample_report()
    item = report["predictions"][0]
    item["model"] = "experimental_elo_by_competition"
    item["elo_history"] = {"scope": "COMPETITION", "division_code": "E0"}
    item["probabilities"] = {"home_win": 0.6, "draw": 0.25, "away_win": 0.15}
    item["poisson_model"] = "experimental_recent_goals_poisson"
    item["poisson_probabilities"] = {"home_win": 0.4, "draw": 0.3, "away_win": 0.3}
    message = format_report(report)
    assert "ELO PRIMARY ESTIMATE" in message
    assert "Competition history: E0" in message
    assert "POISSON ALTERNATIVE (EXPERIMENTAL)" in message
    assert "Poisson xG (auxiliary)" in message



def test_telegram_report_summarizes_primary_model_mix():
    report = sample_report()
    report["primary_model_counts"] = {
        "experimental_elo_by_competition": 3,
        "experimental_recent_goals_poisson": 2,
    }
    report["elo_alternative_available"] = 2
    report["poisson_alternative_available"] = 3
    message = format_report(report)
    assert "MODEL MIX" in message
    assert "experimental_elo_by_competition: 3 primary forecast(s)" in message
    assert "experimental_recent_goals_poisson: 2 primary forecast(s)" in message
    assert "Alternative forecasts available — Elo: 2 | Poisson: 3" in message
