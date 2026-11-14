from __future__ import annotations

import pytest

from veltrix_v2.reporting.reconciliation_read import PostgresTelegramReconciliationReader


KEY = "a" * 64


class FakeConnection:
    def __init__(self):
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        self.last_sql = " ".join(sql.split())
        self.queries.append((self.last_sql, params))
        return self

    def fetchone(self):
        if "current_database()" in self.last_sql:
            return ("veltrix_football_staging", "neondb_owner")
        return (
            KEY, "report-1", "b" * 64, "c" * 64, "OUTCOME_UNKNOWN",
            "TELEGRAM_TIMEOUT", "2026-11-14T10:00:00+00:00",
            "2026-11-14T10:06:00+00:00", [],
        )

    def fetchall(self):
        return [(
            "00000000-0000-4000-8000-000000000001",
            "INCONCLUSIVE",
            [],
            "s3://veltrix-evidence/reconciliation-1.json",
            "d" * 64,
            "telegram_delivery_audit",
            "operator-1",
            None,
            "2026-11-14T10:05:00+00:00",
            "2026-11-14T10:06:00+00:00",
            "MESSAGE_ACCEPTANCE_NOT_PROVEN",
            None,
        )]


def test_reader_sets_read_only_and_returns_claim_with_append_only_events():
    connection = FakeConnection()
    reader = PostgresTelegramReconciliationReader(lambda: connection)
    result = reader.inspect(KEY)

    assert result["status"] == "READ_ONLY_RECONCILIATION_INSPECTION"
    assert result["claim"]["state"] == "OUTCOME_UNKNOWN"
    assert result["claim"]["destination_sha256"] == "c" * 64
    assert "destination_id" not in result["claim"]
    assert "chat_id" not in result["claim"]
    assert result["reconciliation_events"][0]["outcome"] == "INCONCLUSIVE"
    assert connection.queries[0][0] == "SET TRANSACTION READ ONLY"
    assert connection.queries[1][0] == "SELECT current_database(), current_user"
    assert "FROM telegram_delivery_claims" in connection.queries[2][0]
    assert "FROM telegram_delivery_reconciliations" in connection.queries[3][0]
    assert all(
        query.startswith("SELECT") or query == "SET TRANSACTION READ ONLY"
        for query, _ in connection.queries
    )
    assert result["side_effects"] == {
        "database_writes": 0,
        "telegram_requests": 0,
        "retry_authorizations": 0,
    }


@pytest.mark.parametrize("key", ["", "ABC", "g" * 64, "a" * 63])
def test_reader_rejects_invalid_idempotency_key_before_connecting(key):
    called = []
    reader = PostgresTelegramReconciliationReader(lambda: called.append(True))
    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_INVALID"):
        reader.inspect(key)
    assert called == []


def test_reader_rejects_missing_claim():
    class MissingConnection(FakeConnection):
        def fetchone(self):
            if "current_database()" in self.last_sql:
                return ("veltrix_football_staging", "neondb_owner")
            return None

    reader = PostgresTelegramReconciliationReader(MissingConnection)
    with pytest.raises(ValueError, match="CLAIM_NOT_FOUND"):
        reader.inspect(KEY)



def test_reader_rejects_non_allowlisted_database_identity_before_claim_query():
    class WrongIdentityConnection(FakeConnection):
        def fetchone(self):
            if "current_database()" in self.last_sql:
                return ("veltrix_football_staging", "postgres")
            return super().fetchone()

    connection = WrongIdentityConnection()
    reader = PostgresTelegramReconciliationReader(lambda: connection)
    with pytest.raises(PermissionError, match="TARGET_NOT_ALLOWLISTED"):
        reader.inspect(KEY)
    assert len(connection.queries) == 2
