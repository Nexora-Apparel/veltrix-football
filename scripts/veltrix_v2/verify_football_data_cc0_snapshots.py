#!/usr/bin/env python3
"""Independently verify the FootballData CC0 Brazil archive pack."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.veltrix_v2.collect_football_data_cc0_snapshots import (
    APPROVAL_ID, SOURCE_SPECS, SPDX_REQUIRED, canonical_hash, aware,
)
from veltrix_v2.providers.football_data_cc0.parser import parse_json_archive

def fail(code: str):
    raise ValueError(code)

def verify_pack(input_dir: Path) -> dict:
    root = input_dir.resolve()
    mp, op = root / "manifest.json", root / "observations.jsonl"
    if not mp.is_file() or not op.is_file():
        fail("PACK_REQUIRED_FILE_MISSING")
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("PACK_MANIFEST_INVALID")
    generated = aware(manifest.get("generated_at", ""))
    if manifest.get("schema_version") != "veltrix-footballdata-cc0-snapshot-pack-v1":
        fail("PACK_SCHEMA_VERSION_INVALID")
    if manifest.get("rights_approval_id") != APPROVAL_ID or manifest.get("rights_basis") != "OPEN_LICENSE_CC0_1_0":
        fail("PACK_RIGHTS_EVIDENCE_INVALID")
    raw_rows = op.read_bytes()
    if hashlib.sha256(raw_rows).hexdigest() != manifest.get("observations_sha256"):
        fail("OBSERVATIONS_HASH_MISMATCH")
    try:
        rows = [json.loads(line) for line in raw_rows.decode("utf-8").splitlines() if line]
    except (UnicodeDecodeError, json.JSONDecodeError):
        fail("OBSERVATIONS_JSONL_INVALID")
    if len(rows) != manifest.get("observation_version_count"):
        fail("OBSERVATION_COUNT_MISMATCH")
    snapshots = manifest.get("snapshots")
    if not isinstance(snapshots, list) or len(snapshots) != manifest.get("snapshot_count"):
        fail("SNAPSHOT_COUNT_MISMATCH")
    allowed = set(SOURCE_SPECS)
    expected, proof_ids = {}, set()
    rejected = not_yet = normalizations = 0
    for snap in snapshots:
        repo, path, comp = snap.get("source_repository"), snap.get("source_path"), snap.get("competition_id")
        if (repo, path, comp) not in allowed:
            fail("SNAPSHOT_SOURCE_OUTSIDE_ALLOWLIST")
        if snap.get("source_license_spdx") != SPDX_REQUIRED or snap.get("rights_approval_id") != APPROVAL_ID:
            fail("SNAPSHOT_RIGHTS_SCOPE_INVALID")
        if snap.get("revision_history_complete") is not True:
            fail("SNAPSHOT_REVISION_HISTORY_INCOMPLETE")
        sha = snap.get("source_commit_sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            fail("SNAPSHOT_COMMIT_SHA_INVALID")
        snapshot_at = aware(snap.get("source_snapshot_available_at", ""))
        if snapshot_at > generated:
            fail("SNAPSHOT_AFTER_COLLECTION_TIME")
        proof = {
            "source_repository": repo, "source_path": path, "competition_id": comp,
            "source_commit_sha": sha, "source_snapshot_available_at": snapshot_at.isoformat(),
            "source_content_sha256": snap.get("source_content_sha256"),
            "source_license_spdx": SPDX_REQUIRED, "source_license_url": snap.get("source_license_url"),
            "rights_approval_id": APPROVAL_ID, "source_format": "football_data_json",
        }
        proof_id = canonical_hash(proof)
        if snap.get("archive_proof_id") != proof_id:
            fail("ARCHIVE_PROOF_ID_MISMATCH")
        rel = snap.get("stored_snapshot_path")
        if not isinstance(rel, str) or Path(rel).is_absolute() or ".." in Path(rel).parts:
            fail("SNAPSHOT_PATH_INVALID")
        raw_path = (root / rel).resolve()
        if not raw_path.is_relative_to(root) or not raw_path.is_file():
            fail("SNAPSHOT_RAW_FILE_MISSING_OR_UNSAFE")
        raw = raw_path.read_bytes()
        content_sha = hashlib.sha256(raw).hexdigest()
        if content_sha != snap.get("source_content_sha256"):
            fail("SNAPSHOT_RAW_CONTENT_HASH_MISMATCH")
        archive = parse_json_archive(
            raw.decode("utf-8"), competition_id=comp, source_path=path,
            snapshot_commit_sha=sha, snapshot_available_at=snapshot_at, imported_at=generated,
        )
        if (archive.fixture_line_count != snap.get("fixture_line_count")
                or archive.result_count != snap.get("result_count")
                or archive.rejected_result_count != snap.get("rejected_result_count")
                or archive.not_yet_eligible_count != snap.get("not_yet_eligible_count")):
            fail("SNAPSHOT_PARSE_ACCOUNTING_MISMATCH")
        rejected += archive.rejected_result_count
        not_yet += archive.not_yet_eligible_count
        normalizations += len(archive.team_name_normalizations)
        proof_ids.add(proof_id)
        for item in archive.observations:
            row = {
                "fixture_id": item.fixture_id, "competition_id": item.competition_id,
                "home_team_id": item.home_team_id, "away_team_id": item.away_team_id,
                "home_team_name": item.home_team_name, "away_team_name": item.away_team_name,
                "kickoff_at": None, "kickoff_date": item.kickoff_date.isoformat(),
                "source_reported_local_time": item.source_reported_local_time,
                "source_timezone": item.source_timezone, "home_goals": item.home_goals,
                "away_goals": item.away_goals, "round_name": item.round_name,
                "provider": item.provider, "source_id": item.source_id,
                "availability_basis": item.availability_basis,
                "available_at": item.available_at.isoformat(), "recorded_at": item.recorded_at.isoformat(),
                "point_in_time_certifiable": item.point_in_time_certifiable,
                "payload_sha256": item.payload_sha256, "source_row_index": item.source_row_index,
                "team_name_normalizations": list(item.team_name_normalizations),
                "source_repository": repo, "source_path": path, "source_commit_sha": sha,
                "source_commit_timestamp": snapshot_at.isoformat(), "source_content_sha256": content_sha,
                "source_license_spdx": SPDX_REQUIRED, "rights_approval_id": APPROVAL_ID,
                "archive_proof_id": proof_id, "source_published_at": None,
                "source_timestamp_basis": "unverified_repository_commit_timestamp",
                "retrieved_at": generated.isoformat(), "temporal_semantics": "state_as_of_cutoff",
                "revision_history_complete": True, "source_revision_order": snap.get("source_revision_order"),
            }
            key = (item.fixture_id, item.payload_sha256)
            previous = expected.get(key)
            if previous is None or (row["available_at"], row["source_commit_sha"]) < (
                previous["available_at"], previous["source_commit_sha"]
            ):
                expected[key] = row
    actual = {}
    for row in rows:
        key = (row.get("fixture_id"), row.get("payload_sha256"))
        if row.get("archive_proof_id") not in proof_ids or key in actual:
            fail("OBSERVATION_PROOF_OR_DUPLICATE_INVALID")
        actual[key] = row
    if set(actual) != set(expected):
        fail("OBSERVATION_VERSION_SET_MISMATCH")
    for key, expected_row in expected.items():
        row = actual[key]
        if row != expected_row:
            fail("OBSERVATION_ROW_DOES_NOT_MATCH_SOURCE")
        if row["kickoff_at"] is not None or row["source_timezone"] != "UNKNOWN":
            fail("UNKNOWN_SOURCE_TIMEZONE_WAS_INFERRED")
        day = datetime.fromisoformat(row["kickoff_date"]).date()
        boundary = datetime.combine(day + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)
        if aware(row["source_commit_timestamp"]) < boundary:
            fail("DATE_ONLY_RESULT_PRECEDES_SAFE_BOUNDARY")
    reports = manifest.get("source_reports", [])
    result = {
        "status": "PASS", "source_capture_complete": manifest.get("all_sources_succeeded") is True,
        "source_report_count": len(reports), "snapshot_count": len(snapshots),
        "observation_version_count": len(rows), "unique_fixture_count": len({r["fixture_id"] for r in rows}),
        "rejected_result_count": rejected, "not_yet_eligible_count": not_yet,
        "team_name_normalization_count": normalizations, "archive_proof_count": len(proof_ids),
        "observations_sha256": manifest["observations_sha256"],
        "database_written": False, "production_written": False,
    }
    (root / "verification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_pack(Path(args.input_dir)), sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
