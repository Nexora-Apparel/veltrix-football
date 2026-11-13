from datetime import date, datetime, timedelta, timezone

import pytest

from veltrix_v2.data.credit_reservations import (
    BudgetSnapshotEvidence,
    PostgresCreditReservationStore,
    ReservationEvent,
)
from veltrix_v2.providers.odds_api_v4.reservations import (
    ReservationBudget,
    ReservationRequest,
)


NOW = datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
HASH = "a" * 64


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = None

    def execute(self, query, params=None):
        self.connection.calls.append((query, params))
        normalized = " ".join(query.split())
        if normalized == "SELECT current_database()":
            self.result = (self.connection.database,)
        elif "SELECT budget_snapshot_id,provider" in normalized:
            self.result = None
        elif "INSERT INTO provider_credit_budget_snapshots" in normalized:
            self.result = (17,)
        elif "SELECT reserve_provider_credits(" in normalized:
            self.result = (23,)
        elif "SELECT provider,provider_account_ref,billing_period_start" in normalized:
            self.result = ("the_odds_api", "acct-test", date(2026, 11, 1), date(2026, 12, 1))
        elif "SELECT event_sequence,event_type,reserved_credits,event_sha256" in normalized:
            self.result = (1, "RESERVED", 4, HASH, NOW)
        elif "SELECT append_provider_credit_reservation_event(" in normalized:
            self.result = (29,)
        else:
            self.result = None

    def fetchone(self):
        return self.result


class FakeConnection:
    def __init__(self, database="veltrix_football_staging"):
        self.database = database
        self.calls = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def budget():
    return ReservationBudget(
        provider="the_odds_api",
        account_ref="acct-test",
        period_start=date(2026, 11, 1),
        period_end=date(2026, 12, 1),
        monthly_allowance=100,
        provider_remaining=80,
        monthly_hard_cap=90,
        per_run_hard_cap=20,
        request_count_cap=10,
        observed_at=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(minutes=5),
        evidence_sha256=HASH,
    )


def request():
    return ReservationRequest(
        reservation_key="run-1:req-1:attempt-1",
        provider="the_odds_api",
        account_ref="acct-test",
        period_start=date(2026, 11, 1),
        period_end=date(2026, 12, 1),
        run_key="run-1",
        manifest_id=5,
        request_key="req-1",
        attempt_number=1,
        request_fingerprint="b" * 64,
        estimated_credits=4,
        requested_at=NOW,
    )


def test_write_adapter_is_disabled_by_default():
    connection = FakeConnection()
    store = PostgresCreditReservationStore(lambda: connection)
    with pytest.raises(RuntimeError, match="CREDIT_LEDGER_WRITES_DISABLED"):
        store.persist_budget_snapshot(
            BudgetSnapshotEvidence(
                budget(), "evidence://budget", "terms-v1",
                "evidence://terms", "c" * 64, ("approval-1",),
            )
        )
    assert connection.calls == []


def test_production_database_cannot_be_enabled():
    with pytest.raises(RuntimeError, match="PRODUCTION_CREDIT_LEDGER_WRITES_DISABLED"):
        PostgresCreditReservationStore(
            lambda: FakeConnection("veltrix_football"),
            allow_writes=True,
            expected_database="veltrix_football",
        )


def test_budget_snapshot_persistence_is_scoped_and_append_only():
    connection = FakeConnection()
    store = PostgresCreditReservationStore(
        lambda: connection,
        allow_writes=True,
        expected_database="veltrix_football_staging",
    )
    evidence = BudgetSnapshotEvidence(
        budget(), "evidence://budget", "terms-v1",
        "evidence://terms", "c" * 64, ("approval-1",),
    )
    assert store.persist_budget_snapshot(evidence) == 17
    statements = [query for query, _ in connection.calls]
    assert any("pg_advisory_xact_lock" in query for query in statements)
    assert any("INSERT INTO provider_credit_budget_snapshots" in query for query in statements)
    assert connection.committed
    assert connection.closed


def test_reservation_uses_atomic_database_function_after_python_prevalidation():
    connection = FakeConnection()
    store = PostgresCreditReservationStore(
        lambda: connection,
        allow_writes=True,
        expected_database="veltrix_football_staging",
    )
    assert store.reserve(
        request(), budget(), budget_snapshot_id=17, actor="operator", now=NOW
    ) == 23
    reserve_calls = [
        (query, params) for query, params in connection.calls
        if "reserve_provider_credits(" in query
    ]
    assert len(reserve_calls) == 1
    assert reserve_calls[0][1][0] == "run-1:req-1:attempt-1"
    assert reserve_calls[0][1][11] == 17
    assert connection.committed


def test_reservation_prevalidation_blocks_before_opening_database():
    opened = []
    store = PostgresCreditReservationStore(
        lambda: opened.append(True) or FakeConnection(),
        allow_writes=True,
        expected_database="veltrix_football_staging",
    )
    incomplete = ReservationBudget(
        provider="the_odds_api", account_ref="acct-test",
        period_start=date(2026, 11, 1), period_end=date(2026, 12, 1),
        monthly_allowance=None, provider_remaining=80, monthly_hard_cap=90,
        per_run_hard_cap=20, request_count_cap=10,
        observed_at=NOW, valid_until=NOW + timedelta(minutes=1),
        evidence_sha256=HASH,
    )
    with pytest.raises(ValueError, match="BUDGET_EVIDENCE_INCOMPLETE"):
        store.reserve(
            request(), incomplete, budget_snapshot_id=17,
            actor="operator", now=NOW,
        )
    assert opened == []


def test_reservation_event_append_uses_account_period_lock_and_database_transition():
    connection = FakeConnection()
    store = PostgresCreditReservationStore(
        lambda: connection,
        allow_writes=True,
        expected_database="veltrix_football_staging",
    )
    event = ReservationEvent(
        reservation_key="run-1:req-1:attempt-1",
        event_type="DISPATCH_CONFIRMED",
        reserved_credits=4,
        actual_credits=None,
        reason_code="REQUEST_STARTED",
        evidence_sha256="d" * 64,
        actor="operator",
        occurred_at=NOW + timedelta(seconds=1),
    )
    assert store.append_event(event) == 29
    statements = [query for query, _ in connection.calls]
    assert any("pg_advisory_xact_lock" in query for query in statements)
    assert any("append_provider_credit_reservation_event(" in query for query in statements)
    assert connection.committed
