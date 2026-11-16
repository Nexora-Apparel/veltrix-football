from datetime import datetime, timezone
import json

import pytest

from scripts.veltrix_v2.collect_aimidas_snapshot import (
    FileSpec, collect_pack, git_blob_sha1, parse_and_audit,
)
from scripts.veltrix_v2.verify_aimidas_snapshot import verify_pack


RAW = (
    "date,avg_odds_ft_1,avg_odds_ft_x,avg_odds_ft_2,Team,Match\n"
    '2026-01-01,2.10,3.20,3.80,Home,"Home 2-0 Away"\n'
    '2026-01-01,3.80,3.20,2.10,Away,"Home 2-0 Away"\n'
).encode("utf-8")


def spec(raw=RAW):
    return FileSpec(
        path="test/mini.csv",
        git_blob_sha=git_blob_sha1(raw),
        expected_bytes=len(raw),
        expected_rows=2,
        date_min="2026-01-01",
        date_max="2026-01-01",
        kind="test_match_csv",
        expected_avg_1x2=2,
        expected_distinct_matches=1,
        expected_distinct_teams=2,
    )


def test_parser_handles_quoted_match_labels_and_odds():
    result = parse_and_audit(RAW, spec())
    assert result["row_count"] == 2
    assert result["column_count"] == 6
    assert result["valid_average_1x2_rows"] == 2
    assert result["distinct_match_labels"] == 1
    assert result["distinct_teams"] == 2
    assert result["point_in_time_certifiable"] is False


def test_collect_and_independently_verify_pinned_artifact(tmp_path):
    item = spec()
    manifest = collect_pack(
        tmp_path,
        fetcher=lambda path: RAW,
        generated_at=datetime(2026, 11, 15, 12, tzinfo=timezone.utc),
        specs=(item,),
    )
    assert manifest["files_captured"] == 1
    assert manifest["database_written"] is False
    assert manifest["production_written"] is False
    assert (tmp_path / "snapshots/test/mini.csv").read_bytes() == RAW
    result = verify_pack(tmp_path, specs=(item,))
    assert result["status"] == "PASS"
    assert result["files_verified"] == 1
    assert result["point_in_time_certifiable"] is False
    assert (tmp_path / "verification.json").is_file()


def test_collector_rejects_wrong_source_blob(tmp_path):
    wrong = FileSpec(
        path="test/mini.csv",
        git_blob_sha="0" * 40,
        expected_bytes=len(RAW),
        expected_rows=2,
        date_min="2026-01-01",
        date_max="2026-01-01",
        kind="test_match_csv",
        expected_avg_1x2=2,
        expected_distinct_matches=1,
        expected_distinct_teams=2,
    )
    with pytest.raises(RuntimeError, match="SOURCE_GIT_BLOB_SHA_MISMATCH"):
        collect_pack(tmp_path, fetcher=lambda path: RAW, specs=(wrong,))


def test_verifier_rejects_tampered_raw_file(tmp_path):
    item = spec()
    collect_pack(tmp_path, fetcher=lambda path: RAW, specs=(item,))
    (tmp_path / "snapshots/test/mini.csv").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="PACK_BYTE_SIZE_MISMATCH|PACK_GIT_BLOB_MISMATCH"):
        verify_pack(tmp_path, specs=(item,))


def test_verifier_rejects_manifest_claiming_database_write(tmp_path):
    item = spec()
    collect_pack(tmp_path, fetcher=lambda path: RAW, specs=(item,))
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["database_written"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="PACK_BOUNDARY_INVALID:database_written"):
        verify_pack(tmp_path, specs=(item,))


def test_collector_rejects_duplicate_allowlist_paths(tmp_path):
    item = spec()
    with pytest.raises(ValueError, match="SOURCE_FILE_ALLOWLIST_DUPLICATE"):
        collect_pack(tmp_path, fetcher=lambda path: RAW, specs=(item, item))


def test_collector_requires_timezone_aware_manifest_time(tmp_path):
    item = spec()
    with pytest.raises(ValueError, match="GENERATED_AT_MUST_BE_TIMEZONE_AWARE"):
        collect_pack(
            tmp_path,
            fetcher=lambda path: RAW,
            generated_at=datetime(2026, 11, 15, 12),
            specs=(item,),
        )
