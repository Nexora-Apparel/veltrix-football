from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.features.team_form import SettledMatch
from veltrix_v2.features.schedule_load import build_team_schedule_load_snapshot

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 11, 6, tzinfo=UTC)


def match(
    fixture_id,
    days_ago,
    *,
    available_days_ago=None,
    provider="strikerapi",
    team="team-a",
    opponent="team-b",
    competition="EPL",
):
    kickoff = CUTOFF - timedelta(days=days_ago)
    available = CUTOFF - timedelta(days=available_days_ago if available_days_ago is not None else days_ago - 0.5)
    return SettledMatch(
        provider=provider,
        provider_fixture_id=fixture_id,
        competition_key=competition,
        season="2026-27",
        kickoff_utc=kickoff,
        available_at_utc=available,
        status="FINISHED",
        home_provider_team_id=team,
        away_provider_team_id=opponent,
        home_goals=1,
        away_goals=0,
        source_observation_id=f"obs-{fixture_id}",
    )


def values(snapshot):
    return {feature.name: feature for feature in snapshot.features}


def build(rows, **overrides):
    args = dict(
        provider="strikerapi",
        fixture_provider_id="upcoming-fixture",
        team_provider_id="team-a",
        cutoff_utc=CUTOFF,
    )
    args.update(overrides)
    return build_team_schedule_load_snapshot(rows, **args)


def test_counts_cross_competition_schedule_load_in_rolling_windows():
    rows = [
        match("d2", 2, competition="EPL"),
        match("d6", 6, competition="UCL"),
        match("d10", 10, competition="EPL"),
        match("d20", 20, competition="UCL"),
        match("d35", 35, competition="EPL"),
    ]
    result = values(build(rows))
    assert result["days_since_last_match"].value == 2
    assert result["matches_last_7_days"].value == 2
    assert result["matches_last_14_days"].value == 3
    assert result["matches_last_30_days"].value == 4
    assert result["matches_last_30_days"].sample_size == 5


def test_future_or_not_yet_available_results_are_excluded():
    rows = [
        match("eligible", 3),
        match("late-result", 2, available_days_ago=-1),
        match("future-kickoff", -1, available_days_ago=-2),
        match("other-provider", 1, provider="other"),
    ]
    result = values(build(rows))
    assert result["matches_last_7_days"].value == 1
    assert result["days_since_last_match"].value == 3


def test_empty_history_is_explicitly_missing_without_fallback():
    result = values(build([]))
    assert result["days_since_last_match"].value is None
    assert result["days_since_last_match"].quality_state == "missing"
    assert result["days_since_last_match"].missing_reason


def test_duplicate_fixture_ids_are_rejected():
    row = match("duplicate", 3)
    with pytest.raises(ValueError, match="duplicate provider fixture IDs"):
        build([row, row])


def test_naive_cutoff_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        build([], cutoff_utc=datetime(2026, 11, 11, 6))
