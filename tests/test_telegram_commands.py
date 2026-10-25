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
