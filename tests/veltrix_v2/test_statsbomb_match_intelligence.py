import pytest

from veltrix_v2.ingestion.statsbomb_events import adapt_event
from veltrix_v2.ingestion.statsbomb_match_intelligence import aggregate_match


def row(event_id, index, event_type, team_id, team_name, **extra):
    base = {
        "id": event_id,
        "index": index,
        "period": 1,
        "timestamp": f"00:00:{index:02d}.000",
        "minute": 0,
        "second": index,
        "type": {"id": index, "name": event_type},
        "possession": 1,
        "possession_team": {"id": 1, "name": "Alpha"},
        "team": {"id": team_id, "name": team_name},
        "play_pattern": {"id": 1, "name": "Regular Play"},
        "under_pressure": index == 2,
        "counterpress": index == 2,
    }
    base.update(extra)
    return base


def events():
    return [
        adapt_event(row("0052d1b5-e2b0-4629-bbea-c18c884ab103", 1, "Pass", 1, "Alpha"), match_id="m1"),
        adapt_event(row(
            "1052d1b5-e2b0-4629-bbea-c18c884ab103", 2, "Shot", 1, "Alpha",
            shot={"statsbomb_xg": 0.42, "outcome": {"name": "Goal"}},
        ), match_id="m1"),
        adapt_event(row(
            "2052d1b5-e2b0-4629-bbea-c18c884ab103", 3, "Interception", 2, "Beta",
        ), match_id="m1"),
    ]


def test_aggregates_shots_xg_possessions_and_defensive_actions():
    result = aggregate_match(events())
    alpha = result.team_metrics[1]
    beta = result.team_metrics[2]
    assert result.event_count == 3
    assert result.possession_count == 1
    assert result.possession_team_counts[1] == 1
    assert alpha.shots == 1
    assert alpha.shots_on_target == 1
    assert alpha.goals_from_shots == 1
    assert alpha.statsbomb_xg == pytest.approx(0.42)
    assert alpha.statsbomb_xg_model_id == "statsbomb-open-data:shot.statsbomb_xg"
    assert alpha.possessions_won_or_started == 1
    assert alpha.under_pressure_events == 1
    assert alpha.counterpress_events == 1
    assert beta.defensive_actions["Interception"] == 1


def test_missing_xg_stays_missing_not_zero():
    data = events()
    shot = data[1]
    raw = dict(shot.raw_attributes)
    raw.pop("shot")
    from dataclasses import replace
    result = aggregate_match([data[0], replace(shot, raw_attributes=raw), data[2]])
    assert result.team_metrics[1].statsbomb_xg is None


def test_rejects_mixed_match_and_duplicate_events():
    data = events()
    from dataclasses import replace
    with pytest.raises(ValueError, match="MIXED_MATCH_IDS"):
        aggregate_match([data[0], replace(data[1], match_id="m2")])
    with pytest.raises(ValueError, match="DUPLICATE_EVENT_ID"):
        aggregate_match([data[0], data[0]])


def test_rejects_possession_owner_conflict():
    data = events()
    from dataclasses import replace
    bad = replace(data[2], possession_team_id=2, possession_team_name="Beta")
    with pytest.raises(ValueError, match="POSSESSION_OWNER_CONFLICT"):
        aggregate_match([data[0], data[1], bad])


def test_rejects_invalid_xg():
    data = events()
    from dataclasses import replace
    bad = replace(data[1], raw_attributes={"shot": {"statsbomb_xg": 1.2}})
    with pytest.raises(ValueError, match="XG_OUT_OF_RANGE"):
        aggregate_match([data[0], bad, data[2]])
