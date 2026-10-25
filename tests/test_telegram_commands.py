from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.telegram_commands import NEW_MESSAGE_HEADER, handle_command


def test_every_reply_has_new_message_header():
    for command in ("/help", "/status", "/today", "/bttsvalue", "/10odds", "/slipcheck 1.8 2.0"):
        assert handle_command(command).startswith(NEW_MESSAGE_HEADER)


def test_help_lists_requested_commands():
    reply = handle_command("/help")
    for command in ("/overunder", "/btts", "/bttsvalue", "/10odds", "/status", "/performance"):
        assert command in reply


def test_missing_report_never_invents_fixtures():
    reply = handle_command("/today")
    assert "DATA NOT AVAILABLE" in reply
    assert "won't invent" in reply


def test_slipcheck_calculates_combined_odds_without_recommending_bets():
    reply = handle_command("/slipcheck 2.0 2.5")
    assert "Combined decimal odds: 5.00" in reply
    assert "NOT A BETTING RECOMMENDATION" in reply


def test_invalid_slipcheck_rejected():
    assert "Invalid input" in handle_command("/slipcheck 1.8 0")
    assert "Usage" in handle_command("/slipcheck")


def test_status_discloses_validation_gate():
    reply = handle_command("/status")
    assert "DISABLED until chronological out-of-sample validation" in reply


def test_status_discloses_historical_refresh_gaps():
    report = {
        "as_of_date": datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat(),
        "predictions": [],
        "recent_results_sync": {
            "status": "PARTIAL",
            "ranges_succeeded": 1,
            "ranges_requested": 8,
        },
        "historical_data_coverage": {
            "status": "GAPPED_OR_STALE",
            "contiguous_through": "2026-09-03",
            "latest_available_match_date": "2026-10-24",
        },
        "publication_status": "REUSED_SNAPSHOT_NOT_REFRESHED",
    }
    reply = handle_command("/status", report=report)
    assert "Recent-results refresh: PARTIAL (1/8 ranges refreshed)" in reply
    assert "Historical coverage: GAPPED_OR_STALE" in reply
    assert "Report publication: REUSED_SNAPSHOT_NOT_REFRESHED" in reply
    assert "continuous through 2026-09-03, latest available 2026-10-24" in reply


def test_match_lookup_uses_supplied_report_only():
    future_kickoff = (datetime.now(ZoneInfo("Africa/Lagos")) + timedelta(hours=3)).isoformat()
    report = {
        "predictions": [{
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "league": "Premier League",
            "kickoff_local": future_kickoff,
            "status": "EXPERIMENTAL_ONLY",
            "probabilities": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
        }]
    }
    reply = handle_command("/match Arsenal vs Chelsea", report=report)
    assert "Arsenal vs Chelsea" in reply
    assert "H 50%" in reply

def test_today_discloses_gapped_historical_data():
    future_kickoff = (datetime.now(ZoneInfo("Africa/Lagos")) + timedelta(hours=3)).isoformat()
    report = {
        "as_of_date": datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat(),
        "predictions": [{
            "home_team": "Forecast FC",
            "away_team": "Model FC",
            "league": "Test League",
            "kickoff_local": future_kickoff,
            "status": "EXPERIMENTAL_ONLY",
            "probabilities": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2},
        }],
        "recent_results_sync": {
            "status": "PARTIAL",
            "ranges_succeeded": 1,
            "ranges_requested": 8,
        },
        "historical_data_coverage": {
            "status": "GAPPED_OR_STALE",
            "contiguous_through": "2026-09-03",
            "latest_available_match_date": "2026-10-24",
        },
        "publication_status": "REUSED_SNAPSHOT_NOT_REFRESHED",
    }
    reply = handle_command("/today", report=report)
    assert "SNAPSHOT NOTICE: This is a reused same-day snapshot" in reply
    assert "History is continuous through 2026-09-03" in reply
    assert "latest available result date is 2026-10-24" in reply
    assert "1/8 date ranges refreshed" in reply


