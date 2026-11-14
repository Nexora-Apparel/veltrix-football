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


def test_coverage_summary_includes_verified_crosswalk_registry():
    from hashlib import sha256
    import json
    from veltrix_v2.data.crosswalk_bootstrap import build_fivedollar_crosswalk_registry

    def crosswalk_row(fid, home, away, canonical_fixture, canonical_home, canonical_away, obs):
        payload = {
            "id": fid,
            "league": {"id": 311},
            "teams": {"home": {"id": home}, "away": {"id": away}},
        }
        return {
            "provider": "5DollarFootballAPI", "source_id": "5dollarfootballapi",
            "canonical_fixture_id": canonical_fixture,
            "canonical_competition_id": "comp-1",
            "canonical_home_team_id": canonical_home,
            "canonical_away_team_id": canonical_away,
            "payload": payload,
            "payload_sha256": sha256(f"raw-{obs}".encode()).hexdigest(),
            "source_observation_id": obs,
        }

    registry = build_fivedollar_crosswalk_registry(
        [crosswalk_row(100, 11, 22, "fx-1", "team-a", "team-b", 1),
         crosswalk_row(101, 22, 33, "fx-2", "team-b", "team-c", 2)],
        verified_at=datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    )
    summary = build_coverage_summary(
        PersistedCoverageInputs((), (), 0, 0, ()),
        as_of=datetime(2026, 11, 14, 12, tzinfo=timezone.utc),
        crosswalk_registry=registry,
    )
    assert summary["crosswalk_registry"]["fixture_crosswalks"] == 2
    assert summary["crosswalk_registry"]["team_crosswalks"] == 3
    assert summary["crosswalk_registry"]["competition_crosswalks"] == 1
