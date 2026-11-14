from datetime import date, datetime, timedelta, timezone

import pytest

from veltrix_v2.models.form import team_form_as_of
from veltrix_v2.models.poisson import MatchObservation

UTC = timezone.utc
CUTOFF = datetime(2026, 11, 14, 12, tzinfo=UTC)


def match(fid, home, away, hg, ag, days, *, certifiable=True, available=None,
          recorded=None, kickoff=None, kickoff_date=None):
    start = kickoff or CUTOFF - timedelta(days=days)
    return MatchObservation(
        fixture_id=fid, competition_id="league", home_team_id=home, away_team_id=away,
        kickoff_at=None if kickoff_date else start,
        available_at=available or start + timedelta(hours=2),
        recorded_at=recorded or start + timedelta(hours=3),
        home_goals=hg, away_goals=ag, kickoff_date=kickoff_date,
        point_in_time_certifiable=certifiable,
    )


def test_form_counts_points_goals_and_venue_splits():
    rows = [
        match("1", "A", "B", 2, 0, 6),
        match("2", "C", "A", 1, 1, 5),
        match("3", "A", "D", 0, 1, 4),
        match("4", "B", "A", 0, 3, 3),
    ]
    result = team_form_as_of(rows, competition_id="league", home_team_id="A",
                             away_team_id="B", cutoff_at=CUTOFF)
    assert result.home.matches == 4
    assert (result.home.wins, result.home.draws, result.home.losses) == (2, 1, 1)
    assert result.home.points_per_match == pytest.approx(1.75)
    assert result.home.home_matches == 2
    assert result.home.away_matches == 2
    assert result.home.home_goals_for_per_match == pytest.approx(1.0)
    assert result.home.away_goals_for_per_match == pytest.approx(2.0)
    assert result.home.rest_days == pytest.approx(3.0)


def test_late_future_and_non_certifiable_rows_are_excluded():
    rows = [
        match("1", "A", "B", 1, 0, 6),
        match("2", "B", "A", 9, 0, 5, certifiable=False),
        match("3", "A", "B", 9, 0, 4, available=CUTOFF + timedelta(seconds=1)),
        match("4", "B", "A", 9, 0, 3, recorded=CUTOFF + timedelta(seconds=1)),
        match("5", "A", "B", 9, 0, 2, kickoff=CUTOFF + timedelta(minutes=1)),
    ]
    result = team_form_as_of(rows, competition_id="league", home_team_id="A",
                             away_team_id="B", cutoff_at=CUTOFF)
    assert result.home.matches == 1
    assert result.eligible_match_count == 1
    assert result.excluded_non_certifiable_count == 1


def test_last_five_form_uses_latest_results_only():
    rows = [match(str(i), "A", "B", 0, 1, 10 - i) for i in range(1, 5)]
    rows += [match(str(i), "A", "B", 3, 0, 10 - i) for i in range(5, 9)]
    result = team_form_as_of(rows, competition_id="league", home_team_id="A",
                             away_team_id="B", cutoff_at=CUTOFF)
    assert result.home.last_five_points_per_match == pytest.approx(2.4)


def test_date_only_latest_result_does_not_invent_rest_days():
    available = datetime(2026, 8, 21, 7, 43, tzinfo=UTC)
    rows = [
        match("date-a", "A", "C", 1, 0, 100, available=available,
              recorded=available, kickoff_date=date(2026, 8, 1)),
        match("date-b", "D", "B", 1, 1, 100, available=available,
              recorded=available, kickoff_date=date(2026, 8, 1)),
    ]
    result = team_form_as_of(rows, competition_id="league", home_team_id="A",
                             away_team_id="B", cutoff_at=CUTOFF)
    assert result.home.latest_result_was_date_only
    assert result.home.rest_days is None


def test_duplicate_ids_and_unknown_team_history_fail_closed():
    duplicate = match("same", "A", "B", 2, 0, 5)
    rows = [duplicate, match("same", "B", "A", 0, 2, 4)]
    with pytest.raises(ValueError, match="TEAM_FORM_HOME_HISTORY_UNAVAILABLE"):
        team_form_as_of(rows, competition_id="league", home_team_id="A",
                        away_team_id="B", cutoff_at=CUTOFF)
    with pytest.raises(ValueError, match="TEAM_FORM_AWAY_HISTORY_UNAVAILABLE"):
        team_form_as_of([match("1", "A", "C", 1, 0, 5)],
                        competition_id="league", home_team_id="A",
                        away_team_id="UNKNOWN", cutoff_at=CUTOFF)