def test_today_excludes_withheld_fixtures_and_only_shows_real_forecasts():
    future_kickoff = (datetime.now(ZoneInfo("Africa/Lagos")) + timedelta(hours=3)).isoformat()
    report = {
        "predictions": [
            {
                "fixture_id": 1,
                "home_team": "Withheld FC",
                "away_team": "Unknown FC",
                "status": "UNSUPPORTED_COMPETITION",
                "reason": "Competition not supported",
                "kickoff_local": future_kickoff,
            },
            {
                "fixture_id": 2,
                "home_team": "Forecast FC",
                "away_team": "Model FC",
                "league": "Test League",
                "kickoff_local": future_kickoff,
                "status": "EXPERIMENTAL_ONLY",
                "probabilities": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2},
            },
        ]
    }
    today = handle_command("/today", report=report)
    fixtures = handle_command("/fixtures", report=report)
    status = handle_command("/status", report=report)

    assert "Forecast FC vs Model FC" in today
    assert "Withheld FC" not in today
    assert "Withheld FC vs Unknown FC" in fixtures
    assert "Usable experimental forecasts: 1" in status
    assert "Fixtures in report: 2" in status


def test_tomorrow_and_live_commands_do_not_relabel_same_day_snapshot():
    assert "DATA NOT CONNECTED" in handle_command("/tomorrow")
    assert "DATA NOT CONNECTED" in handle_command("/live")


def test_future_filter_excludes_tomorrow_even_when_kickoff_is_future():
    from app.telegram_commands import _kickoff_is_future
    now = datetime.now(ZoneInfo("Africa/Lagos")).replace(hour=12, minute=0, second=0, microsecond=0)
    tomorrow = (now + timedelta(days=1)).replace(hour=23, minute=30, second=0, microsecond=0)
    assert not _kickoff_is_future({"kickoff_local": tomorrow.isoformat()}, now=now, expected_date=now.date())


def test_future_filter_accepts_same_day_utc_timestamp_using_lagos_date():
    from app.telegram_commands import _kickoff_is_future
    now = datetime.now(ZoneInfo("Africa/Lagos")).replace(hour=12, minute=0, second=0, microsecond=0)
    kickoff = now + timedelta(hours=2)
    assert _kickoff_is_future({"kickoff": kickoff.astimezone(ZoneInfo("UTC")).isoformat()}, now=now, expected_date=now.date())


def test_match_does_not_publish_invalid_probability_vectors():
    now = datetime.now(ZoneInfo("Africa/Lagos"))
    future = (now + timedelta(hours=2)).isoformat()
    report = {"predictions": [{
        "home_team": "Unsafe FC", "away_team": "Example FC", "league": "Test",
        "kickoff_local": future, "status": "UNSUPPORTED_COMPETITION",
        "probabilities": {"home_win": 0.8, "draw": 0.8, "away_win": -0.6},
        "reason": "Unsupported competition",
    }]}
    reply = handle_command("/match Unsafe FC vs Example FC", report=report)
    assert "WITHHELD: Unsupported competition" in reply
    assert "H 80%" not in reply


def test_match_with_nan_probabilities_is_withheld():
    now = datetime.now(ZoneInfo("Africa/Lagos"))
    future = (now + timedelta(hours=2)).isoformat()
    report = {"predictions": [{
        "home_team": "NaN FC", "away_team": "Example FC", "league": "Test",
        "kickoff_local": future, "status": "EXPERIMENTAL_ONLY",
        "probabilities": {"home_win": float("nan"), "draw": 0.3, "away_win": 0.7},
    }]}
    reply = handle_command("/match NaN FC vs Example FC", report=report)
    assert "WITHHELD: EXPERIMENTAL_ONLY" in reply


def test_paper_tracking_keyboard_label_does_not_claim_successful_predictions():
    from api.telegram import BUTTON_COMMANDS, KEYBOARD
    labels = {button["text"] for row in KEYBOARD["keyboard"] for button in row}
    assert "Paper Tracking" in labels
    assert "Successful Predictions" not in labels
    assert BUTTON_COMMANDS["paper tracking"] == "/results"
