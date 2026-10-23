from __future__ import annotations

from scripts.send_telegram_report import format_report, send_message


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


def test_telegram_send_requires_credentials():
    import pytest
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        send_message("", "", "test")
