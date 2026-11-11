from datetime import datetime, timezone

import pytest

from veltrix_v2.contracts import PlayerMatchStats


KICKOFF = datetime(2026, 11, 1, 15, tzinfo=timezone.utc)
AVAILABLE = datetime(2026, 11, 1, 17, tzinfo=timezone.utc)
RETRIEVED = datetime(2026, 11, 1, 18, tzinfo=timezone.utc)
HASH = "a" * 64


def build(**overrides):
    values = dict(
        provider="openplay",
        provider_match_id="match-1",
        provider_player_id="player-1",
        provider_team_id="team-1",
        competition_key="EPL",
        season="2026/27",
        kickoff_utc=KICKOFF,
        retrieved_at_utc=RETRIEVED,
        available_at_utc=AVAILABLE,
        payload_sha256=HASH,
        schema_version="player-match-v1",
        rights_approval_id="openplay-cc-by-4.0-approved",
        stats={"minutes_played": 90, "goals": 1, "assists": 0, "xg": 0.72, "xa": 0.13},
        started=True,
        xg_model_id="openplay-noah-bair-v1",
        xa_model_id="openplay-xa-v1",
    )
    values.update(overrides)
    return PlayerMatchStats(**values)


def test_player_stats_keep_provider_and_metric_model_provenance():
    item = build()
    assert item.provider == "openplay"
    assert item.xg_model_id == "openplay-noah-bair-v1"
    assert item.stats["xg"] == 0.72


def test_missing_values_remain_none_not_zero():
    item = build(stats={"minutes_played": 0, "goals": None, "xg": None, "xa": None}, xg_model_id=None, xa_model_id=None)
    assert item.stats["goals"] is None
    assert item.stats["minutes_played"] == 0


def test_stats_are_immutable():
    item = build()
    with pytest.raises(TypeError):
        item.stats["goals"] = 99


def test_point_in_time_cutoff_excludes_late_observation():
    item = build()
    assert not item.available_by(datetime(2026, 11, 1, 16, tzinfo=timezone.utc))
    assert item.available_by(datetime(2026, 11, 1, 17, tzinfo=timezone.utc))


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        build(kickoff_utc=datetime(2026, 11, 1, 15))


def test_stats_cannot_be_available_before_kickoff():
    with pytest.raises(ValueError, match="before kickoff"):
        build(available_at_utc=datetime(2026, 11, 1, 14, tzinfo=timezone.utc))


def test_xg_requires_model_identity():
    with pytest.raises(ValueError, match="xg_model_id"):
        build(xg_model_id=None)


def test_unknown_metrics_fail_closed():
    with pytest.raises(ValueError, match="unsupported player metrics"):
        build(stats={"player_rating": 9.2})


def test_counts_reject_fractional_values():
    with pytest.raises(ValueError, match="integer count"):
        build(stats={"goals": 1.5}, xg_model_id=None, xa_model_id=None)


def test_boolean_is_not_accepted_as_a_numeric_stat():
    with pytest.raises(ValueError, match="numeric or None"):
        build(stats={"goals": True}, xg_model_id=None, xa_model_id=None)
