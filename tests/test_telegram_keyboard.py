from api.telegram import BUTTON_COMMANDS, KEYBOARD


def test_keyboard_exposes_requested_sections():
    labels = {
        button["text"]
        for row in KEYBOARD["keyboard"]
        for button in row
    }
    assert labels == {
        "Today's Predictions",
        "Fixtures",
        "Successful Predictions",
        "Results & Performance",
        "Status",
        "Help",
    }
    assert KEYBOARD["is_persistent"] is True
    assert KEYBOARD["resize_keyboard"] is True


def test_keyboard_buttons_route_to_existing_commands():
    assert BUTTON_COMMANDS["today's predictions"] == "/today"
    assert BUTTON_COMMANDS["fixtures"] == "/fixtures"
    assert BUTTON_COMMANDS["successful predictions"] == "/results"
    assert BUTTON_COMMANDS["results & performance"] == "/performance"
    assert BUTTON_COMMANDS["status"] == "/status"
    assert BUTTON_COMMANDS["help"] == "/help"
