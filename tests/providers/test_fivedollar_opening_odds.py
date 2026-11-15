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

def test_prospective_target_window_starts_now_and_ends_within_seven_days(monkeypatch):
    from datetime import timedelta
    from types import SimpleNamespace

    from scripts import phase2_capture_fivedollar_opening_odds as capture

    monkeypatch.setattr(
        capture, "_load_approval",
        lambda connection, at: SimpleNamespace(competition_scope="522514093"),
    )

    class Cursor:
        def __init__(self): self.calls = []; self.rows = []; self.description = ()
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, traceback): return False
        def execute(self, sql, params):
            self.calls.append((sql, params))
            if "COUNT(DISTINCT e.payload->>'target_source_fixture_id')" in sql:
                self.rows = [(0,)]
            else:
                self.rows = []
        def fetchone(self): return self.rows[0]
        def fetchall(self): return []

    class Connection:
        def __init__(self): self.cursor_instance = Cursor()
        def cursor(self): return self.cursor_instance

    connection = Connection()
    capture._load_targets(
        connection, mode="prospective", lookback_days=90, future_days=7,
        limit=25, now=RETRIEVED,
    )
    params = connection.cursor_instance.calls[0][1]
    assert params[3] == RETRIEVED
    assert params[4] == RETRIEVED + timedelta(days=7)
    assert params[2] == ["522514093"]


def test_prospective_targets_require_exact_ledger_and_current_scheduled_snapshot_evidence(monkeypatch):
    from types import SimpleNamespace

    from scripts import phase2_capture_fivedollar_opening_odds as capture

    monkeypatch.setattr(
        capture, "_load_approval",
        lambda connection, at: SimpleNamespace(competition_scope="3118717965"),
    )

    names = [
        "id", "ledger_fixture_id", "provider_fixture_id", "competition_id",
        "kickoff_at", "season_key", "crosswalk_version_id", "canonical_fixture_id",
        "provider_home_team_id", "provider_away_team_id", "provider_competition_id",
        "source_prediction_event_sha256", "prediction_cutoff_at",
        "prediction_evidence_class", "prediction_point_in_time_certifiable",
        "original_target_response_sha256", "original_target_manifest_sha256",
        "current_snapshot_provider_response_id", "current_snapshot_request_id",
        "current_snapshot_response_sha256", "current_snapshot_fetched_at",
        "home_team_crosswalk_version_id", "home_team_evidence_observation_id",
        "away_team_crosswalk_version_id", "away_team_evidence_observation_id",
        "competition_crosswalk_version_id", "competition_evidence_observation_id",
    ]
    row = (
        None, "5dollarfootballapi:1595172237", "1595172237", 1,
        RETRIEVED + timedelta(days=3), None, None, None,
        "1805143870", "2140840258", "3118717965",
        "a" * 64, RETRIEVED - timedelta(hours=23), "PROSPECTIVE_OBSERVED_ONLY", False,
        "b" * 64, "c" * 64, 123, "43767443333-3118717965-scheduled-1",
        "d" * 64, RETRIEVED, 11, 432397, 12, 432397, 13, 432397,
    )

    class Cursor:
        def __init__(self): self.calls = []; self.rows = []; self.description = ()
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, traceback): return False
        def execute(self, sql, params):
            self.calls.append((sql, params))
            if "COUNT(DISTINCT e.payload->>'target_source_fixture_id')" in sql:
                self.rows = [(1,)]
            else:
                self.rows = [row]
                self.description = [SimpleNamespace(name=name) for name in names]
        def fetchone(self): return self.rows[0]
        def fetchall(self): return self.rows

    class Connection:
        def __init__(self): self.cursor_instance = Cursor()
        def cursor(self): return self.cursor_instance

    connection = Connection()
    targets = capture._load_targets(
        connection, mode="prospective", lookback_days=90, future_days=7,
        limit=25, now=RETRIEVED,
    )
    assert len(targets) == 1
    target = targets[0]
    assert target["id"] is None
    assert target["canonical_fixture_id"] is None
    assert target["ledger_fixture_id"] == "5dollarfootballapi:1595172237"
    assert target["provider_fixture_id"] == "1595172237"
    assert target["prediction_point_in_time_certifiable"] is False
    assert target["current_snapshot_response_sha256"] == "d" * 64
    assert len(connection.cursor_instance.calls) == 2
    target_sql = connection.cursor_instance.calls[1][0]
    for required in ("paper_ledger_events", "provider_responses", "jsonb_array_elements",
                     "entity_crosswalk_versions", "source_observations"):
        assert required in target_sql


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
        connection, mode="historical", lookback_days=90, future_days=0,
        limit=25, now=RETRIEVED,
    )
    sql = connection.cursor_instance.sql
    assert "c.provider_competition_id::text = ANY(%s::text[])" in sql
    assert "f.competition_id::text = ANY(%s::text[])" not in sql
    assert connection.cursor_instance.params[7] == scope.split(",")
