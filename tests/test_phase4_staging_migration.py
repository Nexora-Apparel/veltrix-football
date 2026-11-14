import pytest

from scripts.phase4_staging_migration import validate_connection_target


EXPECTED = {
    "host": "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech",
    "dbname": "veltrix_football_staging",
    "user": "neondb_owner",
    "password": "not-a-real-secret",
}


def test_exact_direct_staging_target_is_accepted():
    assert validate_connection_target(
        EXPECTED,
        expected_database="veltrix_football_staging",
        expected_host="ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech",
        expected_role="neondb_owner",
    ) == {
        "host": EXPECTED["host"],
        "database": EXPECTED["dbname"],
        "role": EXPECTED["user"],
    }


@pytest.mark.parametrize(
    ("patch", "expected_error"),
    [
        ({"host": "ep-ancient-block-bcb439pk-pooler.c-16.us-east-1.aws.neon.tech"}, "STAGING_DATABASE_HOST_NOT_ALLOWLISTED"),
        ({"host": "other.neon.tech"}, "STAGING_DATABASE_HOST_NOT_ALLOWLISTED"),
        ({"dbname": "veltrix-football"}, "STAGING_DATABASE_NAME_NOT_ALLOWLISTED"),
        ({"user": "postgres"}, "STAGING_DATABASE_ROLE_NOT_ALLOWLISTED"),
    ],
)
def test_wrong_target_is_rejected(patch, expected_error):
    params = {**EXPECTED, **patch}
    with pytest.raises(RuntimeError, match=expected_error):
        validate_connection_target(
            params,
            expected_database="veltrix_football_staging",
            expected_host="ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech",
            expected_role="neondb_owner",
        )


def test_missing_allowlist_configuration_fails_closed():
    with pytest.raises(RuntimeError, match="STAGING_DATABASE_HOST_NOT_ALLOWLISTED"):
        validate_connection_target(
            EXPECTED,
            expected_database="veltrix_football_staging",
            expected_host="",
            expected_role="neondb_owner",
        )
