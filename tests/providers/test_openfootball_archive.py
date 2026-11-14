from datetime import date, datetime, timezone

import pytest

from veltrix_v2.models.poisson import MatchObservation, observation_eligible_as_of
from veltrix_v2.providers.openfootball_archive import parse_archive

UTC = timezone.utc
SHA = "94624a1b29c197cc9ac0d318a354e7f8062bb81e"
SNAPSHOT = datetime(2026, 8, 21, 7, 43, 54, tzinfo=UTC)
IMPORTED = datetime(2026, 11, 14, 0, 42, tzinfo=UTC)
SAMPLE = """= Nigeria Professional League 2025/2026
# Retrieved 2026-08-21
▪ Matchday 1
  Fri Aug 22 2025
           Remo Stars FC              v Rivers United FC           1-1
           El-Kanemi Warriors FC      v Bendel FC                  2-0
  Sun Aug 24 2025
           Shooting Stars SC          v Bayelsa United FC          0-1
"""


def test_parse_archive_preserves_date_precision_and_source_provenance():
    result = parse_archive(
        SAMPLE, competition_id="NGA_NPFL", source_path="africa/nigeria/2025-26_ng1.txt",
        snapshot_commit_sha=SHA, snapshot_available_at=SNAPSHOT, imported_at=IMPORTED,
    )
    assert result.season_title == "Nigeria Professional League 2025/2026"
    assert result.fixture_line_count == 3
    assert result.result_count == 3
    assert result.rejected_result_count == 0
    first = result.observations[0]
    assert first.kickoff_at is None
    assert first.kickoff_date == date(2025, 8, 22)
    assert first.available_at == SNAPSHOT
    assert first.recorded_at == IMPORTED
    assert first.home_team_id == "openfootball:NGA_NPFL:remo-stars-fc"
    assert len(result.content_sha256) == 64


def test_date_only_result_is_eligible_only_after_conservative_date_boundary():
    boundary = datetime(2025, 8, 24, 0, 0, tzinfo=UTC)
    observation = MatchObservation(
        fixture_id="date-only", competition_id="NGA_NPFL",
        home_team_id="openfootball:NGA_NPFL:home",
        away_team_id="openfootball:NGA_NPFL:away",
        kickoff_at=None, available_at=boundary, recorded_at=boundary,
        home_goals=1, away_goals=1, kickoff_date=date(2025, 8, 22),
    )
    before = datetime(2025, 8, 23, 23, 59, tzinfo=UTC)
    assert not observation_eligible_as_of(observation, cutoff_at=before)
    assert observation_eligible_as_of(observation, cutoff_at=boundary)


def test_fixture_without_score_is_not_fabricated_as_result():
    text = SAMPLE + "  Mon Aug 25 2025\n           Kano Pillars FC             v Wikki Tourists FC\n"
    result = parse_archive(
        text, competition_id="NGA_NPFL", source_path="season.txt",
        snapshot_commit_sha=SHA, snapshot_available_at=SNAPSHOT, imported_at=IMPORTED,
    )
    assert result.fixture_line_count == 4
    assert result.result_count == 3


def test_snapshot_that_cannot_prove_result_was_finished_is_rejected():
    early = datetime(2025, 8, 23, 0, 0, tzinfo=UTC)
    result = parse_archive(
        SAMPLE, competition_id="NGA_NPFL", source_path="season.txt",
        snapshot_commit_sha=SHA, snapshot_available_at=early, imported_at=IMPORTED,
    )
    assert result.result_count == 0
    assert result.rejected_result_count == 3


def test_invalid_snapshot_identity_and_time_order_fail_closed():
    with pytest.raises(ValueError, match="SNAPSHOT_COMMIT_SHA_INVALID"):
        parse_archive(SAMPLE, competition_id="NGA_NPFL", source_path="season.txt",
                      snapshot_commit_sha="bad", snapshot_available_at=SNAPSHOT, imported_at=IMPORTED)
    with pytest.raises(ValueError, match="IMPORT_PRECEDES_SNAPSHOT_PUBLICATION"):
        parse_archive(SAMPLE, competition_id="NGA_NPFL", source_path="season.txt",
                      snapshot_commit_sha=SHA, snapshot_available_at=SNAPSHOT,
                      imported_at=datetime(2026, 8, 20, tzinfo=UTC))
