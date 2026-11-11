import pytest

from veltrix_v2.ingestion.statsbomb_events import adapt_event, adapt_event_file


def event(**overrides):
    row = {
        "id": "0052d1b5-e2b0-4629-bbea-c18c884ab103",
        "index": 1,
        "period": 1,
        "timestamp": "00:00:06.293",
        "minute": 0,
        "second": 6,
        "type": {"id": 16, "name": "Shot"},
        "possession": 1,
        "possession_team": {"id": 1, "name": "Arsenal"},
        "team": {"id": 1, "name": "Arsenal"},
        "player": {"id": 99, "name": "Player"},
        "play_pattern": {"id": 1, "name": "Regular Play"},
        "location": [100.0, 40.0],
        "under_pressure": True,
        "counterpress": False,
        "shot": {
            "statsbomb_xg": 0.42,
            "outcome": {"id": 97, "name": "Goal"},
        },
    }
    row.update(overrides)
    return row


def test_event_identity_clock_and_context_are_preserved():
    item = adapt_event(event(), match_id="2781")
    assert item.event_id == "0052d1b5-e2b0-4629-bbea-c18c884ab103"
    assert item.match_id == "2781"
    assert item.event_index == 1
    assert item.period == 1
    assert item.timestamp_match_ms == 6293
    assert item.timestamp_semantics == "match_clock_not_utc"
    assert item.event_type_name == "Shot"
    assert item.possession_team_name == "Arsenal"
    assert item.location == (100.0, 40.0)


def test_event_specific_attributes_are_retained_without_xg_reinterpretation():
    item = adapt_event(event(), match_id="2781")
    assert item.raw_attributes["shot"]["statsbomb_xg"] == 0.42
    assert item.raw_attributes["shot"]["outcome"]["name"] == "Goal"


def test_nested_payload_is_immutable():
    item = adapt_event(event(), match_id="2781")
    with pytest.raises(TypeError):
        item.raw_attributes["shot"]["statsbomb_xg"] = 0.1


def test_event_file_requires_sorted_unique_ids_and_indexes():
    first = event()
    second = event(
        id="1052d1b5-e2b0-4629-bbea-c18c884ab103",
        index=2,
        timestamp="00:00:07.000",
    )
    result = adapt_event_file([first, second], match_id="2781")
    assert [item.event_index for item in result] == [1, 2]
    with pytest.raises(ValueError, match="DUPLICATE_EVENT_ID"):
        adapt_event_file([first, first], match_id="2781")
    with pytest.raises(ValueError, match="EVENT_ORDER_INVALID"):
        adapt_event_file([second, first], match_id="2781")


@pytest.mark.parametrize("timestamp", ["00:60:00.000", "00:00:60.000", "00:00:01.1234", "bad"])
def test_invalid_match_clock_is_rejected(timestamp):
    with pytest.raises(ValueError, match="INVALID_EVENT_TIMESTAMP"):
        adapt_event(event(timestamp=timestamp), match_id="2781")


def test_out_of_pitch_location_is_rejected():
    with pytest.raises(ValueError, match="LOCATION_OUT_OF_BOUNDS"):
        adapt_event(event(location=[121, 40]), match_id="2781")


def test_unknown_optional_fields_are_preserved():
    item = adapt_event(event(custom_future_field={"value": 7}), match_id="2781")
    assert item.raw_attributes["custom_future_field"]["value"] == 7


def test_invalid_flags_and_period_are_rejected():
    with pytest.raises(ValueError, match="UNDER_PRESSURE_INVALID"):
        adapt_event(event(under_pressure=1), match_id="2781")
    with pytest.raises(ValueError, match="PERIOD_INVALID"):
        adapt_event(event(period=6), match_id="2781")
