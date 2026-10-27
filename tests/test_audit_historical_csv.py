import csv

from scripts.audit_historical_csv import audit_csv, render_markdown


def test_audit_reports_integrity_coverage_and_missingness(tmp_path):
    path = tmp_path / "matches.csv"
    columns = [
        "match_date", "division", "home_team", "away_team", "home_goals",
        "away_goals", "full_time_result", "home_odds",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerow({
            "match_date": "2022-01-01", "division": "E0", "home_team": "Alpha",
            "away_team": "Beta", "home_goals": 2, "away_goals": 1,
            "full_time_result": "H", "home_odds": "1.8",
        })
        writer.writerow({
            "match_date": "2024-02-01", "division": "E0", "home_team": "Beta",
            "away_team": "Alpha", "home_goals": 0, "away_goals": 0,
            "full_time_result": "D", "home_odds": "",
        })
        writer.writerow({
            "match_date": "2024-02-01", "division": "E0", "home_team": "Beta",
            "away_team": "Alpha", "home_goals": 0, "away_goals": 0,
            "full_time_result": "D", "home_odds": "",
        })

    report = audit_csv(path)
    assert report["rows"] == 3
    assert report["invalid_rows"] == 0
    assert report["duplicate_match_keys"] == 1
    assert report["integrity_status"] == "FAIL"
    assert report["competition_count"] == 1
    assert report["competitions"]["E0"]["matches_by_calendar_year"] == {"2022": 1, "2024": 2}
    assert report["competitions"]["E0"]["unobserved_calendar_years_between_first_and_last"] == ["2023"]
    assert report["missing_values"]["home_odds"]["count"] == 2
    assert "not a confirmed missing-fixture gap" in report["coverage_note"]
    assert "E0" in render_markdown(report)


def test_audit_rejects_missing_required_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("match_date,home_team\n2024-01-01,Alpha\n", encoding="utf-8")
    try:
        audit_csv(path)
    except ValueError as exc:
        assert "missing required columns" in str(exc)
    else:
        raise AssertionError("Missing required columns should be rejected")
