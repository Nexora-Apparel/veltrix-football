from pathlib import Path


SQL = Path("db/migrations/0005_provider_credit_reservation_ledger.sql").read_text()


def test_credit_ledger_is_append_only_and_restricts_manifest_deletion():
    assert "provider_credit_budget_snapshots_append_only" in SQL
    assert "provider_credit_reservation_events_append_only" in SQL
    assert "ON DELETE RESTRICT" in SQL
    assert "BEFORE UPDATE OR DELETE" in SQL


def test_reservation_function_serializes_account_period_not_snapshot_only():
    assert "pg_advisory_xact_lock" in SQL
    assert "p_account_ref" in SQL
    assert "p_period_start" in SQL
    assert "p_period_end" in SQL


def test_independent_limits_and_unknowns_are_fail_closed():
    for column in ("monthly_allowance", "provider_remaining", "monthly_hard_cap",
                   "per_run_hard_cap", "request_count_cap"):
        assert column in SQL
    assert "CREDIT_RESERVATION_CAPACITY_EXCEEDED" in SQL
    assert "CREDIT_BUDGET_SNAPSHOT_MISMATCH_OR_STALE" in SQL
    assert "valid_until TIMESTAMPTZ NOT NULL" in SQL
    assert "p_occurred_at > b.valid_until" in SQL


def test_idempotency_is_bound_to_full_immutable_request_identity():
    assert "CREDIT_RESERVATION_IDEMPOTENCY_CONFLICT" in SQL
    assert "WHERE event_sequence = 1" in SQL
    assert SQL.count("CREATE TABLE provider_credit_") == 2
    assert SQL.count("CREATE OR REPLACE FUNCTION") == 2
    for column in ("request_fingerprint", "capture_manifest_id", "attempt_number",
                   "budget_snapshot_id", "estimated_credits", "run_key"):
        assert column in SQL


def test_no_network_or_secret_handling_is_added_to_reservation_migration():
    forbidden = ("http://", "https://", "api_key", "authorization", "fetch(")
    lowered = SQL.lower()
    assert all(value not in lowered for value in forbidden)
