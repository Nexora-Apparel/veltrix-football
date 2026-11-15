import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from veltrix_v2.providers.football_data_cc0.parser import parse_json_archive
from scripts.veltrix_v2.collect_football_data_cc0_snapshots import (
    APPROVAL_ID, SOURCE_SPECS, collect,
)
from scripts.veltrix_v2.verify_football_data_cc0_snapshots import verify_pack

SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
IMPORTED = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
ROWS = [
    {"match_date": "01.01.2025 19:00", "home": "Club A", "away": "Club B", "goals_home": 2, "goals_away": 1, "round": "1"},
    {"match_date": "02.01.2025 20:00", "home": "Club A\n2", "away": "Club C", "goals_home": 1, "goals_away": 0, "round": "1"},
    {"match_date": "03.01.2025 18:00", "home": "Club B", "away": "Club A", "goals_home": 0, "goals_away": 0, "round": "1"},
]
RAW_A = json.dumps(ROWS, ensure_ascii=False).encode()
ROWS_B = [dict(row) for row in ROWS]
ROWS_B[0]["goals_home"] = 3
RAW_B = json.dumps(ROWS_B, ensure_ascii=False).encode()
RAW_C = json.dumps(ROWS, ensure_ascii=False).encode()

def test_parser_preserves_unknown_timezone_and_audits_team_name_cleanup():
    parsed = parse_json_archive(
        RAW_A.decode(), competition_id="FOOTBALLDATA_BR_SERIE_B_2025",
        source_path=SOURCE_SPECS[0][1], snapshot_commit_sha=SHA_A,
        snapshot_available_at=datetime(2025, 1, 10, tzinfo=timezone.utc),
        imported_at=IMPORTED,
    )
    assert parsed.result_count == 3
    assert parsed.rejected_result_count == 0
    assert parsed.not_yet_eligible_count == 0
    row = parsed.observations[1]
    assert row.home_team_name == "Club A"
    assert row.source_reported_local_time == "20:00"
    assert row.source_timezone == "UNKNOWN"
    assert row.team_name_normalizations[0]["reason"] == "TRAILING_LINE_NUMBER_ARTIFACT_BASE_VERIFIED_IN_SAME_SNAPSHOT"

def test_parser_rejects_unverified_team_name_suffix_and_respects_two_day_boundary():
    raw = json.dumps([
        {"match_date": "01.01.2025 19:00", "home": "Unknown\n2", "away": "Club B", "goals_home": 1, "goals_away": 0},
        {"match_date": "10.01.2025 19:00", "home": "Club A", "away": "Club B", "goals_home": 1, "goals_away": 0},
    ])
    parsed = parse_json_archive(
        raw, competition_id="FOOTBALLDATA_BR_SERIE_B_2025", source_path=SOURCE_SPECS[0][1],
        snapshot_commit_sha=SHA_A, snapshot_available_at=datetime(2025, 1, 11, tzinfo=timezone.utc),
        imported_at=IMPORTED,
    )
    assert parsed.rejected_result_count == 1
    assert parsed.not_yet_eligible_count == 1
    assert parsed.result_count == 0

def test_collector_preserves_revisions_and_verifier_checks_snapshot_hashes(tmp_path, monkeypatch):
    import scripts.veltrix_v2.collect_football_data_cc0_snapshots as collector
    commits_by_path = {
        SOURCE_SPECS[0][1]: [
            {"sha": SHA_A, "commit": {"committer": {"date": "2025-01-10T00:00:00Z"}}},
            {"sha": SHA_B, "commit": {"committer": {"date": "2025-01-12T00:00:00Z"}}},
        ],
        SOURCE_SPECS[1][1]: [
            {"sha": SHA_C, "commit": {"committer": {"date": "2025-01-10T00:00:00Z"}}},
        ],
    }
    raw_by_sha = {SHA_A: RAW_A, SHA_B: RAW_B, SHA_C: RAW_C}
    monkeypatch.setattr(collector, "read_json_default", lambda *args: {"license": {"spdx_id": "CC0-1.0", "url": "https://license.example/cc0"}})
    monkeypatch.setattr(collector, "list_path_commits", lambda repo, path, **kwargs: (commits_by_path[path], True))
    monkeypatch.setattr(collector, "http_get", lambda url, **kwargs: (next(raw for sha, raw in raw_by_sha.items() if sha in url), {}))
    manifest = collect(output_dir=tmp_path, imported_at=IMPORTED, max_requests=20)
    assert manifest["all_sources_succeeded"] is True
    assert manifest["snapshot_count"] == 3
    assert manifest["observation_version_count"] == 7
    rows = [json.loads(line) for line in (tmp_path / "observations.jsonl").read_text().splitlines()]
    assert any(row["source_timezone"] == "UNKNOWN" and row["kickoff_at"] is None for row in rows)
    assert any(row["home_goals"] == 2 for row in rows)
    assert any(row["home_goals"] == 3 for row in rows)
    assert all(row["point_in_time_certifiable"] is False for row in rows)
    verified = verify_pack(tmp_path)
    assert verified["status"] == "PASS"
    assert verified["team_name_normalization_count"] >= 1
    raw_snapshot = next((tmp_path / "snapshots").glob("*.json"))
    raw_snapshot.write_text("tampered")
    with pytest.raises(ValueError, match="SNAPSHOT_RAW_CONTENT_HASH_MISMATCH"):
        verify_pack(tmp_path)
