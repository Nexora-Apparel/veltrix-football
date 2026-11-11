from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.features.elo import build_elo_snapshot
from veltrix_v2.features.team_form import SettledMatch

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 11, 6, tzinfo=UTC)


def match(fid, home, away, hg, ag, day, *, competition="EPL", available_day=None):
    kickoff = CUTOFF - timedelta(days=day)
    available = CUTOFF - timedelta(days=day - 0.1) if available_day is None else CUTOFF + timedelta(days=available_day)
    return SettledMatch(
        provider="strikerapi", provider_fixture_id=fid,
        competition_key=competition, season="2026-27",
        kickoff_utc=kickoff, available_at_utc=available,
        status="FINISHED", home_provider_team_id=home,
        away_provider_team_id=away, home_goals=hg, away_goals=ag,
        source_observation_id=f"obs-{fid}",
    )


def build(rows, **kwargs):
    args = dict(
        provider="strikerapi", fixture_provider_id="upcoming",
        competition_key="EPL", home_team_provider_id="A",
        away_team_provider_id="B", cutoff_utc=CUTOFF,
    )
    args.update(kwargs)
    return build_elo_snapshot(rows, **args)


def by_name(snapshot):
    return {item.name: item for item in snapshot.features}


def test_no_history_is_missing_not_a_fabricated_rating():
    result = by_name(build([]))
    assert result["elo_home_rating"].value is None
    assert result["elo_away_rating"].value is None
    assert result["elo_rating_difference"].value is None
    assert result["elo_home_rating"].quality_state == "missing"


def test_rating_updates_from_results_and_is_competition_scoped():
    rows = [
        match("one", "A", "B", 2, 0, 4),
        match("two", "A", "B", 1, 0, 3),
        match("other-league", "A", "B", 0, 5, 2, competition="LaLiga"),
    ]
    result = by_name(build(rows))
    assert result["elo_home_rating"].value > 1500
    assert result["elo_away_rating"].value < 1500
    assert result["elo_rating_difference"].value > 0
    assert result["elo_home_rating"].sample_size == 2
    assert result["elo_home_rating"].quality_state == "low_sample"


def test_future_and_late_available_results_are_excluded():
    rows = [
        match("eligible", "A", "B", 1, 0, 3),
        match("late", "A", "B", 0, 4, 2, available_day=1),
    ]
    result = by_name(build(rows))
    assert result["elo_home_rating"].sample_size == 1
    assert result["elo_home_rating"].value > 1500


def test_cold_start_opponent_keeps_difference_missing():
    result = by_name(build([match("one", "A", "C", 2, 0, 3)]))
    assert result["elo_home_rating"].value is not None
    assert result["elo_away_rating"].value is None
    assert result["elo_rating_difference"].value is None
    assert result["elo_home_expected_score"].value is None


def test_duplicate_fixture_identity_fails_closed():
    row = match("dup", "A", "B", 1, 0, 3)
    with pytest.raises(ValueError, match="duplicate provider fixture IDs"):
        build([row, row])


def test_naive_cutoff_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        build([], cutoff_utc=datetime(2026, 11, 11, 6))


def test_invalid_elo_parameters_are_rejected():
    with pytest.raises(ValueError, match="K-factor"):
        build([], k_factor=0)
