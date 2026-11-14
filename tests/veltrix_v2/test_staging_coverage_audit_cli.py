from datetime import datetime, timezone
import json
import sys

import pytest

from scripts.phase5_staging_coverage_audit import (
    build_coverage_summary,
    main,
    parse_as_of,
    validate_staging_dsn_target,
)
from veltrix_v2.data.persisted_coverage_adapter import PersistedCoverageInputs

HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"


def test_staging_dsn_guard_accepts_only_exact_direct_staging_target():
    validate_staging_dsn_target(
        f"postgresql://neondb_owner:secret@{HOST}/veltrix_football_staging?sslmode=require"
    )


@pytest.mark.parametrize("dsn", [
    "",
    "postgresql://user:secret@example.com/veltrix_football_staging",
    f"postgresql://user:secret@{HOST}/postgres",
    f"postgresql://user:secret@{HOST}-pooler/veltrix_football_staging",
])
def test_staging_dsn_guard_rejects_non_allowlisted_targets(dsn):
    with pytest.raises((ValueError, PermissionError)):
        validate_staging_dsn_target(dsn)


def test_as_of_requires_timezone_and_normalizes_z():
    assert parse_as_of("2026-11-14T12:00:00Z") == datetime(
        2026, 11, 14, 12, tzinfo=timezone.utc
    )
    with pytest.raises(ValueError, match="AS_OF_TIMESTAMP_MUST_BE_TIMEZONE_AWARE"):
        parse_as_of("2026-11-14T12:00:00")


def test_summary_reports_empty_coverage_without_claiming_certification():
    inputs = PersistedCoverageInputs((), (), 0, 0, ())
    summary = build_coverage_summary(
        inputs, as_of=datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    )
    assert summary["fixture_rows"] == 0
    assert summary["eligible_evidence_rows"] == 0
    assert "does not certify" in summary["certification_notice"]


def test_cli_defaults_to_dry_run_without_reading_database_dsn(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["phase5_staging_coverage_audit.py"])
    monkeypatch.delenv("VELTRIX_STAGING_DATABASE_URL", raising=False)
    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "DRY_RUN"
    assert output["would_connect"] is False
