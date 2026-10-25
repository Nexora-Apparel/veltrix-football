from api.telegram import BUTTON_COMMANDS, KEYBOARD


def test_keyboard_exposes_requested_sections():
    labels = {
        button["text"]
        for row in KEYBOARD["keyboard"]
        for button in row
    }
    assert labels == {
        "Over/Under Goals",
        "BTTS",
        "Today's Predictions",
        "Fixtures",
        "Paper Tracking",
        "Results & Performance",
        "Status",
        "Help",
    }
    assert KEYBOARD["is_persistent"] is True
    assert KEYBOARD["resize_keyboard"] is True


def test_keyboard_buttons_route_to_existing_commands():
    assert BUTTON_COMMANDS["over/under goals"] == "/overunder"
    assert BUTTON_COMMANDS["btts"] == "/btts"
    assert BUTTON_COMMANDS["today's predictions"] == "/today"
    assert BUTTON_COMMANDS["fixtures"] == "/fixtures"
    assert BUTTON_COMMANDS["paper tracking"] == "/results"
    assert BUTTON_COMMANDS["results & performance"] == "/performance"
    assert BUTTON_COMMANDS["status"] == "/status"
    assert BUTTON_COMMANDS["help"] == "/help"
