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
            # These are the exact keys emitted by app.live_predictions.
            "probabilities": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
            "expected_goals": {"home": 1.4, "away": 0.8},
        }],
    }


def test_telegram_report_is_explicitly_experimental_and_same_day():
    message = format_report(sample_report())
    assert "EXPERIMENTAL — NOT VALIDATED FOR BETTING" in message
    assert "Alpha FC vs Beta FC" in message
    assert "Home 50% | Draw 25% | Away 25%" in message
    assert "Home 0%" not in message
    assert "Normal 10.00-odds slips: DISABLED." in message
    assert "Value slips (50.00–100.00 odds): DISABLED." in message
    assert "betting tips" in message


def test_telegram_report_handles_no_usable_predictions():
    report = sample_report()
    report["predictions"] = []
    message = format_report(report)
    assert "NO USABLE EXPERIMENTAL FORECASTS TODAY." in message
    assert "No picks are being forced." in message


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
    assert message.count("League: Example League") == message.count(
        "Status: experimental only; do not treat as a recommendation."
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
