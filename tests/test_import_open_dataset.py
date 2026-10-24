from scripts.import_open_dataset import RAW_BASE, find_matches_csv, normalize_row


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



def test_import_summary_reports_competition_and_season_coverage(tmp_path, monkeypatch):
    import csv
    import io
    from scripts import import_open_dataset as importer

    fields = ["Division", "MatchDate", "HomeTeam", "AwayTeam", "FTHome", "FTAway"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows([
        {"Division": "E0", "MatchDate": "2025-08-01", "HomeTeam": "A", "AwayTeam": "B", "FTHome": "1", "FTAway": "0"},
        {"Division": "E0", "MatchDate": "2025-08-08", "HomeTeam": "C", "AwayTeam": "D", "FTHome": "2", "FTAway": "2"},
        {"Division": "SP1", "MatchDate": "2026-01-02", "HomeTeam": "E", "AwayTeam": "F", "FTHome": "0", "FTAway": "1"},
    ])

    class FakeResponse:
        content = buffer.getvalue().encode("utf-8")
        def raise_for_status(self):
            return None
        def close(self):
            return None

    class FakeSession:
        def __init__(self):
            self.headers = {}
        def get(self, *args, **kwargs):
            return FakeResponse()
        def close(self):
            return None

    monkeypatch.setattr(importer.requests, "Session", FakeSession)
    monkeypatch.setattr(importer, "find_matches_csv", lambda session: "https://example.test/matches.csv")
    report = importer.import_dataset("2025-01-01", "2026-12-31", str(tmp_path / "history.csv"))
    assert report["matches_by_competition"] == {"E0": 2, "SP1": 1}
    assert report["matches_by_season"] == {"2025": 2, "2026": 1}



def test_dataset_path_avoids_github_tree_api_rate_limit():
    class NoRequestSession:
        def get(self, *args, **kwargs):
            raise AssertionError("The known raw CSV path should not require a tree API request.")

    assert find_matches_csv(NoRequestSession()) == RAW_BASE + "data/Matches.csv"
