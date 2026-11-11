from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.ingestion.fivedollar_history import (
    AVAILABILITY_LAG,
    AVAILABILITY_BASIS,
    load_fivedollar_finished_matches,
)

UTC = timezone.utc
RETRIEVED = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)


def fixture(fid, kickoff, *, status="finished", league_id=4160026622,
            home_id=10, away_id=20, home_goals=2, away_goals=1):
    return {
        "id": fid,
        "status": status,
        "kickoff_utc": kickoff.isoformat(),
        "league": {"id": league_id, "name": "England Premier League"},
        "teams": {
            "home": {"id": home_id, "name": "Home FC"},
            "away": {"id": away_id, "name": "Away FC"},
        },
        "goals": {"home": home_goals, "away": away_goals},
        "odds": {"1x2": {"home": 1.2, "draw": 4.0, "away": 9.0}},
        "home_elo": 2200,
        "away_elo": 1500,
    }


def test_history_adapter_uses_four_day_lag_and_ignores_market_fields():
    kickoff = RETRIEVED - timedelta(days=10)
    history = load_fivedollar_finished_matches(
        [fixture(1, kickoff)], retrieved_at_utc=RETRIEVED
    )
    row = history.matches[0]
    assert row.available_at_utc == kickoff + AVAILABILITY_LAG
    assert row.availability_basis == AVAILABILITY_BASIS
    assert row.home_team_id == "5dollar:4160026622:10"
    assert row.away_team_id == "5dollar:4160026622:20"
    assert row.home_goals == 2 and row.away_goals == 1
    assert row.season == "rolling-365d"
    assert history.manifest.point_in_time_certifiable is False
    assert history.manifest.model_training_approved is False
    assert history.manifest.raw_redistribution_allowed is False


def test_recent_matches_inside_four_day_embargo_are_excluded():
    recent = fixture(1, RETRIEVED - timedelta(days=2))
    history = load_fivedollar_finished_matches(
        [fixture(2, RETRIEVED - timedelta(days=10)), recent],
        retrieved_at_utc=RETRIEVED,
    )
    assert len(history.matches) == 1
    assert history.manifest.skipped_recent_embargo == 1


def test_non_finished_rows_are_not_training_labels():
    with pytest.raises(ValueError, match="NO_ELIGIBLE"):
        load_fivedollar_finished_matches(
            [fixture(1, RETRIEVED - timedelta(days=10), status="scheduled")],
            retrieved_at_utc=RETRIEVED,
        )


def test_duplicate_fixture_ids_are_counted_and_not_duplicated():
    row = fixture(1, RETRIEVED - timedelta(days=10))
    history = load_fivedollar_finished_matches(
        [row, row], retrieved_at_utc=RETRIEVED
    )
    assert len(history.matches) == 1
    assert history.manifest.duplicate_fixture_ids == 1


def test_invalid_team_or_score_rows_are_counted():
    bad = fixture(1, RETRIEVED - timedelta(days=10), home_id=10, away_id=10)
    with pytest.raises(ValueError, match="NO_ELIGIBLE"):
        load_fivedollar_finished_matches([bad], retrieved_at_utc=RETRIEVED)


def test_naive_retrieval_time_is_rejected():
    with pytest.raises(ValueError, match="MUST_BE_AWARE"):
        load_fivedollar_finished_matches(
            [fixture(1, RETRIEVED - timedelta(days=10))],
            retrieved_at_utc=datetime(2026, 11, 11, 12, 0),
        )
