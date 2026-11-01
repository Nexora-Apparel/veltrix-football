from app.team_form import summarize_team_form


def test_form_reports_recent_results_and_performance_metrics():
    rows = [
        (2, 0, "home"), (1, 1, "away"), (0, 1, "home"),
        (3, 0, "away"), (1, 0, "home"), (0, 2, "away"),
    ]
    result = summarize_team_form(rows)
    assert result["last_5"]["form"] == "DLWDL"
    assert result["last_5"]["matches"] == 5
    assert result["last_5"]["wins"] == 1
    assert result["last_5"]["draws"] == 2
    assert result["last_5"]["losses"] == 2
    assert result["last_5"]["points_per_game"] == 1.0
    assert result["last_5"]["goals_for"] == 5
    assert result["last_5"]["goals_against"] == 4


def test_venue_filter_uses_only_requested_venue():
    rows = [
        (3, 0, "home"), (0, 2, "away"), (2, 1, "home"),
        (1, 1, "away"), (1, 0, "home"),
    ]
    result = summarize_team_form(rows, venue="home")
    assert result["scope"] == "home"
    assert result["last_10"]["matches"] == 3
    assert result["last_10"]["form"] == "WWW"
    assert result["last_10"]["goals_for"] == 6
    assert result["last_10"]["goals_against"] == 1


def test_empty_form_is_explicit_and_safe():
    result = summarize_team_form([])
    assert result["last_5"]["matches"] == 0
    assert result["last_5"]["points_per_game"] is None
    assert result["last_10"]["form"] == ""
