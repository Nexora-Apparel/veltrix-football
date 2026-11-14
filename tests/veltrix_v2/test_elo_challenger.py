from datetime import datetime, timedelta, timezone

from veltrix_v2.evaluation.elo_challenger import evaluate_elo_challenger
from veltrix_v2.models.poisson import MatchObservation

UTC = timezone.utc
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def match(fid, home, away, hg, ag, day, *, certifiable=True, available=None, recorded=None):
    kickoff = BASE + timedelta(days=day)
    return MatchObservation(
        fixture_id=fid, competition_id="league", home_team_id=home,
        away_team_id=away, kickoff_at=kickoff,
        available_at=available or kickoff + timedelta(hours=2),
        recorded_at=recorded or kickoff + timedelta(hours=3),
        home_goals=hg, away_goals=ag,
        point_in_time_certifiable=certifiable,
    )


def test_challenger_uses_only_certified_pre_cutoff_history():
    rows = [
        match("1", "A", "B", 3, 0, 1),
        match("2", "A", "C", 2, 0, 2),
        match("3", "A", "B", 2, 0, 3),
        match("4", "B", "A", 9, 0, 4, certifiable=False),
        match("5", "A", "B", 1, 0, 5),
    ]
    report = evaluate_elo_challenger(
        rows, evaluation_as_of=BASE + timedelta(days=10)
    )
    assert report.scored_targets == 3
    assert report.skipped_uncertified_targets == 1
    assert report.metrics is not None
    assert report.metrics.sample_count == 3


def test_no_future_training_and_duplicate_target_is_excluded():
    rows = [
        match("1", "A", "B", 2, 0, 1),
        match("2", "B", "A", 0, 1, 2),
        match("dup", "A", "B", 4, 0, 3),
        match("dup", "B", "A", 0, 4, 4),
        match("future", "A", "B", 8, 0, 20),
    ]
    report = evaluate_elo_challenger(
        rows, evaluation_as_of=BASE + timedelta(days=10)
    )
    assert report.duplicate_fixture_rows == 2
    assert all(x.fixture_id not in {"dup", "future"} for x in rows[:0])
    assert report.scored_targets == 1


def test_naive_evaluation_timestamp_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="ELO_EVALUATION_AS_OF_MUST_BE_AWARE"):
        evaluate_elo_challenger([], evaluation_as_of=datetime(2026, 1, 1))
