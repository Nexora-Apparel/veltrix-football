from datetime import datetime, timezone

import pytest

from veltrix_v2.ingestion.club_football_match_data import (
    AVAILABILITY_BASIS,
    load_club_football_match_data,
)

UTC = timezone.utc
HEADER = (
    "source,division,match_date,home_team,away_team,home_goals,away_goals,full_time_result,"
    "home_elo,away_elo,home_form3,away_form3,home_odds,draw_odds,away_odds"
)


def write_csv(path, rows):
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def row(division="E0", day="2026-08-01", home="Team A", away="Team B",
        hg="2", ag="1", result="H", source="xgabora/Club-Football-Match-Data"):
    return f"{source},{division},{day},{home},{away},{hg},{ag},{result},1500,1490,6,4,2.0,3.0,4.0"


def test_adapter_creates_date_only_records_and_ignores_odds_elo(tmp_path):
    path = write_csv(tmp_path / "matches.csv", [row()])
    dataset = load_club_football_match_data(
        path,
        retrieved_at_utc=datetime(2026, 11, 9, 12, tzinfo=UTC),
        divisions=["E0"],
    )
    assert len(dataset.matches) == 1
    match = dataset.matches[0]
    assert match.kickoff_utc == datetime(2026, 8, 1, 12, tzinfo=UTC)
    assert match.available_at_utc == datetime(2026, 8, 5, 0, tzinfo=UTC)
    assert match.availability_basis == AVAILABILITY_BASIS
    assert dataset.manifest.point_in_time_certifiable is False
    assert dataset.manifest.source_publication_timestamps_available is False
    assert "home_odds" in dataset.manifest.ignored_feature_columns
    assert "home_elo" in dataset.manifest.ignored_feature_columns


def test_adapter_filters_requested_divisions(tmp_path):
    path = write_csv(tmp_path / "matches.csv", [row("E0"), row("SP1")])
    dataset = load_club_football_match_data(
        path,
        retrieved_at_utc=datetime(2026, 11, 9, 12, tzinfo=UTC),
        divisions=["E0"],
    )
    assert len(dataset.matches) == 1
    assert dataset.matches[0].competition_key == "cfmd:E0"


def test_adapter_rejects_duplicate_fixture_keys(tmp_path):
    path = write_csv(tmp_path / "matches.csv", [row(), row()])
    with pytest.raises(ValueError, match="DUPLICATE_MATCH_KEY"):
        load_club_football_match_data(
            path,
            retrieved_at_utc=datetime(2026, 11, 9, 12, tzinfo=UTC),
            divisions=["E0"],
        )


def test_adapter_rejects_result_conflict(tmp_path):
    path = write_csv(tmp_path / "matches.csv", [row(result="A")])
    with pytest.raises(ValueError, match="RESULT_CONFLICT"):
        load_club_football_match_data(
            path,
            retrieved_at_utc=datetime(2026, 11, 9, 12, tzinfo=UTC),
            divisions=["E0"],
        )


def test_adapter_rejects_wrong_source(tmp_path):
    path = write_csv(tmp_path / "matches.csv", [row(source="unknown/source")])
    with pytest.raises(ValueError, match="SOURCE_IDENTITY"):
        load_club_football_match_data(
            path,
            retrieved_at_utc=datetime(2026, 11, 9, 12, tzinfo=UTC),
            divisions=["E0"],
        )


def test_adapter_rejects_naive_retrieval_timestamp(tmp_path):
    path = write_csv(tmp_path / "matches.csv", [row()])
    with pytest.raises(ValueError, match="MUST_BE_AWARE"):
        load_club_football_match_data(
            path,
            retrieved_at_utc=datetime(2026, 11, 9, 12),
            divisions=["E0"],
        )
