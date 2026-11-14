from pathlib import Path

import pytest

import scripts.phase5_staging_paper_ledger_migration as migration


DSN = "postgresql://neondb_owner:secret@ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech/veltrix_football_staging"


def _manifest_versions():
    return [entry[0] for entry in migration.load_manifest()]


def test_migration_script_defaults_to_dry_run_with_only_0005_pending(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DSN)
    monkeypatch.setattr(migration, "validate_staging_dsn_target", lambda value: None)
    monkeypatch.setattr(migration, "_baseline", lambda value: {
        "fixtures": 2496, "source_observations": 2496, "provider_responses": 28,
        "capture_manifests": 0, "capture_manifest_events": 0,
        "provider_capture_requests": 0,
    })
    versions = _manifest_versions()
    monkeypatch.setattr(migration, "migrate", lambda value, dry_run=False: {
        "database": "veltrix_football_staging",
        "user": "neondb_owner",
        "applied": versions[:-1],
        "pending": [versions[-1]],
    })
    result = migration.run(apply=False)
    assert result["status"] == "DRY_RUN_READY"
    assert result["pending"] == ["0005_prospective_paper_ledger"]
    assert result["writes_performed"] is False


def test_apply_requires_explicit_internal_guard(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DSN)
    monkeypatch.delenv("VELTRIX_ENABLE_PHASE5_PAPER_LEDGER_MIGRATION", raising=False)
    monkeypatch.setattr(migration, "validate_staging_dsn_target", lambda value: None)
    monkeypatch.setattr(migration, "_baseline", lambda value: {})
    versions = _manifest_versions()
    calls = []

    def fake_migrate(value, dry_run=False):
        calls.append(dry_run)
        return {
            "database": "veltrix_football_staging",
            "user": "neondb_owner",
            "applied": versions[:-1],
            "pending": [versions[-1]],
        }

    monkeypatch.setattr(migration, "migrate", fake_migrate)
    with pytest.raises(PermissionError, match="PAPER_LEDGER_MIGRATION_EXPLICIT_GUARD_REQUIRED"):
        migration.run(apply=True)
    assert calls == [True]


def test_wrong_host_is_rejected_before_any_migration(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://neondb_owner:secret@wrong.example/veltrix_football_staging",
    )
    monkeypatch.setattr(migration, "validate_staging_dsn_target", lambda value: None)
    with pytest.raises(PermissionError, match="PAPER_LEDGER_MIGRATION_HOST_NOT_ALLOWLISTED"):
        migration.run(apply=False)
