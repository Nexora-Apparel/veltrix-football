from datetime import date

from veltrix_v2.ingestion.openfootball import parse_match
from veltrix_v2.ingestion.openfootball_reconcile import ReferenceFixture, reconcile_openfootball


def test_reconciliation_requires_exact_identity_crosswalk_and_scores():
    source = [
        parse_match({"date": "2026-10-01", "team1": "Arsenal FC", "team2": "Chelsea FC", "score": {"ft": [2, 0]}}, 0),
        parse_match({"date": "2026-10-02", "team1": "Liverpool FC", "team2": "Everton FC", "score": {}}, 1),
    ]
    reference = [
        ReferenceFixture("r1", "2026-10-01", "ars", "che", 2, 0, "finished"),
    ]
    result = reconcile_openfootball(source, reference, {"Arsenal FC": "ars", "Chelsea FC": "che"})
    assert result.openfootball_rows == 2
    assert result.reference_rows == 1
    assert result.comparable_rows == 1
    assert result.matched_rows == 1
    assert result.missing_openfootball_score == 1
    assert result.passed


def test_score_conflicts_fail_reconciliation():
    source = [parse_match({"date": "2026-10-01", "team1": "Arsenal FC", "team2": "Chelsea FC", "score": {"ft": [2, 0]}}, 0)]
    reference = [ReferenceFixture("r1", "2026-10-01", "ars", "che", 1, 0, "FT")]
    result = reconcile_openfootball(source, reference, {"Arsenal FC": "ars", "Chelsea FC": "che"})
    assert result.score_conflicts == 1
    assert not result.passed


def test_missing_team_crosswalk_is_quarantined_not_fuzzy_matched():
    source = [parse_match({"date": "2026-10-01", "team1": "Arsenal", "team2": "Chelsea", "score": {"ft": [2, 0]}}, 0)]
    result = reconcile_openfootball(source, [], {})
    assert result.identity_conflicts == 1
    assert not result.passed
