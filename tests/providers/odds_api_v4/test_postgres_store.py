from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from veltrix_v2.providers.odds_api_v4.parser import parse_bulk_odds
from veltrix_v2.providers.odds_api_v4.postgres_store import (
    PostgresOddsQuoteStore, QuoteWriteContext,
)


UTC = timezone.utc


class FakeCursor:
    def __init__(self, *, duplicate=False):
        self.row = None
        self.inserted = 0
        self.duplicate = duplicate

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=()):
        if "FROM provider_responses" in sql:
            raw = RAW
            self.row = ("the_odds_api", "odds_api_v4",
                        hashlib.sha256(raw).hexdigest(), raw)
        elif "FROM provider_capture_requests" in sql:
            self.row = ("the_odds_api", "odds_api_v4", 11)
        elif "FROM entity_crosswalk_versions" in sql:
            self.row = ("the_odds_api", "odds_api_v4", "event-1", "123",
                        "FIXTURE", "RESOLVED", RETRIEVED - timedelta(days=1), None)
        elif "FROM source_approvals" in sql:
            self.row = ("approval-1", "the_odds_api", "odds_api_v4", "soccer_epl,soccer_spain_la_liga",
                        "odds_quote", "APPROVED", ["COLLECTION", "STORAGE"],
                        RETRIEVED - timedelta(days=2), RETRIEVED - timedelta(days=1),
                        RETRIEVED + timedelta(days=10), "a" * 64)
        elif "FROM source_approval_status_events" in sql:
            self.row = None
        elif "INSERT INTO odds_quote_observations" in sql:
            if self.duplicate:
                self.row = None
            else:
                self.inserted += 1
                self.row = (self.inserted,)
        else:
            raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self._cursor


NOW = datetime.now(UTC).replace(microsecond=0)
RETRIEVED = NOW - timedelta(seconds=2)
PUBLISHED = NOW - timedelta(seconds=3)
KICKOFF = NOW + timedelta(days=2)
CUTOFF = NOW + timedelta(days=1)
RAW = json.dumps([{
    "id": "event-1",
    "bookmakers": [{
        "key": "book-a", "title": "Book A",
        "markets": [{
            "key": "h2h", "last_update": PUBLISHED.isoformat(),
            "outcomes": [{"name": "Home", "price": 2.1}],
        }],
    }],
}]).encode()


def parsed():
    return parse_bulk_odds(RAW, sport_key="soccer_epl", retrieved_at=RETRIEVED)


def context(raw=RAW):
    return QuoteWriteContext(
        fixture_id=123, crosswalk_version_id=7, response_id=11,
        capture_request_id=12, rights_approval_id="approval-1",
        raw_response=raw, prediction_cutoff_at=CUTOFF, kickoff_at=KICKOFF,
    )


def test_writer_inserts_admitted_quote_atomically():
    cursor = FakeCursor()
    store = PostgresOddsQuoteStore(lambda: FakeConnection(cursor))
    result = store.write_capture(parsed(), context())
    assert result.inserted == 1
    assert result.duplicates == 0
    assert result.rejected == 0


def test_writer_reports_idempotent_duplicate_without_overwrite():
    cursor = FakeCursor(duplicate=True)
    store = PostgresOddsQuoteStore(lambda: FakeConnection(cursor))
    result = store.write_capture(parsed(), context())
    assert result.inserted == 0
    assert result.duplicates == 1


def test_writer_rejects_raw_response_hash_mismatch_before_database_access():
    called = False

    def connect():
        nonlocal called
        called = True
        raise AssertionError("database must not be opened")

    store = PostgresOddsQuoteStore(connect)
    with pytest.raises(ValueError, match="RAW_RESPONSE_HASH_MISMATCH"):
        store.write_capture(parsed(), context(b"altered"))
    assert not called


def test_writer_requires_exact_persisted_provider_request_link():
    class BrokenRequestCursor(FakeCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "FROM provider_capture_requests" in sql:
                self.row = ("other_provider", "other_source", 11)

    cursor = BrokenRequestCursor()
    store = PostgresOddsQuoteStore(lambda: FakeConnection(cursor))
    with pytest.raises(ValueError, match="CAPTURE_REQUEST_RESPONSE_LINK_MISMATCH"):
        store.write_capture(parsed(), context())


def test_writer_rejects_missing_raw_response_record():
    class MissingResponseCursor(FakeCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "FROM provider_responses" in sql:
                self.row = None

    cursor = MissingResponseCursor()
    store = PostgresOddsQuoteStore(lambda: FakeConnection(cursor))
    with pytest.raises(ValueError, match="PERSISTED_PROVIDER_RESPONSE_IDENTITY_MISMATCH"):
        store.write_capture(parsed(), context())


def test_writer_rejects_competition_outside_approved_scope():
    class OutOfScopeCursor(FakeCursor):
        def execute(self, sql, params=()):
            super().execute(sql, params)
            if "FROM source_approvals" in sql:
                self.row = ("approval-1", "the_odds_api", "odds_api_v4",
                            "soccer_spain_la_liga", "odds_quote", "APPROVED",
                            ["COLLECTION", "STORAGE"],
                            RETRIEVED - timedelta(days=2), RETRIEVED - timedelta(days=1),
                            RETRIEVED + timedelta(days=10), "a" * 64)

    cursor = OutOfScopeCursor()
    store = PostgresOddsQuoteStore(lambda: FakeConnection(cursor))
    result = store.write_capture(parsed(), context())
    assert result.inserted == 0
    assert result.rejected == 1
