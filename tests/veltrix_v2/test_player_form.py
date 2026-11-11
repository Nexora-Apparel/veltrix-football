from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.features.player_form import PlayerMatchEvidence, build_player_form


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def evidence(index, **overrides):
    values = {
        "match_id": f"m{index}",
        "player_id": "p1",
        "team_id": "t1",
        "kickoff_utc": BASE + timedelta(days=index * 7),
        "available_at_utc": BASE + timedelta(days=index * 7 + 2),
        "metrics": {
            "minutes_played": 90, "goals": 1, "shots": 3,
            "xg": 0.4, "npxg": 0.3, "xa": 0.1,
        },
        "started": True,
        "xg_model_id": "openplay-xg-v1",
        "xa_model_id": "openplay-xa-v1",
    }
    values.update(overrides)
    return PlayerMatchEvidence(**values)


def test_builds_rolling_features_only_from_available_past_matches():
    rows = [evidence(i) for i in range(4)]
    cutoff = BASE + timedelta(days=24)
    result = build_player_form(rows, player_id="p1", cutoff_utc=cutoff, last_n=5)
    assert result.matches_used == 3
    assert result.sample_state == "usable_research_sample"
    assert result.minutes_avg == 90
    assert result.starts_rate == 1
    assert result.goals_per90 == pytest.approx(1)
    assert result.xg_per90 == pytest.approx(0.4)
    assert result.xg_model_id == "openplay-xg-v1"
    assert result.source_match_ids == ("m0", "m1", "m2")


def test_post_cutoff_or_not_yet_available_matches_are_excluded():
    rows = [
        evidence(0),
        evidence(1, available_at_utc=BASE + timedelta(days=50)),
        evidence(3),
    ]
    result = build_player_form(rows, player_id="p1", cutoff_utc=BASE + timedelta(days=30))
    assert result.source_match_ids == ("m0",)


def test_quarantined_rows_are_excluded_and_low_sample_is_explicit():
    rows = [
        evidence(0),
        evidence(1, quality_state="quarantined_known_data_issue"),
    ]
    result = build_player_form(rows, player_id="p1", cutoff_utc=BASE + timedelta(days=30))
    assert result.matches_used == 1
    assert result.sample_state == "low_sample"


def test_mixed_xg_models_fail_closed():
    rows = [evidence(0), evidence(1, xg_model_id="other-model")]
    with pytest.raises(ValueError, match="MIXED_XG_MODEL_IDENTITIES"):
        build_player_form(rows, player_id="p1", cutoff_utc=BASE + timedelta(days=30))


def test_duplicate_match_evidence_fails_closed():
    row = evidence(0)
    with pytest.raises(ValueError, match="DUPLICATE_MATCH_EVIDENCE"):
        build_player_form([row, row], player_id="p1", cutoff_utc=BASE + timedelta(days=30))


def test_unzoned_timestamps_and_missing_xg_model_are_rejected():
    with pytest.raises(ValueError, match="KICKOFF_MUST_BE_TIMEZONE_AWARE"):
        evidence(0, kickoff_utc=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="XG_MODEL_ID_REQUIRED"):
        evidence(0, xg_model_id=None)


def test_zero_minutes_produces_missing_per90_not_infinity():
    row = evidence(0, metrics={"minutes_played": 0, "goals": 0, "shots": 0, "xg": 0.0})
    result = build_player_form([row], player_id="p1", cutoff_utc=BASE + timedelta(days=10))
    assert result.goals_per90 is None
    assert result.xg_per90 is None
