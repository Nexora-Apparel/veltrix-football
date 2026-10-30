from __future__ import annotations

import base64
import json

import requests
import pytest

from scripts.send_telegram_report import (
    MAX_MESSAGE_LENGTH,
    format_report,
    format_report_messages,
    send_message,
    _load_delivery_state,
    _record_delivery_date,
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


def test_telegram_report_is_predictions_only_and_keeps_new_update_alert():
    message = format_report(sample_report())
    assert "🔔 🆕 NEW VELTRIX UPDATE" in message
    assert "VELTRIX FOOTBALL · PREDICTIONS" in message
    assert "2026-10-23" in message
    assert "Matches: 1" in message
    assert "Alpha FC vs Beta FC" in message
    assert "Example League" in message
    assert "Kickoff" not in message
    assert "17:00 WAT" in message
    assert "1X2: Home 50% | Draw 25% | Away 25%" in message
    assert "BTTS Yes: 58%" in message
    assert "Over 2.5: 52% | Under 2.5: 48%" in message
    assert "xG: 1.40 - 0.80" in message
    assert "PAPER TRACKING" not in message
    assert "DATA NOTICE" not in message
    assert "MULTI-SOURCE REFERENCE PRICES" not in message
    assert "5DollarFootballAPI" not in message


def test_predictions_alert_is_short_when_no_usable_forecasts():
    report = sample_report()
    report["predictions"] = [{"status": "INSUFFICIENT_HISTORY"}]
    message = format_report(report)
    assert "🔔 🆕 NEW VELTRIX UPDATE" in message
    assert "Matches: 0" in message
    assert "No usable predictions available for today." in message
    assert "withheld" not in message


def test_report_hides_diagnostics_when_recent_data_refresh_is_incomplete():
    report = sample_report()
    report["recent_results_sync"] = {"status": "UNAVAILABLE", "warning": "invalid token"}
    message = format_report(report)
    assert "Alpha FC vs Beta FC" in message
    assert "DATA NOTICE" not in message
    assert "invalid token" not in message


def test_report_hides_snapshot_diagnostics_from_prediction_alert():
    report = sample_report()
    report["publication_status"] = "REUSED_SNAPSHOT_NOT_REFRESHED"
    message = format_report(report)
    assert "Alpha FC vs Beta FC" in message
    assert "SNAPSHOT NOTICE" not in message


def test_report_hides_quota_diagnostics_from_prediction_alert():
    report = sample_report()
    report["recent_results_sync"] = {
        "status": "UNAVAILABLE",
        "warning": "Provider request quota/rate limit reached.",
    }
    message = format_report(report)
    assert "Alpha FC vs Beta FC" in message
    assert "DATA NOTICE" not in message
    assert "quota" not in message.lower()


def test_report_hides_historical_coverage_details_from_prediction_alert():
    report = sample_report()
    report["recent_results_sync"] = {"status": "PARTIAL", "warning": "Refresh limited"}
    report["historical_data_coverage"] = {
        "status": "GAPPED_OR_STALE", "contiguous_through": "2026-09-03",
        "latest_available_match_date": "2026-10-24",
    }
    message = format_report(report)
    assert "Alpha FC vs Beta FC" in message
    assert "Historical coverage" not in message
    assert "continuous through" not in message


def test_report_handles_no_usable_predictions_without_long_notes():
    report = sample_report()
    report["predictions"] = [
        {"status": "INSUFFICIENT_HISTORY"},
        {"status": "UNSUPPORTED_COMPETITION"},
    ]
    message = format_report(report)
    assert "Matches: 0" in message
    assert "No usable predictions available for today." in message
    assert "withheld" not in message


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




def test_delivery_state_loads_published_dates_and_sha(monkeypatch):
    payload = {
        "sha": "blob-sha",
        "content": base64.b64encode(json.dumps({
            "version": 1, "sent_dates": ["2026-10-26", "2026-10-27"]
        }).encode()).decode(),
    }
    monkeypatch.setattr("scripts.send_telegram_report._github_json", lambda *a, **k: payload)
    state, sha = _load_delivery_state("Nexora-Apparel/veltrix-football", "token")
    assert state == {"version": 1, "sent_dates": ["2026-10-26", "2026-10-27"]}
    assert sha == "blob-sha"


def test_delivery_state_rejects_malformed_remote_state(monkeypatch):
    payload = {"sha": "blob-sha", "content": base64.b64encode(b'{"version":9}').decode()}
    monkeypatch.setattr("scripts.send_telegram_report._github_json", lambda *a, **k: payload)
    with pytest.raises(RuntimeError, match="duplicate send"):
        _load_delivery_state("Nexora-Apparel/veltrix-football", "token")


def test_delivery_marker_is_saved_with_existing_sha_and_recent_dates(monkeypatch):
    calls = []
    def fake_github_json(url, token, method="GET", body=None):
        calls.append((url, token, method, body))
        return {"content": {"sha": "new-sha"}}
    monkeypatch.setattr("scripts.send_telegram_report._github_json", fake_github_json)
    state = {"version": 1, "sent_dates": [f"2026-10-{day:02d}" for day in range(1, 31)]}
    _record_delivery_date("Nexora-Apparel/veltrix-football", "token", "2026-10-31", state, "old-sha")
    assert len(calls) == 1
    _, token, method, body = calls[0]
    assert token == "token" and method == "PUT"
    assert body["sha"] == "old-sha"
    saved = json.loads(base64.b64decode(body["content"]))
    assert saved["version"] == 1
    assert saved["sent_dates"][-1] == "2026-10-31"
    assert len(saved["sent_dates"]) == 30



def test_main_skips_a_report_date_already_recorded_as_sent(tmp_path, monkeypatch, capsys):
    import json
    from scripts import send_telegram_report as sender

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "as_of_date": "2026-10-27",
        "same_day_only": True,
        "timezone": "Africa/Lagos",
        "predictions": [],
    }), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["send_telegram_report.py", "--report", str(report_path), "--ledger", str(tmp_path / "missing-ledger.json")])
    monkeypatch.setenv("GITHUB_REPOSITORY", "Nexora-Apparel/veltrix-football")
    monkeypatch.setenv("GITHUB_TOKEN", "github-test-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setattr(sender, "_load_delivery_state", lambda repo, token: ({"version": 1, "sent_dates": ["2026-10-27"]}, "sha"))
    monkeypatch.setattr(sender, "send_message", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate send attempted")))

    sender.main()
    assert "already sent" in capsys.readouterr().out



def test_report_hides_plan_limited_history_details_from_prediction_alert():
    report = sample_report()
    report["recent_results_sync"] = {
        "status": "PARTIAL",
        "warning": "Historical dates remain unavailable on the provider plan.",
    }
    report["historical_data_coverage"] = {
        "status": "GAPPED_OR_STALE",
        "contiguous_through": "2026-09-20",
        "latest_available_match_date": "2026-10-26",
        "provider_plan_limited_date_count": 21,
        "retryable_gap_date_count": 0,
    }
    message = format_report(report)
    assert "Alpha FC vs Beta FC" in message
    assert "historical date(s) are inaccessible" not in message
    assert "provider plan" not in message


def test_main_force_flag_resends_corrected_same_day_report(tmp_path, monkeypatch, capsys):
    """Controlled release check for corrected same-day delivery."""
    import json
    from scripts import send_telegram_report as sender

    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "as_of_date": "2026-10-27",
        "same_day_only": True,
        "timezone": "Africa/Lagos",
        "predictions": [],
    }), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["send_telegram_report.py", "--report", str(report_path), "--ledger", str(tmp_path / "missing-ledger.json"), "--force"])
    monkeypatch.setenv("GITHUB_REPOSITORY", "Nexora-Apparel/veltrix-football")
    monkeypatch.setenv("GITHUB_TOKEN", "github-test-token")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "telegram-test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setattr(sender, "_load_delivery_state", lambda repo, token: ({"version": 1, "sent_dates": ["2026-10-27"]}, "sha"))
    sent = []
    monkeypatch.setattr(sender, "send_message", lambda token, chat_id, message: sent.append(message))
    monkeypatch.setattr(sender, "_record_delivery_date", lambda *args, **kwargs: None)

    sender.main()
    assert sent
    assert "delivered for 2026-10-27" in capsys.readouterr().out


def test_telegram_report_includes_value_screen_status_and_only_supplied_candidates():
    report = sample_report()
    report["value_bet_screen"] = {
        "status": "DISABLED_UNVALIDATED",
        "markets": ["1X2", "BTTS", "OVER_UNDER_2_5"],
    }
    report["predictions"][0]["value_bet_screen"] = {
        "markets": {
            "1X2": {"candidates": [{
                "selection": "home_win",
                "decimal_odds": 2.1,
                "edge_percentage_points": 5.5,
                "expected_return_per_unit": 0.12,
            }]},
        },
    }
    message = format_report(report)
    assert "Value screen: 1X2 / BTTS / Over-Under · DISABLED_UNVALIDATED" in message
    assert "VALUE CANDIDATE: 1X2 home_win @ 2.10 · edge 5.5pp · expected return 12.0%" in message


def test_telegram_report_labels_competition_prior_forecast_basis():
    report = sample_report()
    report["predictions"][0]["prediction_basis"] = (
        "competition-level historical goal-rate prior; team-specific history below minimum"
    )
    message = format_report(report)
    assert "FORECAST BASIS: competition-level historical goal-rate prior; team-specific history below minimum" in message
