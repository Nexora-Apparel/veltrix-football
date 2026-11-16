from pathlib import Path

from scripts.phase5_prediction_feature_link_migration import (
    EXPECTED_DATABASE,
    EXPECTED_HOST,
    EXPECTED_ROLE,
    PENDING,
)
from scripts.db_migrate import MIGRATION_DIR, load_manifest


def test_prediction_feature_link_migration_is_last_and_additive():
    manifest = load_manifest()
    versions = [item[0] for item in manifest]
    assert versions[-1] == "0012_prediction_feature_snapshot_links"
    assert PENDING == ["0012_prediction_feature_snapshot_links"]


def test_prediction_feature_link_migration_has_composite_prediction_and_pit_evidence_guards():
    sql = (MIGRATION_DIR / "0012_prediction_feature_snapshot_links.sql").read_text()
    for token in (
        "CREATE TABLE prediction_feature_snapshot_links",
        "FOREIGN KEY (ledger_id, prediction_sequence)",
        "REFERENCES paper_ledger_events(ledger_id, sequence)",
        "REFERENCES feature_snapshots(feature_snapshot_id)",
        "REFERENCES feature_snapshot_eligibility_events(eligibility_event_id)",
        "forecast_evidence_sha256",
        "model_artifact_sha256",
        "forecast_summary_sha256",
        "feature_admission_summary_sha256",
        "validate_prediction_feature_snapshot_link",
        "V2_PREDICTION_CANONICAL_TEAM_OR_COMPETITION_IDENTITY_MISMATCH",
        "PREDICTION_FEATURE_SNAPSHOT_LINKS_APPEND_ONLY",
        "BEFORE UPDATE OR DELETE",
        "BEFORE TRUNCATE",
    ):
        assert token in sql


def test_migration_script_is_hard_allowlisted_to_staging():
    assert EXPECTED_DATABASE == "veltrix_football_staging"
    assert EXPECTED_ROLE == "neondb_owner"
    assert EXPECTED_HOST == "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
