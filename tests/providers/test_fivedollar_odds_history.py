import json
from decimal import Decimal
from datetime import datetime, timezone

import pytest

from veltrix_v2.providers.fivedollar_odds_history.parser import parse_odds_history

UTC = timezone.utc
KICKOFF = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)
RETRIEVED = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


def _response(ticks, *, fixture_id=481163241, market="1x2"):
    return json.dumps({
        "success": 1,
        "data": {
            "fixture_id": fixture_id,
            "bookmaker": {"name": "Bet365", "slug": "bet365"},
            "market": market,
            "ticks": ticks,
        },
    }, separators=(",", ":")).encode()


def _tick(stamp, **extra):
    return {
        "minute": None, "line": None,
        "home": 2.1, "draw": 3.2, "away": 3.6,
        "score": {"home": None, "away": None},
        "recorded_at": stamp,
        **extra,
    }


def test_preserves_source_tick_time_separately_from_local_retrieval_time():
    raw = _response([_tick("2026-11-14T10:00:00+00:00")])
    parsed = parse_odds_history(
        raw, expected_fixture_id="481163241", expected_market="1x2",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    row = parsed.observations[0]
    assert row.recorded_at == datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
    assert row.retrieved_at == RETRIEVED
    assert row.eligible_prematch is True
    assert row.home_price == Decimal("2.1")
    assert len(parsed.response_sha256) == 64


def test_excludes_inplay_ticks_even_when_timestamp_precedes_kickoff():
    raw = _response([
        _tick("2026-11-14T10:00:00Z"),
        _tick("2026-11-14T17:00:00Z", minute=0, score={"home": 0, "away": 0}),
    ])
    parsed = parse_odds_history(
        raw, expected_fixture_id="481163241", expected_market="1x2",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert parsed.observations[0].eligible_prematch is True
    assert parsed.observations[1].prematch_state is False
    assert parsed.observations[1].eligible_prematch is False


@pytest.mark.parametrize("stamp", ["2026-11-14T18:00:00Z", "2026-11-14T18:00:01Z"])
def test_excludes_ticks_at_or_after_kickoff(stamp):
    parsed = parse_odds_history(
        _response([_tick(stamp)]), expected_fixture_id="481163241",
        expected_market="1x2", retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert parsed.observations[0].eligible_prematch is False


def test_missing_or_naive_source_timestamp_is_preserved_but_never_eligible():
    parsed = parse_odds_history(
        _response([_tick(None), _tick("2026-11-14T10:00:00")]),
        expected_fixture_id="481163241", expected_market="1x2",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert all(row.eligible_prematch is False for row in parsed.observations)
    assert sum(d.code == "TICK_TIMESTAMP_MISSING_OR_UNTRUSTED" for d in parsed.diagnostics) == 2


def test_timestamp_after_retrieval_is_ineligible():
    parsed = parse_odds_history(
        _response([_tick("2026-11-15T13:00:00Z")]),
        expected_fixture_id="481163241", expected_market="1x2",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert parsed.observations[0].eligible_prematch is False
    assert any(d.code == "TICK_TIMESTAMP_AFTER_RETRIEVAL" for d in parsed.diagnostics)


def test_suspended_and_half_time_ticks_are_not_prematch_prices():
    parsed = parse_odds_history(
        _response([
            _tick("2026-11-14T10:00:00Z", suspended=True),
            _tick("2026-11-14T11:00:00Z", half_time=True),
        ]),
        expected_fixture_id="481163241", expected_market="1x2",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert all(not row.eligible_prematch for row in parsed.observations)


def test_fixture_market_and_response_identity_are_enforced():
    with pytest.raises(ValueError, match="ODDS_HISTORY_FIXTURE_ID_MISMATCH"):
        parse_odds_history(
            _response([_tick("2026-11-14T10:00:00Z")]),
            expected_fixture_id="different", expected_market="1x2",
            retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
        )
    with pytest.raises(ValueError, match="ODDS_HISTORY_MARKET_MISMATCH"):
        parse_odds_history(
            _response([_tick("2026-11-14T10:00:00Z")], market="asian"),
            expected_fixture_id="481163241", expected_market="1x2",
            retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
        )


def test_bad_prices_and_duplicate_ticks_are_diagnostic_and_not_admitted():
    duplicate = _tick("2026-11-14T10:00:00Z")
    invalid = _tick("2026-11-14T11:00:00Z", home=1.0)
    parsed = parse_odds_history(
        _response([duplicate, duplicate, invalid]),
        expected_fixture_id="481163241", expected_market="1x2",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert parsed.observations[0].eligible_prematch
    assert parsed.observations[1].eligible_prematch is False
    assert any(d.code == "DUPLICATE_TICK" for d in parsed.diagnostics)
    assert parsed.observations[2].eligible_prematch is False
    assert any(d.code == "TICK_PRICE_OR_LINE_MISSING" for d in parsed.diagnostics)


def test_invalid_input_and_naive_retrieval_or_kickoff_fail_closed():
    with pytest.raises(TypeError, match="RAW_RESPONSE_MUST_BE_BYTES"):
        parse_odds_history(
            "{}", expected_fixture_id="481163241", expected_market="1x2",
            retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
        )
    with pytest.raises(ValueError, match="RETRIEVED_AT_MUST_BE_TIMEZONE_AWARE"):
        parse_odds_history(
            b"{}", expected_fixture_id="481163241", expected_market="1x2",
            retrieved_at=datetime(2026, 11, 15), kickoff_at=KICKOFF,
        )


def test_out_of_order_ticks_are_diagnostic_and_not_admitted():
    parsed = parse_odds_history(
        _response([
            _tick("2026-11-14T11:00:00Z"),
            _tick("2026-11-14T10:00:00Z"),
        ]),
        expected_fixture_id="481163241", expected_market="1x2",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert parsed.observations[0].eligible_prematch is True
    assert parsed.observations[1].eligible_prematch is False
    assert any(d.code == "TICK_ORDER_NOT_CHRONOLOGICAL" for d in parsed.diagnostics)


def test_malformed_minute_and_state_flags_cannot_be_treated_as_prematch():
    parsed = parse_odds_history(
        _response([
            _tick("2026-11-14T10:00:00Z", minute="0"),
            _tick("2026-11-14T11:00:00Z", half_time="false"),
        ]),
        expected_fixture_id="481163241", expected_market="1x2",
        retrieved_at=RETRIEVED, kickoff_at=KICKOFF,
    )
    assert all(not row.eligible_prematch for row in parsed.observations)
    assert any(d.code == "TICK_MINUTE_INVALID" for d in parsed.diagnostics)
    assert any(d.code == "TICK_STATE_FLAG_INVALID" for d in parsed.diagnostics)
