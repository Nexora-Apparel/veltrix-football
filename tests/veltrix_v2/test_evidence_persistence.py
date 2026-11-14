import pytest

from veltrix_v2.data.evidence_persistence import persist_provider_evidence_report


class NeverConnect:
    def __enter__(self):
        raise AssertionError("connection must not be opened")

    def cursor(self):
        raise AssertionError("cursor must not be opened")


def test_evidence_persistence_is_disabled_by_default():
    with pytest.raises(PermissionError, match="EVIDENCE_PERSISTENCE_WRITE_GUARD_DISABLED"):
        persist_provider_evidence_report(NeverConnect(), None, ())


def test_evidence_persistence_rejects_non_allowlisted_database_target():
    with pytest.raises(PermissionError, match="EVIDENCE_PERSISTENCE_TARGET_NOT_ALLOWLISTED"):
        persist_provider_evidence_report(
            NeverConnect(), None, (),
            write_enabled=True,
            environment="production",
            database_name="production",
            host="prod.example",
            role="app",
        )


def test_evidence_persistence_requires_typed_report_before_opening_connection():
    with pytest.raises(TypeError, match="PROVIDER_EVIDENCE_REPORT_REQUIRED"):
        persist_provider_evidence_report(
            NeverConnect(), None, (),
            write_enabled=True,
            environment="staging",
            database_name="veltrix_football_staging",
            host="ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech",
            role="neondb_owner",
        )
