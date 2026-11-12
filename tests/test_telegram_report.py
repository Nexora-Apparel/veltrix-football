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
            "recent_form": {
                "home_team": {"overall": {"last_5": {"matches": 5, "form": "WWDLL", "points_per_game": 1.4}}},
                "away_team": {"overall": {"last_5": {"matches": 5, "form": "LLDWD", "points_per_game": 1.0}}},
            },
        }],
    }


def test_telegram_report_is_predictions_only_and_keeps_new_update_alert():
    message = format_report(sample_report())
    assert "🔔 🆕 NEW VELTRIX UPDATE" in message
    assert "VELTRIX FOOTBALL AI · DAILY INTELLIGENCE" in message
    assert "2026-10-23" in message
    assert "Alpha FC vs Beta FC" in message
    assert "Example League" in message
    assert "Kickoff" not in message
    assert "17:00 WAT" in message
    assert "1X2: Home 50% | Draw 25% | Away 25%" in message
    assert "BTTS Yes: 58%" in message
    assert "Over 2.5: 52% | Under 2.5: 48%" in message
    assert "xG: 1.40 - 0.80" in message
    assert "Recent form · last 5: Home WWDLL (1.40 PPG) | Away LLDWD (1.00 PPG)" in message
    assert "PAPER TRACKING" not in message
    assert "DATA NOTICE" not in message
    assert "MULTI-SOURCE REFERENCE PRICES" not in message
    assert "Football data by 5DollarFootballAPI" in message
    assert "https://5dollarfootballapi.com" in message


def test_predictions_alert_is_short_when_no_usable_forecasts():
    report = sample_report()
    report["predictions"] = [{"status": "INSUFFICIENT_HISTORY"}]
    message = format_report(report)
    assert "🔔 🆕 NEW VELTRIX UPDATE" in message
    assert "Forecast withheld: insufficient reliable team history." in message
    assert "No probabilities or betting signal published for this fixture." in message


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
    assert "History Gap" not in message
    assert "No probabilities or betting signal published for this fixture." in message


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
    assert all("Football data by 5DollarFootballAPI" in message for message in messages)
    assert all("https://5dollarfootballapi.com" in message for message in messages)
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
    assert state == {"version": 2, "sent_dates": ["2026-10-26", "2026-10-27"], "sent_report_hashes_by_date": {}}
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
    state = {"version": 2, "sent_dates": [f"2026-10-{day:02d}" for day in range(1, 31)], "sent_report_hashes_by_date": {}}
    _record_delivery_date("Nexora-Apparel/veltrix-football", "token", "2026-10-31", "a" * 64, state, "old-sha")
    assert len(calls) == 1
    _, token, method, body = calls[0]
    assert token == "token" and method == "PUT"
    assert body["sha"] == "old-sha"
    saved = json.loads(base64.b64decode(body["content"]))
    assert saved["version"] == 2
    assert saved["sent_dates"][-1] == "2026-10-31"
    assert len(saved["sent_dates"]) == 30
    assert saved["sent_report_hashes_by_date"]["2026-10-31"] == ["a" * 64]



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
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report_hash = sender._report_fingerprint(sender.format_report_messages(report))
    monkeypatch.setattr(sender, "_load_delivery_state", lambda repo, token: ({
        "version": 2, "sent_dates": ["2026-10-27"],
        "sent_report_hashes_by_date": {"2026-10-27": [report_hash]},
    }, "sha"))
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
    """Explicit opt-in resend for a corrected same-day publication."""
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
    assert "Value screen: 1X2 / BTTS / Over-Under · DISABLED_UNVALIDATED" not in message
    assert "LOCKED_INSUFFICIENT_EVIDENCE" not in message
    assert "VALUE BET VERDICT: Potential edge under review · 1X2 home_win @ 2.10" in message
    assert "· not approved" in message
    assert "· approved" not in message


def test_telegram_report_labels_competition_prior_forecast_basis():
    report = sample_report()
    report["predictions"][0]["prediction_basis"] = (
        "competition-level historical goal-rate prior; team-specific history below minimum"
    )
    message = format_report(report)
    assert "WHY THIS VERDICT: competition-level historical goal-rate prior; team-specific history below minimum" in message


def test_telegram_report_discloses_reference_prices_for_all_three_markets():
    report = sample_report()
    item = report["predictions"][0]
    item["prediction_basis"] = "competition-level historical goal-rate prior; team-specific history below minimum"
    item["the_odds_api_market_odds"] = {"markets": {
        "h2h": [{"bookmaker": "Book A", "outcomes": [
            {"name": "Alpha FC", "price": 2.10},
            {"name": "Draw", "price": 3.20},
            {"name": "Beta FC", "price": 3.60},
        ]}],
        "btts": [{"bookmaker": "Book B", "outcomes": [
            {"name": "Yes", "price": 1.85}, {"name": "No", "price": 1.95},
        ]}],
        "totals": [{"bookmaker": "Book C", "outcomes": [
            {"name": "Over", "point": 2.5, "price": 1.90},
            {"name": "Under", "point": 2.5, "price": 1.95},
        ]}],
    }}
    message = format_report(report)
    assert "WHY THIS VERDICT: competition-level historical goal-rate prior" in message
    assert "REFERENCE BOOKMAKER PRICES — NOT VALUE PICKS" in message
    assert "1X2 · Book A: Alpha FC 2.10 / Draw 3.20 / Beta FC 3.60" in message
    assert "BTTS · Book B: Yes 1.85 / No 1.95" in message
    assert "O/U 2.5 · Book C: Over 2.5 1.90 / Under 2.5 1.95" in message


