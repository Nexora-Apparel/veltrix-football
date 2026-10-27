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



def test_football_data_current_season_rows_normalize_and_reject_unfinished_scores():
    from datetime import date
    from scripts.import_open_dataset import _football_data_season_code, normalize_football_data_row

    assert _football_data_season_code(date(2026, 10, 27)) == "2627"
    row = normalize_football_data_row({
        "Date": "21/09/26", "HomeTeam": "Arsenal", "AwayTeam": "Chelsea",
        "FTHG": "2", "FTAG": "1", "B365H": "1.80", "B365D": "3.50",
        "B365A": "4.20", "HTHG": "1", "HTAG": "0", "HS": "12",
        "AS": "8", "HST": "5", "AST": "3",
    }, "E0")
    assert row is not None
    assert row["source"] == "football-data.co.uk"
    assert row["match_date"] == "2026-09-21"
    assert row["full_time_result"] == "H"
    assert row["home_odds"] == 1.8
    assert row["home_shots_on_target"] == 5
    assert normalize_football_data_row({
        "Date": "21/09/26", "HomeTeam": "Arsenal", "AwayTeam": "Chelsea",
        "FTHG": "", "FTAG": "",
    }, "E0") is None


def test_current_season_fallback_adds_completed_rows_and_deduplicates():
    import csv
    import io
    import requests
    from datetime import date
    from scripts.import_open_dataset import OUTPUT_COLUMNS, _append_current_season_fallback

    csv_text = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\\n"
        "E0,21/09/26,Arsenal,Chelsea,2,1,H,1.80,3.50,4.20\\n"
        "E0,22/09/26,Arsenal,Chelsea,,, ,1.80,3.50,4.20\\n"
    )

    class FakeResponse:
        def __init__(self, status_code, body=""):
            self.status_code = status_code
            self.content = body.encode("cp1252")
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"HTTP {self.status_code}")
        def close(self):
            pass

    class FakeSession:
        def __init__(self):
            self.headers = {}
        def get(self, url, timeout=20):
            if url.endswith("/E0.csv"):
                return FakeResponse(200, csv_text)
            return FakeResponse(404)
        def close(self):
            pass

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS)
    writer.writeheader()
    seen = set()
    summary = _append_current_season_fallback(
        FakeSession(), writer, seen, date(2026, 9, 1), date(2026, 10, 1)
    )
    rows = list(csv.DictReader(io.StringIO(output.getvalue())))
    assert summary["files_checked"] == 22
    assert summary["files_available"] == 1
    assert summary["matches_added"] == 1
    assert summary["matches_by_competition"] == {"E0": 1}
    assert len(rows) == 1
    assert rows[0]["home_team"] == "Arsenal"
