import json
import pytest
from datetime import datetime, timezone

from scripts.veltrix_v2.collect_openfootball_pit_snapshots import collect_snapshots
from scripts.veltrix_v2.verify_openfootball_pit_snapshot_pack import verify_pack

SHA1 = "a" * 40
IMPORTED = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
SOURCE = (
    "= Premier League 2024/2025\n"
    "▪ Matchday 1\n"
    "  Fri Jan 03 2025\n"
    "           Arsenal FC              v Chelsea FC           2-1\n"
)
SOURCES = (("openfootball/england", "2024-25/1-premierleague.txt", "OPENFOOTBALL_EPL_2024_25"),)

def make_transport(commits, raw_by_sha=None, license_id="CC0-1.0"):
    raw_by_sha = raw_by_sha or {SHA1: SOURCE.encode()}
    def read_json(url):
        if url.endswith("/repos/openfootball/england"):
            return {"html_url": "https://github.com/openfootball/england",
                    "license": {"spdx_id": license_id, "url": "https://api.github.com/licenses/cc0-1.0"}}
        return commits
    def read_bytes(url):
        for sha, raw in raw_by_sha.items():
            if f"/{sha}/" in url:
                return raw
        raise AssertionError(url)
    return read_json, read_bytes

def make_pack(tmp_path):
    commits = [{"sha": SHA1, "commit": {"committer": {"date": "2025-01-06T10:00:00Z"}}}]
    read_json, read_bytes = make_transport(commits)
    return collect_snapshots(
        output_dir=tmp_path, imported_at=IMPORTED, sources=SOURCES,
        read_json=read_json, read_bytes=read_bytes,
    )

def test_pack_records_immutable_snapshot_and_actual_retrieval_time(tmp_path):
    commits = [{"sha": SHA1, "commit": {"committer": {"date": "2025-01-06T10:00:00Z"}}}]
    read_json, read_bytes = make_transport(commits)
    manifest = collect_snapshots(
        output_dir=tmp_path, imported_at=IMPORTED, sources=SOURCES,
        read_json=read_json, read_bytes=read_bytes,
    )
    rows = [json.loads(line) for line in (tmp_path / "observations.jsonl").read_text().splitlines()]
    assert manifest["all_sources_succeeded"] is True
    assert manifest["snapshot_count"] == 1
    assert manifest["observation_version_count"] == 1
    assert rows[0]["source_id"] == "openfootball-cc0-archive"
    assert rows[0]["source_commit_timestamp"] == "2025-01-06T10:00:00+00:00"
    assert rows[0]["recorded_at"] == IMPORTED.isoformat()
    assert rows[0]["available_at"] == IMPORTED.isoformat()
    assert rows[0]["source_published_at"] is None
    assert manifest["snapshots"][0]["source_snapshot_available_at"] == "2025-01-06T10:00:00+00:00"
    assert rows[0]["point_in_time_certifiable"] is False
    assert rows[0]["source_timestamp_basis"] == "unverified_repository_commit_timestamp"
    assert len(rows[0]["archive_proof_id"]) == 64
    assert manifest["database_written"] is False
    assert "not_yet_eligible_count" in manifest["snapshots"][0]
    verified = verify_pack(tmp_path)
    assert verified["status"] == "PASS"
    assert verified["archive_proof_count"] == 1

def test_pack_rejects_source_without_cc0_rights(tmp_path):
    read_json, read_bytes = make_transport([], license_id="MIT")
    manifest = collect_snapshots(
        output_dir=tmp_path, imported_at=IMPORTED, sources=SOURCES,
        read_json=read_json, read_bytes=read_bytes,
    )
    assert manifest["all_sources_succeeded"] is False
    assert manifest["failed_sources"][0]["error_code"] == "SOURCE_LICENSE_NOT_CC0_1_0"
    assert manifest["snapshot_count"] == 0

def test_pack_preserves_score_corrections_as_separate_versions(tmp_path):
    second = "b" * 40
    commits = [
        {"sha": second, "commit": {"committer": {"date": "2025-01-08T10:00:00Z"}}},
        {"sha": SHA1, "commit": {"committer": {"date": "2025-01-06T10:00:00Z"}}},
    ]
    read_json, read_bytes = make_transport(
        commits, {SHA1: SOURCE.encode(), second: SOURCE.replace("2-1", "1-1").encode()}
    )
    manifest = collect_snapshots(
        output_dir=tmp_path, imported_at=IMPORTED, sources=SOURCES,
        read_json=read_json, read_bytes=read_bytes,
    )
    rows = [json.loads(line) for line in (tmp_path / "observations.jsonl").read_text().splitlines()]
    assert manifest["snapshot_count"] == 2
    assert len(rows) == 2
    assert {row["home_goals"] for row in rows} == {1, 2}
    assert verify_pack(tmp_path)["status"] == "PASS"

def test_pack_fails_closed_when_commit_history_limit_is_hit(tmp_path):
    commits = [
        {"sha": f"{i:040x}", "commit": {"committer": {"date": "2025-01-06T10:00:00Z"}}}
        for i in range(2)
    ]
    read_json, read_bytes = make_transport(commits)
    manifest = collect_snapshots(
        output_dir=tmp_path, imported_at=IMPORTED, max_commits_per_source=2,
        sources=SOURCES, read_json=read_json, read_bytes=read_bytes,
    )
    assert manifest["all_sources_succeeded"] is False
    assert manifest["failed_sources"][0]["error_code"] == "COMMIT_HISTORY_LIMIT_REACHED_REFUSING_PARTIAL_HISTORY"

def test_verifier_rejects_tampered_source_snapshot(tmp_path):
    make_pack(tmp_path)
    snapshot = next((tmp_path / "snapshots").glob("*.txt"))
    snapshot.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="SNAPSHOT_RAW_CONTENT_HASH_MISMATCH"):
        verify_pack(tmp_path)


def test_verifier_rejects_tampered_observation_jsonl(tmp_path):
    make_pack(tmp_path)
    path = tmp_path / "observations.jsonl"
    path.write_text(path.read_text().replace('"home_goals":2', '"home_goals":3'))
    with pytest.raises(ValueError, match="OBSERVATIONS_HASH_MISMATCH"):
        verify_pack(tmp_path)
