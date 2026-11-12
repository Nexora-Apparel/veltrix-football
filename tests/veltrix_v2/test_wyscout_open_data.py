from datetime import datetime, timezone

import pytest

from veltrix_v2.providers.wyscout_open_data import (
    CONSERVATIVE_AVAILABLE_AT_UTC,
    SOURCE_LICENSE_ID,
    WyscoutShotTrainingExample,
    parse_wyscout_shot_events,
)

UTC = timezone.utc
KICKOFF = datetime(2018, 6, 10, 20, 0, tzinfo=UTC)


def event(**overrides):
    row = {
        "id": 12345,
        "matchId": 9001,
        "eventName": "Shot",
        "subEventName": "Shot",
        "teamId": 44,
        "playerId": 55,
        "matchPeriod": "1H",
        "eventSec": 31.25,
        "positions": [{"x": 91, "y": 29}, {"x": 0, "y": 0}],
        "tags": [{"id": 101}, {"id": 402}, {"id": 201}, {"id": 1901}, {"id": 1203}],
    }
    row.update(overrides)
    return row


def parse(rows, **overrides):
    args = {
        "competition_key": "world-cup",
        "season": "2018",
        "match_kickoff_utc": KICKOFF,
        "source_available_at_utc": CONSERVATIVE_AVAILABLE_AT_UTC,
        "source_observation_id": "obs-wyscout-9001",
    }
    args.update(overrides)
    return parse_wyscout_shot_events({"events": rows}, **args)


def test_parses_shot_outcome_context_and_cc_by_provenance():
    result, = parse([event()])
    assert isinstance(result, WyscoutShotTrainingExample)
    assert result.match_id == "9001"
    assert result.event_id == "12345"
    assert result.team_id == "44"
    assert result.player_id == "55"
    assert result.shot_x_pct == 91
    assert result.shot_y_pct == 29
    assert result.goal is True
    assert result.body_part == "RIGHT_FOOT"
    assert result.goal_zone == "GOAL_MID_CENTRE"
    assert result.is_counterattack is True
    assert result.is_opportunity is True
    assert result.source_observation_id == "obs-wyscout-9001"
    assert result.source_license_id == SOURCE_LICENSE_ID
    assert result.event_time_utc == datetime(2018, 6, 10, 20, 0, 31, 250000, tzinfo=UTC)


def test_skips_non_shots_and_penalty_shootout_attempts():
    rows = [
        event(id=1, eventName="Pass", subEventName="Simple pass"),
        event(id=2, matchPeriod="P"),
    ]
    assert parse(rows) == ()


def test_includes_penalty_and_direct_free_kick_attempts_as_distinct_context():
    penalty = event(
        id=10,
        eventName="Free Kick",
        subEventName="Penalty",
        tags=[{"id": 101}, {"id": 402}],
    )
    direct = event(
        id=11,
        eventName="Free Kick",
        subEventName="Free kick shot",
        tags=[{"id": 403}],
    )
    rows = parse([penalty, direct])
    assert len(rows) == 2
    assert rows[0].is_penalty is True
    assert rows[0].is_direct_free_kick is False
    assert rows[1].is_penalty is False
    assert rows[1].is_direct_free_kick is True
    assert rows[1].body_part == "HEAD_OR_BODY"


def test_period_offsets_are_applied_to_event_time():
    second_half = event(matchPeriod="2H", eventSec=120)
    extra_time = event(id=2, matchPeriod="E1", eventSec=30)
    rows = parse([second_half, extra_time])
    assert rows[0].event_time_utc == datetime(2018, 6, 10, 20, 47, tzinfo=UTC)
    assert rows[1].event_time_utc == datetime(2018, 6, 10, 21, 30, 30, tzinfo=UTC)


def test_rejects_missing_observation_id_and_non_conservative_availability():
    with pytest.raises(ValueError, match="SOURCE_OBSERVATION_ID_REQUIRED"):
        parse([event()], source_observation_id=" ")
    with pytest.raises(ValueError, match="CONSERVATIVE_RELEASE_DATE"):
        parse(
            [event()],
            source_available_at_utc=datetime(2019, 10, 29, tzinfo=UTC),
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"positions": []}, "START_POSITION_REQUIRED"),
        ({"positions": [{"x": 101, "y": 50}]}, "COORDINATES_OUT_OF_RANGE"),
        ({"matchPeriod": "Q1"}, "PERIOD_UNSUPPORTED"),
        ({"eventSec": -1}, "EVENT_SECONDS_NEGATIVE"),
        ({"tags": [{"id": "101"}]}, "TAG_RECORD_INVALID"),
    ],
)
def test_rejects_invalid_shot_event_data(overrides, message):
    with pytest.raises(ValueError, match=message):
        parse([event(**overrides)])


def test_rejects_duplicate_event_ids_within_match_payload():
    with pytest.raises(ValueError, match="DUPLICATE_SHOT_EVENT_ID"):
        parse([event(id=5), event(id=5)])
