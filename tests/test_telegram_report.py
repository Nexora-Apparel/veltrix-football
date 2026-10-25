from __future__ import annotations

import requests
import pytest

from scripts.send_telegram_report import (
    MAX_MESSAGE_LENGTH,
    format_report,
    format_report_messages,
    send_message,
)


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
            "kickoff_local": "2026-10-23T16:00:00Z",
            "probabilities": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
            "expected_goals": {"home": 1.4, "away": 0.8},
            "model": "experimental_recent_goals_poisson",
            "elo_probabilities": {"home_win": 0.6, "draw": 0.25, "away_win": 0.15},
            "btts_yes": 0.58,
            "over_2_5": 0.52,
        }],
    }


def test_telegram_report_is_clear_and_experimental():
    message = format_report(sample_report())
    assert "⚽ VELTRIX FOOTBALL" in message
    assert "TODAY'S MATCH FORECASTS" in message
    assert "2026-10-23" in message
    assert "Nigeria (WAT)" in message
    assert "Experimental estimates only" in message
    assert "FORECASTS: 1" in message
    assert "Alpha FC vs Beta FC" in message
    assert "Example League" in message
    assert "Kickoff: 17:00 WAT" in message
    assert "Home win: 50%" in message
    assert "Draw: 25%" in message
    assert "Away win: 25%" in message
    assert "Expected goals: 1.40 - 0.80" in message
    assert "ELO ALTERNATIVE" not in message
    assert "POISSON GOAL MARKETS" not in message
    assert "Fixture data provided by Highlightly Football API." in message


def test_report_warns_when_recent_data_refresh_is_incomplete():
    report = sample_report()
    report["recent_results_sync"] = {
        "status": "UNAVAILABLE",
        "warning": "invalid token",
    }
    message = format_report(report)
    assert "DATA NOTICE: Recent-results refresh status: UNAVAILABLE." in message
    assert "authentication was rejected" in message
    assert "invalid token" not in message


def test_report_explains_recent_results_quota_limit_without_raw_provider_error():
    report = sample_report()
    report["recent_results_sync"] = {
        "status": "UNAVAILABLE",
        "warning": "Highlightly request failed with HTTP 429: daily API request quota or rate limit reached.",
    }
    message = format_report(report)
    assert "Recent-results refresh status: UNAVAILABLE" in message
    assert "Provider request quota/rate limit reached" in message
    assert "missing results are not invented" in message
    assert "HTTP 429" not in message


def test_report_handles_no_usable_predictions_and_withheld_fixtures():
    report = sample_report()
    report["predictions"] = [
        {"status": "INSUFFICIENT_HISTORY"},
        {"status": "UNSUPPORTED_COMPETITION"},
    ]
    message = format_report(report)
    assert "FORECASTS: 0" in message
    assert "NO USABLE EXPERIMENTAL FORECASTS TODAY." in message
    assert "1 match(es) withheld: not enough reliable team history." in message
    assert "1 match(es) withheld: league history is not supported." in message


def test_report_splits_without_dropping_fixtures_or_exceeding_limit():
    report = sample_report()
    template = dict(report["predictions"][0])
    report["predictions"] = []
    for index in range(30):
        report["predictions"].append({
            **template,
            "home_team": f"Home Team {index:02d}",
            "away_team": f"Away Team {index:02d}",
        })
    messages = format_report_messages(report)
    assert len(messages) > 1
    assert all(len(message) <= MAX_MESSAGE_LENGTH for message in messages)
    combined = "\n".join(messages)
    for index in range(30):
        assert f"Home Team {index:02d} vs Away Team {index:02d}" in combined


def test_telegram_send_requires_credentials_and_does_not_echo_token_on_network_error(monkeypatch):
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        send_message("", "", "test")

    token = "123456:TOP_SECRET_TEST_TOKEN"

    def fail_request(*args, **kwargs):
        raise requests.ConnectionError(
            f"connection failed for https://api.telegram.org/bot{token}/sendMessage"
        )

    monkeypatch.setattr("scripts.send_telegram_report.requests.post", fail_request)
    with pytest.raises(RuntimeError) as error:
        send_message(token, "12345", "hello")
    assert token not in str(error.value)
    assert "ConnectionError" in str(error.value)


def test_elo_primary_report_discloses_poisson_expected_goals_are_separate():
    report = sample_report()
    report["predictions"][0]["model"] = "experimental_elo_by_competition"
    report["predictions"][0]["probabilities"] = {"home_win": 0.59, "draw": 0.26, "away_win": 0.15}
    message = format_report(report)
    assert "Model: Elo ratings (1X2); Poisson xG" in message
    assert "When Elo is primary, expected goals are a separate Poisson estimate" in message
