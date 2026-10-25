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


def test_match_lookup_uses_supplied_report_only():
    report = {
        "predictions": [{
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "league": "Premier League",
            "probabilities": {"home_win": 0.5, "draw": 0.25, "away_win": 0.25},
        }]
    }
    reply = handle_command("/match Arsenal vs Chelsea", report=report)
    assert "Arsenal vs Chelsea" in reply
    assert "H 50%" in reply

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
