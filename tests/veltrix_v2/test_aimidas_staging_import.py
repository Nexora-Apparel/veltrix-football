from __future__ import annotations

from pathlib import Path

import pytest

from scripts.veltrix_v2.import_aimidas_staging import (
    APPROVAL_ID, EXPECTED_HOST, MANIFEST_KEY_PREFIX, SOURCE_ID, SOURCE_COMMIT, manifest_key_for,
    canonical_json, preflight, sha256,
)


class NoQueryConnection:
    def cursor(self):
        raise AssertionError("database must not be queried after a failed preflight gate")


def test_canonical_json_is_stable_and_utf8():
    value = {"z": "Série B", "a": [1, True, None]}
    assert canonical_json(value) == canonical_json({"a": [1, True, None], "z": "Série B"})
    assert sha256(canonical_json(value)) == sha256(canonical_json(value))


def test_importer_identity_is_pinned_and_non_keyed():
    assert SOURCE_ID == "ai-midas-github-csv"
    assert APPROVAL_ID == "approval-aimidas-football-data-noncommercial-2026-11-15"
    assert SOURCE_COMMIT == "29baca362a34ce5dcd3924b07ec9c7d5139d83fc"
    assert MANIFEST_KEY_PREFIX == "aimidas-" + SOURCE_COMMIT + "-csv-pack-v1"
    assert manifest_key_for("a" * 64) == MANIFEST_KEY_PREFIX + "-" + "a" * 16


def test_preflight_requires_explicit_enable_before_any_database_access(monkeypatch):
    monkeypatch.delenv("VELTRIX_ENABLE_AIMIDAS_STAGING_IMPORT", raising=False)
    with pytest.raises(RuntimeError, match="AIMIDAS_STAGING_IMPORT_EXPLICIT_ENABLE_REQUIRED"):
        preflight(NoQueryConnection(), "postgresql://neondb_owner@host/db?sslmode=require")


def test_preflight_rejects_wrong_host_before_any_database_access(monkeypatch):
    monkeypatch.setenv("VELTRIX_ENABLE_AIMIDAS_STAGING_IMPORT", "YES")
    with pytest.raises(RuntimeError, match="AIMIDAS_STAGING_HOST_ALLOWLIST_MISMATCH"):
        preflight(NoQueryConnection(), "postgresql://neondb_owner@wrong.example/db?sslmode=require")


def test_preflight_rejects_missing_tls_before_any_database_access(monkeypatch):
    monkeypatch.setenv("VELTRIX_ENABLE_AIMIDAS_STAGING_IMPORT", "YES")
    with pytest.raises(RuntimeError, match="AIMIDAS_STAGING_TLS_REQUIRED"):
        preflight(NoQueryConnection(), f"postgresql://neondb_owner@{EXPECTED_HOST}/db")


def test_preflight_requires_nonempty_database_url_host(monkeypatch):
    monkeypatch.setenv("VELTRIX_ENABLE_AIMIDAS_STAGING_IMPORT", "YES")
    with pytest.raises(RuntimeError, match="AIMIDAS_STAGING_HOST_ALLOWLIST_MISMATCH"):
        preflight(NoQueryConnection(), "postgresql:///db?sslmode=require")
