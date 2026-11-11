from datetime import datetime, timedelta, timezone
from dataclasses import replace

import pytest

from veltrix_v2.features.team_form import SettledMatch, build_team_form_snapshot

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 11, 6, tzinfo=UTC)


def match(
    fixture_id="fx-1", kickoff=CUTOFF - timedelta(days=2),
    available=CUTOFF - timedelta(days=1), home="team-a", away="team-b",
    home_goals=2, away_goals=1, competition="EPL", season="2026-27",
):
    return SettledMatch(
        provider="strikerapi", provider_fixture_id=fixture_id,
        competition_key=competition, season=season,
        kickoff_utc=kickoff, available_at_utc=available,
        status="FINISHED", home_provider_team_id=home,
        away_provider_team_id=away, home_goals=home_goals,
        away_goals=away_goals, source_observation_id=f"obs-{fixture_id}",
    )


def build(rows, **overrides):
    args = dict(
        provider="strikerapi", fixture_provider_id="upcoming-fx",
        team_provider_id="team-a", competition_key="EPL",
        season="2026-27", cutoff_utc=CUTOFF,
    )
    args.update(overrides)
    return build_team_form_snapshot(rows, **args)


def by_name(snapshot):
    return {item.name: item for item in snapshot.features}


def test_uses_only_completed_results_available_before_cutoff():
    rows = [
        match("old", kickoff=CUTOFF - timedelta(days=20)),
        match("late-available", available=CUTOFF + timedelta(seconds=1)),
        match("future-kickoff", kickoff=CUTOFF + timedelta(minutes=1),
                  available=CUTOFF + timedelta(hours=1)),
        match("wrong-league", competition="LaLiga"),
        match("eligible", home_goals=3, away_goals=0),
    ]
    result = by_name(build(rows))
    assert result["goals_for_per_match"].sample_size == 2
    assert result["goals_for_per_match"].quality_state == "low_sample"
    assert set(result["goals_for_per_match"].source_observation_ids) == {"obs-old", "obs-eligible"}


def test_empty_history_is_explicitly_missing_not_fallback():
    result = by_name(build([]))
    assert result["goals_for_per_match"].value is None
    assert result["goals_for_per_match"].quality_state == "missing"
    assert result["goals_for_per_match"].missing_reason


def test_away_team_orientation_is_correct():
    row = match(home="opponent", away="team-a", home_goals=0, away_goals=2)
    result = by_name(build([row]))
    assert result["goals_for_per_match"].value == 2
    assert result["goals_against_per_match"].value == 0
    assert result["points_per_match"].value == 3


def test_result_cannot_be_available_before_kickoff():
    with pytest.raises(ValueError, match="available before kickoff"):
        match(available=CUTOFF - timedelta(days=4), kickoff=CUTOFF - timedelta(days=2))


def test_naive_cutoff_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        build([], cutoff_utc=datetime(2026, 11, 11, 6))


def test_duplicate_fixture_ids_fail_closed():
    row = match("duplicate")
    with pytest.raises(ValueError, match="duplicate provider fixture IDs"):
        build([row, replace(row, home_goals=0, away_goals=1)])


def test_duplicate_source_observation_ids_fail_closed():
    first = match("first")
    second = replace(match("second"), source_observation_id=first.source_observation_id)
    with pytest.raises(ValueError, match="duplicate source observation IDs"):
        build([first, second])


def test_non_finite_half_life_is_rejected():
    with pytest.raises(ValueError, match="finite positive half-life"):
        build([match()], half_life_matches=float("nan"))
