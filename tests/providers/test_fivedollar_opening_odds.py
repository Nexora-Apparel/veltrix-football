import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from veltrix_v2.providers.fivedollar_odds_history.fixture_odds_parser import (
    parse_fixture_opening_1x2,
)

UTC = timezone.utc
KICKOFF = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)
RETRIEVED = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def _body(*, opening="DEFAULT", closing=None, fixture_id=481163241):
    if opening == "DEFAULT":
        opening = {
            "home": 2.1, "draw": 3.2, "away": 3.6,
            "opened_at": "2026-11-14T10:00:00+00:00",
        }
    return json.dumps({
        "success": 1,
        "data": {
            "id": fixture_id,
            "odds": {
                "1x2": {
                    "opening": opening,
                    "closing": closing if closing is not None else {
                        "home": 1.9, "draw": 3.4, "away": 4.0,
                    },
                    "inplay": None,
                }
            },
        },
    }, separators=(",", ":")).encode()


def test_opening_quote_timestamp_is_preserved_as_point_in_time_evidence():
    parsed = parse_fixture_opening_1x2(
        _body(), expected_fixture_id="481163241",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    row = parsed.observation
    assert row.eligible_pit is True
    assert row.opened_at == datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
    assert row.retrieved_at == RETRIEVED
    assert row.home_price == Decimal("2.1")
    assert row.bookmaker_slug == "bet365"
    assert len(row.response_sha256) == 64


def test_closing_snapshot_without_its_own_timestamp_is_never_substituted():
    parsed = parse_fixture_opening_1x2(
        _body(opening=None, closing={
            "home": 1.9, "draw": 3.4, "away": 4.0,
            "closed_at": "2026-11-14T17:55:00Z",
        }),
        expected_fixture_id="481163241",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert parsed.observation.eligible_pit is False
    assert parsed.observation.opened_at is None
    assert any(d.code == "OPENING_QUOTE_MISSING" for d in parsed.diagnostics)


@pytest.mark.parametrize("stamp", ["2026-11-14T18:00:00Z", "2026-11-14T18:01:00Z"])
def test_opening_quote_at_or_after_kickoff_is_not_pit(stamp):
    parsed = parse_fixture_opening_1x2(
        _body(opening={
            "home": 2.1, "draw": 3.2, "away": 3.6, "opened_at": stamp,
        }),
        expected_fixture_id="481163241",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert parsed.observation.eligible_pit is False
    assert any(d.code == "OPENING_TIMESTAMP_NOT_PREMATCH" for d in parsed.diagnostics)


def test_missing_or_naive_opening_timestamp_is_not_pit():
    for opening in (
        {"home": 2.1, "draw": 3.2, "away": 3.6},
        {"home": 2.1, "draw": 3.2, "away": 3.6, "opened_at": "2026-11-14T10:00:00"},
    ):
        parsed = parse_fixture_opening_1x2(
            _body(opening=opening), expected_fixture_id="481163241",
            retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
        )
        assert parsed.observation.eligible_pit is False
        assert any(d.code == "OPENING_TIMESTAMP_MISSING_OR_UNTRUSTED" for d in parsed.diagnostics)


def test_invalid_prices_or_future_source_timestamp_fail_closed():
    parsed = parse_fixture_opening_1x2(
        _body(opening={
            "home": 1.0, "draw": 3.2, "away": 3.6,
            "opened_at": "2026-11-15T13:00:00Z",
        }),
        expected_fixture_id="481163241",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert parsed.observation.eligible_pit is False
    assert any(d.code == "OPENING_TIMESTAMP_AFTER_RETRIEVAL" for d in parsed.diagnostics)
    assert any(d.code == "OPENING_1X2_PRICE_INVALID_OR_MISSING" for d in parsed.diagnostics)


def test_fixture_identity_and_timezones_are_required():
    with pytest.raises(ValueError, match="FIXTURE_ODDS_ID_MISMATCH"):
        parse_fixture_opening_1x2(
            _body(), expected_fixture_id="wrong",
            retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
        )
    with pytest.raises(ValueError, match="KICKOFF_AT_MUST_BE_TIMEZONE_AWARE"):
        parse_fixture_opening_1x2(
            _body(), expected_fixture_id="481163241",
            retrieved_at=RETRIEVED, kickoff_at=datetime(2026, 11, 14, 18),
        )

def test_capture_target_scope_uses_provider_competition_ids(monkeypatch):
    from types import SimpleNamespace

    from scripts import phase2_capture_fivedollar_opening_odds as capture

    scope = "3118717965,3405541143,3614399544,4160026622,4212821298,522514093,686337048"
    monkeypatch.setattr(
        capture, "_load_approval",
        lambda connection, at: SimpleNamespace(competition_scope=scope),
    )

    class Cursor:
        description = ()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    connection = Connection()
    capture._load_targets(
        connection, lookback_days=90, limit=25, now=RETRIEVED,
    )
    sql = connection.cursor_instance.sql
    assert "c.provider_competition_id::text = ANY(%s::text[])" in sql
    assert "f.competition_id::text = ANY(%s::text[])" not in sql
    assert connection.cursor_instance.params[7] == scope.split(",")
