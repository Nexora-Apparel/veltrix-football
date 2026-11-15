from datetime import datetime, timezone

from veltrix_v2.models.poisson import MatchObservation, observation_eligible_as_of


def test_timestamped_but_uncertified_observation_is_not_pit_eligible():
    kickoff = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    row = MatchObservation(
        fixture_id="fixture-1", competition_id="league-1",
        home_team_id="home", away_team_id="away",
        kickoff_at=kickoff, available_at=kickoff,
        recorded_at=kickoff, home_goals=1, away_goals=0,
        point_in_time_certifiable=False,
    )
    assert not observation_eligible_as_of(
        row, cutoff_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        competition_id="league-1",
    )
