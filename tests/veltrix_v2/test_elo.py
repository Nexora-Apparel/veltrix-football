from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.models.elo import ratings_as_of
from veltrix_v2.models.poisson import MatchObservation

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 14, 12, tzinfo=UTC)


def row(fid, home, away, hg, ag, *, days=1, available=None, recorded=None,
        competition="league", certifiable=True, kickoff=None):
    start = kickoff or CUTOFF - timedelta(days=days)
    return MatchObservation(
        fixture_id=fid, competition_id=competition,
        home_team_id=home, away_team_id=away,
        kickoff_at=start, available_at=available or start + timedelta(hours=2),
        recorded_at=recorded or start + timedelta(hours=3),
        home_goals=hg, away_goals=ag,
        point_in_time_certifiable=certifiable,
    )


def test_ratings_are_competition_scoped_and_return_feature_not_prediction():
    rows = [
        row("1", "A", "B", 3, 0, days=5),
        row("2", "B", "A", 0, 1, days=4),
        row("3", "X", "Y", 8, 0, days=3, competition="other"),
    ]
    result = ratings_as_of(rows, competition_id="league", home_team_id="A",
                           away_team_id="B", cutoff_at=CUTOFF)
    assert result.eligible_match_count == 2
    assert result.home_team.rating > result.away_team.rating
    assert result.home_team.matches_played == 2
    assert result.away_team.matches_played == 2
    assert 0 < result.expected_home_score < 1
    assert not hasattr(result, "home_win")


def test_future_late_and_non_certifiable_results_do_not_update_ratings():
    base = [
        row("1", "A", "B", 1, 0, days=5),
        row("2", "B", "A", 0, 1, days=4, certifiable=False),
        row("3", "A", "B", 9, 0, days=3,
            available=CUTOFF + timedelta(seconds=1)),
        row("4", "B", "A", 9, 0, days=2,
            recorded=CUTOFF + timedelta(seconds=1)),
        row("5", "A", "B", 9, 0, days=1,
            kickoff=CUTOFF + timedelta(minutes=1)),
    ]
    result = ratings_as_of(base, competition_id="league", home_team_id="A",
                           away_team_id="B", cutoff_at=CUTOFF)
    assert result.eligible_match_count == 1
    assert result.excluded_non_certifiable_count == 1


def test_duplicate_fixture_ids_are_excluded_without_input_order_preference():
    first = row("duplicate", "A", "B", 4, 0, days=4)
    conflicting = row("duplicate", "B", "A", 0, 4, days=3)
    rows = [first, conflicting, row("other", "B", "A", 0, 1, days=2)]
    result = ratings_as_of(rows, competition_id="league", home_team_id="A",
                           away_team_id="B", cutoff_at=CUTOFF)
    assert result.eligible_match_count == 1


def test_same_timestamp_matches_are_applied_as_one_round():
    same = CUTOFF - timedelta(days=2)
    rows = [
        row("a", "A", "B", 3, 0, kickoff=same),
        row("b", "C", "A", 0, 2, kickoff=same),
        row("c", "B", "C", 1, 1, kickoff=same),
    ]
    forward = ratings_as_of(rows, competition_id="league", home_team_id="A",
                            away_team_id="B", cutoff_at=CUTOFF)
    reverse = ratings_as_of(list(reversed(rows)), competition_id="league",
                            home_team_id="A", away_team_id="B", cutoff_at=CUTOFF)
    assert forward == reverse


def test_unknown_team_fails_closed_instead_of_returning_initial_rating():
    rows = [row("1", "A", "B", 1, 0)]
    with pytest.raises(ValueError, match="ELO_AWAY_TEAM_HAS_NO_CERTIFIED_HISTORY"):
        ratings_as_of(rows, competition_id="league", home_team_id="A",
                      away_team_id="UNKNOWN", cutoff_at=CUTOFF)


def test_invalid_configuration_and_naive_cutoff_are_rejected():
    with pytest.raises(ValueError, match="ELO_K_FACTOR_INVALID"):
        ratings_as_of([row("1", "A", "B", 1, 0)], competition_id="league",
                      home_team_id="A", away_team_id="B", cutoff_at=CUTOFF,
                      k_factor=0)
    with pytest.raises(ValueError, match="ELO_CUTOFF_MUST_BE_TIMEZONE_AWARE"):
        ratings_as_of([], competition_id="league", home_team_id="A",
                      away_team_id="B", cutoff_at=datetime(2026, 11, 14))
