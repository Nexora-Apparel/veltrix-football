from pathlib import Path
from hashlib import sha256
import pytest

from scripts.v2_apply_migrations import (
    EXPECTED_DATABASE, apply_sql_migration, validate_database_dsn,
)


def test_dsn_accepts_only_approved_neon_database_with_tls():
    validate_database_dsn(
        "postgresql://user:password@ep-test.us-east-1.aws.neon.tech/veltrix_football_v2?sslmode=require",
        expected_host="ep-test.us-east-1.aws.neon.tech",
    )


@pytest.mark.parametrize("dsn",[
    "postgresql://user:password@localhost/veltrix_football_v2?sslmode=require",
    "postgresql://user:password@ep-test.neon.tech/other_db?sslmode=require",
    "postgresql://user:password@ep-test.neon.tech/veltrix_football_v2",
    "mysql://user:password@ep-test.neon.tech/veltrix_football_v2?sslmode=require",
])
def test_dsn_rejects_wrong_database_host_scheme_or_missing_tls(dsn):
    with pytest.raises(ValueError):
        validate_database_dsn(dsn, expected_host="ep-test.neon.tech")


def test_approved_database_name_cannot_be_overridden():
    with pytest.raises(ValueError,match="V2_DATABASE_NAME_MUST_MATCH_APPROVED_TARGET"):
        validate_database_dsn(
            "postgresql://user:password@ep-test.neon.tech/veltrix_football_v2?sslmode=require",
            expected_database="other_db", expected_host="ep-test.neon.tech",
        )


def test_migration_runner_requires_exact_checksum():
    with pytest.raises(ValueError,match="MIGRATION_CHECKSUM_INPUT_MISMATCH"):
        apply_sql_migration(None,migration_version="001",sql="SELECT 1",
                            checksum_sha256="0"*64)


def test_dsn_rejects_hostname_not_on_exact_allowlist():
    with pytest.raises(ValueError,match="V2_DATABASE_HOST_MUST_MATCH_EXPLICIT_ALLOWLIST"):
        validate_database_dsn(
            "postgresql://user:password@ep-test.neon.tech/veltrix_football_v2?sslmode=require",
            expected_host="another-project.neon.tech",
        )
