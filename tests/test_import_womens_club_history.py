from datetime import date
import csv
import io

from scripts import import_womens_club_history as importer


def sample(**overrides):
    row = {
        "date": "2024-10-01", "tier": "1",
        "division": "FA Women's Super League (WSL)",
        "match_id": "M-2024-2025-1-001-M", "season": "2024-2025",
        "home_team_id": "T-001-T", "home_team_name": "Arsenal Women",
        "away_team_id": "T-002-T", "away_team_name": "Chelsea Women",
        "home_team_score": "2", "away_team_score": "1",
    }
    row.update(overrides)
    return row


def test_normalizes_womens_club_match_and_preserves_category_ids():
    result = importer.normalize_match(sample(), date(2024, 1, 1), date(2025, 1, 1))
    assert result is not None
    assert result["category"] == "WOMENS_CLUB"
    assert result["division"] == "ENG_WOMENS_TIER_1"
    assert result["home_team_id"] == "T-001-T"
    assert result["full_time_result"] == "H"
    assert result["home_goals"] == 2


def test_rejects_bad_scores_ids_and_out_of_range_dates():
    assert importer.normalize_match(sample(home_team_score="-1"), date(2024, 1, 1), date(2025, 1, 1)) is None
    assert importer.normalize_match(sample(away_team_id="T-001-T"), date(2024, 1, 1), date(2025, 1, 1)) is None
    assert importer.normalize_match(sample(date="2023-10-01"), date(2024, 1, 1), date(2025, 1, 1)) is None
    assert importer.normalize_match(sample(tier="3"), date(2024, 1, 1), date(2025, 1, 1)) is None


def test_import_writes_separate_category_file_and_reports_coverage(tmp_path, monkeypatch):
    fields = list(sample().keys())
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows([sample(), sample(match_id="M-2024-2025-1-002-M", date="2024-10-08",
                                       home_team_id="T-003-T", home_team_name="Liverpool Women")])

    class Response:
        content = stream.getvalue().encode("utf-8")
        def raise_for_status(self):
            pass
        def close(self):
            pass

    monkeypatch.setattr(importer.requests, "get", lambda *args, **kwargs: Response())
    output = tmp_path / "womens.csv"
    report = importer.import_dataset("2024-01-01", "2025-01-01", str(output))
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert report["matches_added"] == 2
    assert report["matches_by_division"] == {"ENG_WOMENS_TIER_1": 2}
    assert all(row["category"] == "WOMENS_CLUB" for row in rows)
    assert all(row["division"].startswith("ENG_WOMENS_") for row in rows)
    assert all(row["source_match_id"] for row in rows)


def test_import_deduplicates_source_match_ids(tmp_path, monkeypatch):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(sample().keys()))
    writer.writeheader()
    writer.writerows([sample(), sample()])
    class Response:
        content = stream.getvalue().encode("utf-8")
        def raise_for_status(self):
            pass
        def close(self):
            pass
    monkeypatch.setattr(importer.requests, "get", lambda *args, **kwargs: Response())
    report = importer.import_dataset("2024-01-01", "2025-01-01", str(tmp_path / "womens.csv"))
    assert report["matches_added"] == 1
    assert report["duplicate_source_match_ids"] == 1
