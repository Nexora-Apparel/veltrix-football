from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.ingestion.fivedollar_odds import parse_fivedollar_fixture_odds

UTC = timezone.utc
KICKOFF = datetime(2026, 11, 12, 19, 0, tzinfo=UTC)
CAPTURE = datetime(2026, 11, 12, 5, 0, tzinfo=UTC)


def payload():
    return {
        "success": 1,
        "data": {
            "fixture_id": "fixture-123",
            "bookmakers": [{
                "slug": "bet365",
                "odds": {
                    "1x2": {
                        "opening": {"home": 2.0, "draw": 3.4, "away": 4.0, "opened_at": "2026-11-10T12:00:00+00:00"},
                        "closing": {"home": 1.95, "draw": 3.5, "away": 4.1},
                    },
                    "btts": {
                        "opening": {"yes": 1.8, "no": 2.0},
                        "closing": {"yes": 1.85, "no": 1.95},
                    },
                    "goal_line_fixed": [
                        {"line": 1.5, "closing": {"over": 1.2, "under": 4.2}},
                        {"line": 2.5, "closing": {"over": 1.9, "under": 1.9}},
                    ],
                },
            }],
        },
    }


def test_parser_emits_complete_timestamped_1x2_btts_and_totals():
    result = parse_fivedollar_fixture_odds(
        payload(), fixture_id="fixture-123", kickoff_at=KICKOFF, captured_at=CAPTURE
    )
    assert result.missing_markets == ()
    assert len(result.snapshots) == 7
    assert {row.market for row in result.snapshots} == {"1X2", "BTTS", "TOTALS"}
    assert all(row.captured_at == CAPTURE for row in result.snapshots)
    assert all(row.kickoff_at == KICKOFF for row in result.snapshots)
    totals = [row for row in result.snapshots if row.market == "TOTALS"]
    assert {row.line for row in totals} == {Decimal("2.5")}
    assert {row.selection for row in totals} == {"OVER", "UNDER"}


def test_missing_btts_is_reported_not_fabricated():
    body = payload()
    del body["data"]["bookmakers"][0]["odds"]["btts"]
    result = parse_fivedollar_fixture_odds(
        body, fixture_id="fixture-123", kickoff_at=KICKOFF, captured_at=CAPTURE
    )
    assert "BTTS" in result.missing_markets
    assert not any(row.market == "BTTS" for row in result.snapshots)


def test_wrong_fixture_and_bookmaker_are_rejected():
    with pytest.raises(ValueError, match="FIXTURE_ID_MISMATCH"):
        parse_fivedollar_fixture_odds(
            payload(), fixture_id="another-fixture", kickoff_at=KICKOFF, captured_at=CAPTURE
        )
    with pytest.raises(ValueError, match="BOOKMAKER_MISSING"):
        parse_fivedollar_fixture_odds(
            payload(), fixture_id="fixture-123", kickoff_at=KICKOFF,
            captured_at=CAPTURE, bookmaker_slug="pinnacle"
        )


def test_invalid_or_inplay_price_is_not_emitted():
    body = payload()
    body["data"]["bookmakers"][0]["odds"]["1x2"]["closing"]["home"] = 1.0
    result = parse_fivedollar_fixture_odds(
        body, fixture_id="fixture-123", kickoff_at=KICKOFF, captured_at=CAPTURE
    )
    assert "1X2" in result.missing_markets
    assert not any(row.market == "1X2" for row in result.snapshots)


def test_capture_at_or_after_kickoff_fails_through_contract():
    with pytest.raises(ValueError, match="CAPTURE_MUST_PRECEDE_KICKOFF"):
        parse_fivedollar_fixture_odds(
            payload(), fixture_id="fixture-123", kickoff_at=KICKOFF,
            captured_at=KICKOFF + timedelta(seconds=1)
        )


def test_integer_total_line_is_rejected():
    with pytest.raises(ValueError, match="HALF_GOAL"):
        parse_fivedollar_fixture_odds(
            payload(), fixture_id="fixture-123", kickoff_at=KICKOFF,
            captured_at=CAPTURE, total_line=Decimal("2.0")
        )


def test_partial_market_is_reported_and_no_partial_rows_are_emitted():
    body = payload()
    body["data"]["bookmakers"][0]["odds"]["1x2"]["closing"]["away"] = None
    result = parse_fivedollar_fixture_odds(
        body, fixture_id="fixture-123", kickoff_at=KICKOFF, captured_at=CAPTURE
    )
    assert "1X2" in result.missing_markets
    assert not any(row.market == "1X2" for row in result.snapshots)



def test_capture_after_kickoff_is_rejected_even_when_no_markets_exist():
    payload = {"success": 1, "data": {"fixture_id": "fx-1", "bookmakers": [
        {"slug": "bet365", "odds": {}}
    ]}}
    with pytest.raises(ValueError, match="CAPTURE_MUST_PRECEDE_KICKOFF"):
        parse_fivedollar_fixture_odds(
            payload,
            fixture_id="fx-1",
            kickoff_at=KICKOFF,
            captured_at=KICKOFF + timedelta(seconds=1),
        )



def test_source_observation_id_is_propagated_to_every_odds_selection():
    result = parse_fivedollar_fixture_odds(
        payload(),
        fixture_id="fixture-123",
        kickoff_at=KICKOFF,
        captured_at=CAPTURE,
        source_observation_id="obs-5dollar-payload-123",
    )
    assert len(result.snapshots) == 7
    assert {
        row.source_observation_id for row in result.snapshots
    } == {"obs-5dollar-payload-123"}


def test_invalid_source_observation_id_is_rejected():
    with pytest.raises(ValueError, match="SOURCE_OBSERVATION_ID_REQUIRED"):
        parse_fivedollar_fixture_odds(
            payload(),
            fixture_id="fixture-123",
            kickoff_at=KICKOFF,
            captured_at=CAPTURE,
            source_observation_id="   ",
        )
