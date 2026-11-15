#!/usr/bin/env python3
"""Re-verify a pinned AI Midas snapshot pack without network or database access."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

from scripts.veltrix_v2.collect_aimidas_snapshot import (
    APPROVAL_ID, SCHEMA_VERSION, SOURCE_COMMIT, SOURCE_FILES, REPOSITORY, FileSpec,
)


def fail(code: str) -> None:
    raise ValueError(code)


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        fail("PACK_FILE_PATH_MISSING")
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        fail("PACK_FILE_PATH_ESCAPES_ROOT")
    return candidate


def independent_csv_summary(raw: bytes, spec: FileSpec) -> dict:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        fail("CSV_NOT_UTF8")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = reader.fieldnames
    if not fields:
        fail("CSV_HEADER_MISSING")
    rows = [row for row in reader if any((value or "").strip() for value in row.values())]
    date_field = "Date" if "Date" in fields else "date" if "date" in fields else None
    if date_field is None:
        fail("CSV_DATE_FIELD_MISSING")
    dates = sorted((row.get(date_field) or "").strip() for row in rows if (row.get(date_field) or "").strip())
    if not dates:
        fail("CSV_DATE_VALUES_MISSING")
    odds_fields = ("avg_odds_ft_1", "avg_odds_ft_x", "avg_odds_ft_2")
    valid_odds = 0
    if set(odds_fields).issubset(fields):
        for row in rows:
            try:
                prices = tuple(float(row[name]) for name in odds_fields)
            except (TypeError, ValueError):
                continue
            if all(price > 1.0 and price < 1000.0 for price in prices):
                valid_odds += 1
    matches = {(row.get("Match") or "").strip() for row in rows} - {""}
    teams = {(row.get("Team") or "").strip() for row in rows} - {""}
    return {
        "path": spec.path,
        "kind": spec.kind,
        "row_count": len(rows),
        "column_count": len(fields),
        "date_field": date_field,
        "date_min": dates[0],
        "date_max": dates[-1],
        "has_average_1x2_fields": set(odds_fields).issubset(fields),
        "valid_average_1x2_rows": valid_odds,
        "distinct_match_labels": len(matches),
        "distinct_teams": len(teams),
        "has_prematch_named_fields": any(
            "prematch" in name.lower() or "pre_match" in name.lower() for name in fields
        ),
        "has_timezone_or_source_publication_timestamp": False,
        "point_in_time_certifiable": False,
    }


def verify_pack(input_dir: Path, *, specs: tuple[FileSpec, ...] = SOURCE_FILES) -> dict:
    root = input_dir.resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        fail("PACK_MANIFEST_MISSING")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("PACK_MANIFEST_INVALID")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        fail("PACK_SCHEMA_VERSION_INVALID")
    if manifest.get("source_repository") != REPOSITORY or manifest.get("source_commit_sha") != SOURCE_COMMIT:
        fail("PACK_SOURCE_PIN_INVALID")
    if manifest.get("rights_approval_id") != APPROVAL_ID:
        fail("PACK_RIGHTS_APPROVAL_INVALID")
    try:
        generated = datetime.fromisoformat(manifest.get("generated_at", "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        fail("PACK_GENERATED_AT_INVALID")
    if generated.tzinfo is None or generated.utcoffset() is None:
        fail("PACK_GENERATED_AT_NOT_AWARE")
    for field in ("database_written", "production_written", "model_admitted", "predictions_changed", "point_in_time_certifiable", "raw_redistribution_allowed"):
        if manifest.get(field) is not False:
            fail(f"PACK_BOUNDARY_INVALID:{field}")

    records = manifest.get("files")
    if not isinstance(records, list) or len(records) != len(specs):
        fail("PACK_FILE_COUNT_INVALID")
    by_path = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            fail("PACK_FILE_RECORD_INVALID")
        if record["path"] in by_path:
            fail("PACK_DUPLICATE_FILE_RECORD")
        by_path[record["path"]] = record
    if set(by_path) != {spec.path for spec in specs}:
        fail("PACK_FILE_ALLOWLIST_MISMATCH")

    total_bytes = 0
    verified = []
    for spec in specs:
        record = by_path[spec.path]
        expected_stored = (Path("snapshots") / spec.path).as_posix()
        if record.get("stored_path") != expected_stored:
            fail(f"PACK_STORED_PATH_INVALID:{spec.path}")
        raw_path = safe_path(root, expected_stored)
        if not raw_path.is_file():
            fail(f"PACK_RAW_FILE_MISSING:{spec.path}")
        raw = raw_path.read_bytes()
        total_bytes += len(raw)
        if len(raw) != spec.expected_bytes or record.get("actual_bytes") != len(raw):
            fail(f"PACK_BYTE_SIZE_MISMATCH:{spec.path}")
        git_sha = hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()
        if git_sha != spec.git_blob_sha or record.get("git_blob_sha1") != git_sha:
            fail(f"PACK_GIT_BLOB_MISMATCH:{spec.path}")
        sha256 = hashlib.sha256(raw).hexdigest()
        if record.get("sha256") != sha256:
            fail(f"PACK_SHA256_MISMATCH:{spec.path}")
        summary = independent_csv_summary(raw, spec)
        for key, value in summary.items():
            if record.get(key) != value:
                fail(f"PACK_CSV_SUMMARY_MISMATCH:{spec.path}:{key}")
        if summary["row_count"] != spec.expected_rows:
            fail(f"PACK_EXPECTED_ROW_COUNT_MISMATCH:{spec.path}")
        if summary["date_min"] != spec.date_min or summary["date_max"] != spec.date_max:
            fail(f"PACK_EXPECTED_DATE_RANGE_MISMATCH:{spec.path}")
        if summary["valid_average_1x2_rows"] != spec.expected_avg_1x2:
            fail(f"PACK_EXPECTED_ODDS_COUNT_MISMATCH:{spec.path}")
        if spec.expected_distinct_matches and summary["distinct_match_labels"] != spec.expected_distinct_matches:
            fail(f"PACK_EXPECTED_MATCH_COUNT_MISMATCH:{spec.path}")
        if spec.expected_distinct_teams and summary["distinct_teams"] != spec.expected_distinct_teams:
            fail(f"PACK_EXPECTED_TEAM_COUNT_MISMATCH:{spec.path}")
        verified.append(spec.path)

    if manifest.get("files_requested") != len(specs) or manifest.get("files_captured") != len(specs):
        fail("PACK_CAPTURE_COUNT_INVALID")
    if manifest.get("total_bytes") != total_bytes:
        fail("PACK_TOTAL_BYTES_MISMATCH")
    result = {
        "status": "PASS",
        "source_repository": REPOSITORY,
        "source_commit_sha": SOURCE_COMMIT,
        "rights_approval_id": APPROVAL_ID,
        "files_verified": len(verified),
        "total_bytes": total_bytes,
        "all_files_pinned": True,
        "all_csv_audits_reproduced": True,
        "point_in_time_certifiable": False,
        "database_written": False,
        "production_written": False,
        "model_admitted": False,
        "predictions_changed": False,
    }
    (root / "verification.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(verify_pack(Path(args.input_dir)), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