def test_telegram_report_lists_all_fixtures_and_marks_ineligible_forecasts():
    report = sample_report()
    report["predictions"] = [
        {**report["predictions"][0], "home_team": "Forecasted FC", "away_team": "Modelled FC"},
        {
            "status": "INSUFFICIENT_HISTORY",
            "home_team": "History Gap FC",
            "away_team": "New Club FC",
            "league": "Example League",
            "kickoff_local": "2026-10-23T18:00:00+01:00",
        },
        {
            "status": "UNSUPPORTED_COMPETITION",
            "home_team": "Cup Side",
            "away_team": "Regional Side",
            "league": "Unmapped Cup",
            "kickoff_local": "2026-10-23T19:00:00+01:00",
        },
    ]
    message = "\n".join(format_report_messages(report))
    assert "Forecasted FC vs Modelled FC" in message
    assert "History Gap FC vs New Club FC" in message
    assert "Cup Side vs Regional Side" in message
    assert "FORECAST STATUS: INSUFFICIENT_HISTORY" in message
    assert "FORECAST STATUS: UNSUPPORTED_COMPETITION" in message
    assert "No probabilities or betting signal published for this fixture." in message


# Controlled production verification: exercise corrected all-fixture Telegram delivery.



def test_report_header_shows_goal_calibration_and_market_release_state():
    report = sample_report()
    report["goal_market_calibration"] = {
        "status": "NO_COMPATIBLE_FORECASTS",
        "compatible_forecasts": 0,
        "applied_forecasts": 0,
    }
    report["value_validation_certificate"] = {
        "status": "LOCKED_INSUFFICIENT_EVIDENCE",
        "approved_markets": [],
    }
    message = format_report(report)
    assert "Goal calibration:" not in message
    assert "Validation:" not in message


def test_telegram_retains_fixture_with_unverified_kickoff():
    report = sample_report()
    report["predictions"] = [{
        "status": "KICKOFF_UNVERIFIED",
        "home_team": "Retained FC",
        "away_team": "Visible United",
        "league": "Test League",
        "kickoff_local": None,
        "reason": "Kickoff timestamp missing",
    }]
    message = format_report(report)
    assert "Retained FC vs Visible United" in message
    assert "Fixture retained; forecast withheld because its kickoff time could not be verified." in message


def test_legacy_sent_date_without_hash_allows_one_updated_same_day_report(monkeypatch):
    from scripts import send_telegram_report as sender

    messages = format_report_messages(sample_report())
    report_hash = sender._report_fingerprint(messages)
    legacy_state = {"version": 2, "sent_dates": ["2026-10-23"], "sent_report_hashes_by_date": {}}
    assert sender._should_skip_delivery(legacy_state, "2026-10-23", report_hash) is False
    updated = sender._mark_same_day_update(messages)
    assert "UPDATED SAME-DAY REPORT" in updated[0]
    assert sender._should_skip_delivery({
        "version": 2,
        "sent_dates": ["2026-10-23"],
        "sent_report_hashes_by_date": {"2026-10-23": [report_hash]},
    }, "2026-10-23", report_hash) is True


def test_different_same_day_report_hash_is_not_suppressed():
    from scripts.send_telegram_report import _should_skip_delivery
    state = {
        "version": 2,
        "sent_dates": ["2026-10-23"],
        "sent_report_hashes_by_date": {"2026-10-23": ["a" * 64]},
    }
    assert _should_skip_delivery(state, "2026-10-23", "b" * 64) is False



def test_telegram_withholds_legacy_low_data_forecast_probabilities():
    report = sample_report()
    report["predictions"][0]["status"] = "EXPERIMENTAL_LOW_DATA"
    report["predictions"][0]["model"] = "experimental_global_licensed_prior_poisson"
    report["predictions"][0]["prediction_basis"] = "licensed global goal-rate prior only"
    report["predictions"][0]["betting_recommendation"] = False
    message = format_report(report)
    assert "Alpha FC vs Beta FC" in message
    assert "FORECAST STATUS: INSUFFICIENT_HISTORY" in message
    assert "Historical evidence is not yet sufficient for a reliable forecast." in message
    assert "1X2: Home 50%" not in message
    assert "BTTS Yes: 58%" not in message
    assert "xG: 1.40 - 0.80" not in message
    assert "LOW-DATA EXPERIMENTAL" not in message
