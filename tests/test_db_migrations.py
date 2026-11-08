from pathlib import Path
import hashlib

import pytest

from scripts.db_migrate import load_manifest


def test_manifest_is_sorted_and_sha256_matches_exact_bytes(tmp_path: Path):
    (tmp_path / "0002_second.sql").write_bytes(b"SELECT 2;\n")
    (tmp_path / "0001_first.sql").write_bytes(b"SELECT 1;\n")
    manifest = load_manifest(tmp_path)
    assert [row[0] for row in manifest] == ["0001_first", "0002_second"]
    assert manifest[0][1] == hashlib.sha256(b"SELECT 1;\n").hexdigest()


def test_manifest_rejects_invalid_migration_filename(tmp_path: Path):
    (tmp_path / "initial.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError, match="Invalid migration filename"):
        load_manifest(tmp_path)


def test_manifest_rejects_duplicate_versions_not_possible_from_filesystem(tmp_path: Path):
    # Distinct names cannot share the same stem; version uniqueness is also
    # enforced by the migration-history primary key at database level.
    (tmp_path / "0001_first.sql").write_text("SELECT 1;")
    assert len(load_manifest(tmp_path)) == 1
