import pytest

from veltrix_v2.ingestion.openplay_match_coverage import adapt_match_record


def match(**overrides):
    row = {
        "match_id": 12345,
        "comp": "EPL",
        "season": "2024/2025",
        "date": "2025-02-01",
        "home_team_id": 10,
        "away_team_id": 20,
        "home_score": 2,
        "away_score": 1,
        "xg_model": "openplay-xg-v1",
        "score_matches_events": True,
        "scraped_at": "2025-02-02 10:00:00",
    }
    row.update(overrides)
    return row


COVERAGE = [{
    "comp": "EPL", "season": "2024/2025", "in_v1_scope": "true",
    "matches_played": "380", "matches_with_events": "379", "gaps": "1",
    "coverage_pct": "99.74", "matches_with_data_issues": "2",
}]


def test_match_record_joins_coverage_and_preserves_xg_model_identity():
    item = adapt_match_record(match(), coverage_rows=COVERAGE)
    assert item.match_id == "12345"
    assert item.source_match_date == "2025-02-01"
    assert item.xg_model_id == "openplay-xg-v1"
    assert item.competition_season_in_scope is True
    assert item.competition_season_matches_played == 380
    assert item.competition_season_matches_with_events == 379
    assert item.competition_season_gaps == 1
    assert item.quality_state == "eligible_for_historical_research"


def test_known_gap_and_issue_rows_quarantine_match():
    gap = [{"match_id": "12345", "comp": "EPL", "season": "2024/2025"}]
    item = adapt_match_record(match(), coverage_rows=COVERAGE, known_gap_rows=gap)
    assert item.known_gap is True
    assert item.quality_state == "quarantined_known_gap"

    issues = [{"match_id": "12345", "issue": "incomplete-lineup"}]
    item = adapt_match_record(match(), coverage_rows=COVERAGE, data_issue_rows=issues)
    assert item.data_issue_codes == ("incomplete-lineup",)
    assert item.quality_state == "quarantined_known_data_issue"


def test_missing_coverage_is_quarantined_not_assumed_complete():
    item = adapt_match_record(match(), coverage_rows=[])
    assert item.competition_season_in_scope is False
    assert item.competition_season_coverage_pct is None
    assert item.quality_state == "quarantined_outside_declared_coverage"


def test_duplicate_coverage_rows_fail_closed():
    with pytest.raises(ValueError, match="DUPLICATE_COMPETITION_SEASON_COVERAGE"):
        adapt_match_record(match(), coverage_rows=COVERAGE + COVERAGE)


def test_missing_or_invalid_xg_identity_and_score_are_rejected():
    with pytest.raises(ValueError, match="REQUIRED_FIELD:xg_model"):
        adapt_match_record(match(xg_model=""), coverage_rows=COVERAGE)
    with pytest.raises(ValueError, match="INVALID_INTEGER:home_score"):
        adapt_match_record(match(home_score=2.5), coverage_rows=COVERAGE)


def test_source_date_and_scraped_timestamp_are_not_reinterpreted():
    item = adapt_match_record(match(date="2025-02-01", scraped_at="2025-02-02 10:00:00"), coverage_rows=COVERAGE)
    assert item.source_match_date == "2025-02-01"
    assert item.source_scraped_at == "2025-02-02 10:00:00"
