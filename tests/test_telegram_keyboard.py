from api.telegram import BUTTON_COMMANDS, KEYBOARD


def test_keyboard_exposes_prediction_and_results_commands_only():
    labels = {
        button["text"]
        for row in KEYBOARD["keyboard"]
        for button in row
    }
    assert labels == {
        "1X2 Predictions",
        "BTTS",
        "Over/Under Goals",
        "Value Bet",
        "Results",
        "Performance",
        "Today's Predictions",
        "Fixtures",
        "Help",
    }
    assert KEYBOARD["is_persistent"] is True
    assert KEYBOARD["resize_keyboard"] is True


def test_keyboard_buttons_route_to_existing_commands():
    assert BUTTON_COMMANDS["1x2 predictions"] == "/today"
    assert BUTTON_COMMANDS["over/under goals"] == "/overunder"
    assert BUTTON_COMMANDS["btts"] == "/btts"
    assert BUTTON_COMMANDS["value bet"] == "/value"
    assert BUTTON_COMMANDS["today's predictions"] == "/today"
    assert BUTTON_COMMANDS["fixtures"] == "/fixtures"
    assert BUTTON_COMMANDS["results"] == "/results"
    assert BUTTON_COMMANDS["performance"] == "/performance"
    assert BUTTON_COMMANDS["help"] == "/help"
