from pathlib import Path
import hashlib

from scripts.db_migrate import load_manifest


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "db" / "migrations"


def test_phase4_migration_is_in_manifest_after_phase3():
    manifest = load_manifest(MIGRATIONS)
    versions = [row[0] for row in manifest]
    assert versions[-1] == "0004_point_in_time_feature_capture"
    assert versions == sorted(versions)
    raw = (MIGRATIONS / "0004_point_in_time_feature_capture.sql").read_bytes()
    assert manifest[-1][1] == hashlib.sha256(raw).hexdigest()


def test_phase4_migration_is_additive_and_does_not_backfill_history():
    sql = (MIGRATIONS / "0004_point_in_time_feature_capture.sql").read_text(encoding="utf-8").upper()
    assert "DROP TABLE" not in sql
    assert "DROP COLUMN" not in sql
    assert "TRUNCATE" not in sql
    assert "DELETE FROM" not in sql
    assert "UPDATE SOURCE_OBSERVATIONS" not in sql
    assert "SOURCE_PUBLISHED_AT TIMESTAMPTZ" in sql
    assert "SOURCE_EFFECTIVE_AT TIMESTAMPTZ" in sql
    assert "RECORDED_AT TIMESTAMPTZ" in sql
    assert "SOURCE_TIMESTAMP_RAW TEXT" in sql
    assert "SOURCE_OBSERVATIONS_RECORDED_AT_NEW_ROWS_CHECK" in sql
    assert "NOT VALID" in sql


def test_phase4_capture_relations_are_linked_and_append_only():
    sql = (MIGRATIONS / "0004_point_in_time_feature_capture.sql").read_text(encoding="utf-8").upper()
    required_tables = (
        "CAPTURE_MANIFESTS",
        "CAPTURE_MANIFEST_EVENTS",
        "PROVIDER_CAPTURE_REQUESTS",
        "ENTITY_CROSSWALK_VERSIONS",
        "FEATURE_SNAPSHOTS",
        "FEATURE_SNAPSHOT_ELIGIBILITY_EVENTS",
        "FEATURE_SNAPSHOT_LINKS",
    )
    for table in required_tables:
        assert f"CREATE TABLE {table}" in sql
        assert f"CREATE TRIGGER {table}_APPEND_ONLY" in sql

    assert "REFERENCES PROVIDER_RESPONSES(ID, PROVIDER, SOURCE_ID)" in sql
    assert "REFERENCES SOURCE_OBSERVATIONS(ID)" in sql
    assert "REFERENCES SOURCE_APPROVALS(APPROVAL_ID)" in sql
    assert "REFERENCES FIXTURES(ID)" in sql
    assert "ON DELETE CASCADE" not in sql


def test_phase4_feature_schema_fails_closed_for_missing_and_bad_features():
    sql = (MIGRATIONS / "0004_point_in_time_feature_capture.sql").read_text(encoding="utf-8").upper()
    assert "FEATURE_STATUS IN ('PRESENT','MISSING','REJECTED')" in sql
    assert "FEATURE_VALUE IS NULL" in sql
    assert "VALUE_SHA256 IS NULL" in sql
    assert "SOURCE_PUBLISHED_AT IS NOT NULL" in sql
    assert "RIGHTS_APPROVAL_ID IS NOT NULL" in sql
    assert "PREDICTION_CUTOFF_AT TIMESTAMPTZ NOT NULL" in sql
    assert "FEATURE_SET_SHA256 CHAR(64) NOT NULL" in sql
