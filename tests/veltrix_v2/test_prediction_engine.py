from datetime import datetime, timedelta, timezone
import hashlib

from veltrix_v2.models.engine import PredictionTarget, predict_batch
from veltrix_v2.models.poisson import MatchObservation

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 14, 12, tzinfo=UTC)


def history(n=120):
    rows = []
    teams = ["A", "B", "C", "D", "E", "F"]
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(n):
        kickoff = start + timedelta(days=i)
        home = teams[i % len(teams)]
        away = teams[(i + 1) % len(teams)]
        rows.append(MatchObservation(
            fixture_id=f"history-{i}", competition_id="league",
            home_team_id=home, away_team_id=away, kickoff_at=kickoff,
            available_at=kickoff + timedelta(hours=2),
            recorded_at=kickoff + timedelta(hours=3),
            home_goals=1 + (i % 3 == 0), away_goals=i % 2,
        ))
    return rows


def target(i, *, kickoff=None, retrieved=None, home="A", away="B", fixture_id=None):
    kickoff = kickoff or CUTOFF + timedelta(hours=3 + i)
    retrieved = retrieved or CUTOFF - timedelta(minutes=5)
    return PredictionTarget(
        fixture_id=fixture_id or f"target-{i}", competition_id="league",
        home_team_id=home, away_team_id=away, kickoff_at=kickoff,
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        source_fixture_id=str(1000 + i), retrieved_at=retrieved,
        payload_sha256=hashlib.sha256(f"target-{i}".encode()).hexdigest(),
        rights_approval_id="approval-5dollar-community-fixture-result-2026-11",
    )


def test_batch_generates_forecasts_for_all_eligible_targets_in_kickoff_order():
    targets = [target(2), target(0), target(1, home="B", away="A")]
    report = predict_batch(history(), targets, cutoff_at=CUTOFF)
    assert report.requested_target_count == 3
    assert report.forecast_count == 3
    assert [x.fixture_id for x in report.forecasts] == ["target-0", "target-1", "target-2"]
    assert all(not x.model.publishable for x in report.forecasts)


def test_batch_caps_at_25_without_ranking_by_favourite_or_probability():
    targets = [target(i) for i in range(30)]
    report = predict_batch(history(), targets, cutoff_at=CUTOFF, max_fixtures=25)
    assert report.forecast_count == 25
    assert report.skipped_capacity == 5
    assert [x.fixture_id for x in report.forecasts] == [f"target-{i}" for i in range(25)]


def test_duplicate_ids_past_targets_and_not_yet_known_targets_are_skipped():
    duplicate_a = target(0, fixture_id="duplicate")
    duplicate_b = target(1, fixture_id="duplicate")
    past = target(2, kickoff=CUTOFF)
    late = target(3, retrieved=CUTOFF + timedelta(seconds=1))
    report = predict_batch(history(), [duplicate_a, duplicate_b, past, late], cutoff_at=CUTOFF)
    assert report.skipped_duplicate_target_ids == 2
    assert report.skipped_invalid_targets == 1
    assert report.skipped_targets_not_yet_known == 1
    assert report.forecast_count == 0


def test_batch_does_not_fabricate_predictions_when_team_history_is_missing():
    report = predict_batch(history(), [target(0, home="UNKNOWN")], cutoff_at=CUTOFF)
    assert report.forecast_count == 0
    assert report.skipped_no_history == 1


def test_batch_configuration_is_bounded_and_cutoff_must_be_aware():
    import pytest

    with pytest.raises(ValueError, match="MAX_FIXTURES_MUST_BE_1_TO_25"):
        predict_batch(history(), [], cutoff_at=CUTOFF, max_fixtures=26)
    with pytest.raises(ValueError, match="BATCH_CUTOFF_MUST_BE_TIMEZONE_AWARE"):
        predict_batch(history(), [], cutoff_at=datetime(2026, 11, 14, 12))


def test_batch_counts_untyped_targets_as_invalid():
    report = predict_batch(history(), [object()], cutoff_at=CUTOFF)
    assert report.requested_target_count == 1
    assert report.skipped_invalid_targets == 1
    assert report.forecast_count == 0


def test_batch_propagates_recency_half_life_to_each_forecast():
    report = predict_batch(history(), [target(0)], cutoff_at=CUTOFF,
                           recency_half_life_days=30)
    assert report.forecasts[0].model.recency_half_life_days == 30


def test_batch_rejects_invalid_recency_even_when_no_targets_exist():
    import pytest
    with pytest.raises(ValueError, match="RECENCY_HALF_LIFE_MUST_BE_POSITIVE_FINITE"):
        predict_batch(history(), [], cutoff_at=CUTOFF, recency_half_life_days=0)
