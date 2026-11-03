from pathlib import Path


def test_watchdog_rejects_old_same_day_reports():
    workflow = Path(".github/workflows/daily-report-watchdog.yml").read_text(encoding="utf-8")
    assert "max_age_minutes = 90" in workflow
    assert "age_fresh = report_age_minutes is not None and 0 <= report_age_minutes <= max_age_minutes" in workflow
    assert "and age_fresh" in workflow
    assert 'print(f"report_age_minutes=' in workflow
