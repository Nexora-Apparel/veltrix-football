from __future__ import annotations

import json
from datetime import date, datetime, timezone

from scripts.veltrix_v2.collect_aimidas_snapshot import FileSpec
from scripts.veltrix_v2 import reconcile_aimidas_historical_identity as audit


def _row(**overrides):
    row = {
        "source_id": audit.SOURCE_ID,
        "source_repository": audit.REPOSITORY,
        "source_commit": audit.SOURCE_COMMIT,
        "source_path": "sample.csv",
        "source_git_blob_sha1": "a" * 40,
        "source_file_sha256": "b" * 64,
        "source_line_number": 2,
        "source_row_sha256": "c" * 64,
        "source_fixture_key": "aimidas:test:sample.csv:2",
        "competition": "England Premier League",
        "source_season_raw": "2016/2017",
        "derived_season_key": "2016-2017",
        "source_date_raw": "2016-08-13 11:30:00",
        "source_calendar_date": "2016-08-13",
        "home_name_raw": "Arsenal",
        "away_name_raw": "Liverpool",
        "home_name_normalized": "arsenal",
        "away_name_normalized": "liverpool",
        "home_score": 2,
        "away_score": 1,
    }
    row.update(overrides)
    return row


def _fixture(**overrides):
    fixture = {
        "fixture_id": 101,
        "provider": "5DollarFootballAPI",
        "provider_fixture_id": "fixture-101",
        "competition": "England Premier League",
        "home_team_id": 10,
        "home_name": "Arsenal",
        "away_team_id": 20,
        "away_name": "Liverpool",
        "kickoff_at": datetime(2016, 8, 13, 12, 30, tzinfo=timezone.utc),
        "season_key": "2016-2017",
        "status": "FINISHED",
        "home_score": 2,
        "away_score": 1,
        "result_source": "provider",
    }
    fixture.update(overrides)
    return fixture


def test_name_normalization_removes_accents_but_preserves_tokens():
    assert audit.normalize_name("Atlético  Mineiro FC") == "atletico mineiro fc"


def test_season_boundaries_are_competition_specific():
    assert audit.derived_season_key("Brazil Serie A", date(2024, 2, 1)) == "2024"
    assert audit.derived_season_key("England Premier League", date(2024, 5, 19)) == "2023-2024"
    assert audit.derived_season_key("England Premier League", date(2024, 8, 17)) == "2024-2025"


def test_unique_exact_identity_and_score_is_candidate_not_resolved():
    result = audit.reconcile([_row()], [_fixture()])
    row = result["rows"][0]
    assert row["canonical_status"] == "UNIQUE_CANONICAL_CANDIDATE_REVIEW_REQUIRED"
    assert row["canonical_candidates"][0]["fixture_id"] == 101
    assert row["crosswalk_resolution"] == "NOT_RESOLVED_REVIEW_REQUIRED"
    assert result["summary"]["crosswalk_rows_written"] == 0


def test_score_mismatch_and_ambiguous_matches_fail_closed():
    mismatch = audit.reconcile([_row()], [_fixture(home_score=1)])
    assert mismatch["rows"][0]["canonical_status"] == "SCORE_MISMATCH_REVIEW_REQUIRED"

    ambiguous = audit.reconcile([_row()], [_fixture(), _fixture(fixture_id=102)])
    assert ambiguous["rows"][0]["canonical_status"] == "AMBIGUOUS_CANONICAL_CANDIDATES"


def test_duplicate_and_conflicting_duplicate_groups_are_separate():
    first = _row(source_fixture_key="row-1")
    exact = _row(source_fixture_key="row-2")
    conflict = _row(source_fixture_key="row-3", home_score=3)
    result = audit.reconcile([first, exact, conflict], [])
    assert result["summary"]["exact_duplicate_groups"] == 1
    assert result["summary"]["conflicting_duplicate_groups"] == 1
    assert result["summary"]["database_mutations"] == 0


def test_source_rows_preserve_source_line_and_raw_season(tmp_path, monkeypatch):
    spec = FileSpec(
        path="sample.csv", git_blob_sha="d" * 40, expected_bytes=0,
        expected_rows=1, date_min="2016-08-13 11:30:00",
        date_max="2016-08-13 11:30:00", kind="historical_match_csv",
    )
    raw = (
        "season,date,home_name,away_name,homeGoalCount,awayGoalCount\n"
        "2016/2017,2016-08-13 11:30:00,Arsenal,Liverpool,2,1\n"
    ).encode()
    import hashlib
    manifest = {
        "source_repository": audit.REPOSITORY,
        "source_commit_sha": audit.SOURCE_COMMIT,
        "files": [{"path": "sample.csv", "sha256": hashlib.sha256(raw).hexdigest(), "actual_bytes": len(raw)}],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "snapshots" / "sample.csv").write_bytes(raw)
    monkeypatch.setattr(audit, "HISTORICAL_FILES", (spec,))
    monkeypatch.setitem(audit.COMPETITIONS, "sample.csv", "England Premier League")
    rows, files = audit.source_rows(tmp_path)
    assert rows[0]["source_line_number"] == 2
    assert rows[0]["source_season_raw"] == "2016/2017"
    assert rows[0]["derived_season_key"] == "2016-2017"
    assert rows[0]["source_fixture_key"].startswith("aimidas:")
    assert files["sample.csv"]["rows"] == 1
