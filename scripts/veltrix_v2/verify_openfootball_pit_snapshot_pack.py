#!/usr/bin/env python3
"""Independently verify the OpenFootball PIT snapshot pack and archive proofs."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from veltrix_v2.providers.openfootball_archive import parse_archive
from scripts.veltrix_v2.collect_openfootball_pit_snapshots import (
    APPROVAL_ID, SOURCE_SPECS, SPDX_REQUIRED, canonical_hash, aware,
)

def fail(code: str):
    raise ValueError(code)

def safe_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        fail("SNAPSHOT_PATH_MISSING")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        fail("SNAPSHOT_PATH_ESCAPES_PACK")
    return candidate

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
    if manifest.get("schema_version") != "veltrix-openfootball-pit-snapshot-pack-v1":
        fail("PACK_SCHEMA_VERSION_INVALID")
    if manifest.get("rights_approval_id") != APPROVAL_ID or manifest.get("rights_basis") != "OPEN_LICENSE_CC0_1_0":
        fail("PACK_RIGHTS_EVIDENCE_INVALID")
    if manifest.get("raw_redistribution_allowed") is not False:
        fail("PACK_RAW_REDISTRIBUTION_POLICY_INVALID")
    if manifest.get("database_written") is not False or manifest.get("production_written") is not False:
        fail("PACK_WRITE_BOUNDARY_INVALID")

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
    expected, proofs = {}, {}
    rejected = 0
    not_yet_eligible = 0
    for snap in snapshots:
        if not isinstance(snap, dict):
            fail("SNAPSHOT_ROW_INVALID")
        repo, path, comp = snap.get("source_repository"), snap.get("source_path"), snap.get("competition_id")
        if (repo, path, comp) not in allowed:
            raise ValueError(f"SNAPSHOT_SOURCE_OUTSIDE_ALLOWLIST:{repo!r}:{path!r}:{comp!r}")
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
            "rights_approval_id": APPROVAL_ID,
        }
        proof_id = canonical_hash(proof)
        if snap.get("archive_proof_id") != proof_id:
            fail("ARCHIVE_PROOF_ID_MISMATCH")
        raw_path = safe_file(root, snap.get("stored_snapshot_path"))
        if not raw_path.is_file():
            fail("SNAPSHOT_RAW_FILE_MISSING")
        raw = raw_path.read_bytes()
        content_sha = hashlib.sha256(raw).hexdigest()
        if content_sha != snap.get("source_content_sha256"):
            fail("SNAPSHOT_RAW_CONTENT_HASH_MISMATCH")
        try:
            archive = parse_archive(
                raw.decode("utf-8"), competition_id=comp, source_path=path, source_id="openfootball-cc0-archive",
                snapshot_commit_sha=sha, snapshot_available_at=snapshot_at, imported_at=generated,
            )
        except UnicodeDecodeError:
            fail("SNAPSHOT_RAW_FILE_NOT_UTF8")
        if (archive.result_count != snap.get("result_count")
                or archive.fixture_line_count != snap.get("fixture_line_count")
                or archive.rejected_result_count != snap.get("rejected_result_count")
                or archive.not_yet_eligible_count != snap.get("not_yet_eligible_count")):
            fail("SNAPSHOT_PARSE_ACCOUNTING_MISMATCH")
        rejected += archive.rejected_result_count
        not_yet_eligible += archive.not_yet_eligible_count
        proofs[proof_id] = snap
        for item in archive.observations:
            row = {
                "fixture_id": item.fixture_id, "competition_id": item.competition_id,
                "home_team_id": item.home_team_id, "away_team_id": item.away_team_id,
                "kickoff_at": None, "kickoff_date": item.kickoff_date.isoformat(),
                "source_reported_local_time": item.source_reported_local_time,
                "source_timezone": item.source_timezone,
                "home_goals": item.home_goals, "away_goals": item.away_goals,
                "provider": item.provider, "source_id": item.source_id,
                "availability_basis": item.availability_basis,
                "available_at": item.available_at.isoformat(), "recorded_at": item.recorded_at.isoformat(),
                "point_in_time_certifiable": item.point_in_time_certifiable,
                "payload_sha256": item.payload_sha256, "source_repository": repo,
                "source_path": path, "source_commit_sha": sha,
                "source_commit_timestamp": snapshot_at.isoformat(),
                "source_content_sha256": content_sha, "source_license_spdx": SPDX_REQUIRED,
                "rights_approval_id": APPROVAL_ID, "archive_proof_id": proof_id,
                "source_published_at": None,
                "source_timestamp_basis": "unverified_repository_commit_timestamp",
                "retrieved_at": generated.isoformat(), "temporal_semantics": "state_as_of_cutoff",
                "revision_history_complete": True,
                "source_revision_order": snap.get("source_revision_order"),
            }
            key = (item.fixture_id, item.payload_sha256)
            prior = expected.get(key)
            if prior is None or (row["available_at"], row["source_commit_sha"]) < (
                prior["available_at"], prior["source_commit_sha"]
            ):
                expected[key] = row

    actual = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("archive_proof_id") not in proofs:
            fail("OBSERVATION_ROW_OR_PROOF_INVALID")
        key = (row.get("fixture_id"), row.get("payload_sha256"))
        if key in actual:
            fail("OBSERVATION_VERSION_DUPLICATE")
        actual[key] = row
    if set(actual) != set(expected):
        fail("OBSERVATION_VERSION_SET_MISMATCH")
    for key, row in expected.items():
        got = actual[key]
        if got != row:
            fail("OBSERVATION_ROW_DOES_NOT_MATCH_SOURCE_SNAPSHOT")
        match_date = datetime.fromisoformat(got["kickoff_date"]).date()
        safe_boundary = datetime.combine(match_date + timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)
        if aware(got["source_commit_timestamp"]) < safe_boundary:
            fail("DATE_ONLY_RESULT_PRECEDES_SAFE_BOUNDARY")
        if got["kickoff_at"] is not None or got["recorded_at"] != generated.isoformat():
            fail("KICKOFF_OR_RETRIEVAL_TIMESTAMP_INVALID")

    reports = manifest.get("source_reports", [])
    if not isinstance(reports, list) or any(not isinstance(r, dict) for r in reports):
        fail("SOURCE_REPORTS_INVALID")
    result = {
        "status": "PASS",
        "source_capture_complete": manifest.get("all_sources_succeeded") is True,
        "source_report_count": len(reports), "snapshot_count": len(snapshots),
        "observation_version_count": len(rows),
        "unique_fixture_count": len({r["fixture_id"] for r in rows}),
        "rejected_result_count": rejected, "not_yet_eligible_count": not_yet_eligible,
        "archive_proof_count": len(proofs),
        "all_commit_histories_complete": all(r.get("commit_history_complete") is True for r in reports),
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
