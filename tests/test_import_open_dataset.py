from scripts.import_open_dataset import normalize_row


def base_row(**overrides):
    row = {
        "Division": "E0", "MatchDate": "2026-09-01",
        "HomeTeam": "Home FC", "AwayTeam": "Away FC",
        "FTHome": "2", "FTAway": "1", "HomeElo": "1800",
        "AwayElo": "1750", "Form3Home": "7", "Form3Away": "4",
        "Form5Home": "12", "Form5Away": "8", "OddHome": "1.8",
        "OddDraw": "3.5", "OddAway": "4.2", "Over25": "1.9",
        "Under25": "2.0", "HTHome": "1", "HTAway": "0",
        "HomeShots": "10", "AwayShots": "8", "HomeTarget": "4",
        "AwayTarget": "3",
    }
    row.update(overrides)
    return row


def test_normalizes_completed_match_and_preserves_odds():
    result = normalize_row(base_row())
    assert result is not None
    assert result["full_time_result"] == "H"
    assert result["home_goals"] == 2
    assert result["home_elo"] == 1800
    assert result["home_odds"] == 1.8
    assert result["half_time_away_goals"] == 0


def test_draw_and_missing_optional_fields():
    result = normalize_row(base_row(FTHome="0", FTAway="0", OddHome="", HomeElo=""))
    assert result is not None
    assert result["full_time_result"] == "D"
    assert result["home_odds"] is None
    assert result["home_elo"] is None


def test_rejects_invalid_score_or_date():
    assert normalize_row(base_row(FTHome="NA")) is None
    assert normalize_row(base_row(MatchDate="not-a-date")) is None


def test_rejects_same_team_and_requires_schema():
    assert normalize_row(base_row(AwayTeam="Home FC")) is None
    try:
        normalize_row({"Division": "E0"})
    except ValueError as exc:
        assert "missing required columns" in str(exc)
    else:
        raise AssertionError("Expected schema validation error")



def test_rejects_negative_or_fractional_full_time_scores():
    assert normalize_row(base_row(FTHome="-1")) is None
    assert normalize_row(base_row(FTAway="-1")) is None
    assert normalize_row(base_row(FTHome="2.5")) is None
    assert normalize_row(base_row(FTAway="1.25")) is None
