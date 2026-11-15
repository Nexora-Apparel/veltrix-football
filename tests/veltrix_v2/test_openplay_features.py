from datetime import datetime, timezone

import pytest

from veltrix_v2.data.openplay_features import (
    OPENPLAY_XG_MODEL,
    build_openplay_team_match_features,
    eligible_openplay_team_match_features,
)

UTC = timezone.utc
SAVED = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
RECORDED = datetime(2026, 11, 15, 13, 0, tzinfo=UTC)
CUTOFF_BEFORE_IMPORT = datetime(2026, 11, 15, 12, 59, tzinfo=UTC)
CUTOFF_AFTER_IMPORT = datetime(2026, 11, 15, 13, 1, tzinfo=UTC)


def _inputs():
    return {
        "matches": [{
            "match_id": 7, "comp": "eng", "season": "2526",
            "date": "2026-10-30", "scraped_at": "2026-11-02T12:00:00Z",
            "home_team_id": 100, "away_team_id": 200,
            "xg_model": OPENPLAY_XG_MODEL, "score_matches_events": True,
        }],
        "team_match_stats": [
            {"match_id": 7, "team_id": 100, "opponent_id": 200, "goals_for": 2,
             "goals_against": 1, "xg": 1.8, "npxg": 1.2, "shots": 12,
             "shots_on_target": 5, "passes": 400, "passes_completed": 330,
             "tackles": 18, "interceptions": 9, "possession_pct": 0.58},
            {"match_id": 7, "team_id": 200, "opponent_id": 100, "goals_for": 1,
             "goals_against": 2, "xg": 0.8, "npxg": 0.7, "shots": 7,
             "shots_on_target": 2, "passes": 290, "passes_completed": 220,
             "tackles": 20, "interceptions": 11, "possession_pct": 0.42},
        ],
        "player_match_stats": [
            {"match_id": 7, "team_id": 100, "player_id": 1, "is_starter": True,
             "minutes_played": 90, "xg": 0.4, "npxg": 0.4, "shots": 2,
             "shots_on_target": 1, "goals": 1, "xa": 0.2, "key_passes": 2,
             "tackles": 1, "interceptions": 1},
            {"match_id": 7, "team_id": 100, "player_id": 2, "is_starter": False,
             "minutes_played": 30, "xg": 0.1, "npxg": 0.1, "shots": 1,
             "shots_on_target": 0, "goals": 0, "xa": 0.0, "key_passes": 1,
             "tackles": 2, "interceptions": 0},
        ],
        "lineups": [
            {"match_id": 7, "team_id": 100, "player_id": 1, "is_starter": True,
             "played": True, "is_captain_start": True},
            {"match_id": 7, "team_id": 100, "player_id": 2, "is_starter": False,
             "played": True, "is_captain_start": False},
        ],
        "shots": [
            {"match_id": 7, "team_id": 100, "xg": 0.4, "is_shootout": False,
             "is_penalty": False, "is_on_target": True, "is_big_chance": True,
             "is_set_piece": False},
            {"match_id": 7, "team_id": 100, "xg": 0.2, "is_shootout": True,
             "is_penalty": True, "is_on_target": True, "is_big_chance": False,
             "is_set_piece": True},
        ],
        "cards": [
            {"match_id": 7, "team_id": 100, "card": "yellow"},
            {"match_id": 7, "team_id": 100, "card": "red"},
        ],
        "formations": [
            {"match_id": 7, "team_id": 100, "period": 1,
             "start_expanded_minute": 0, "formation": "4231"},
        ],
        "team_crosswalk": {"100": "team-home", "200": "team-away"},
        "competition_crosswalk": {"eng": "competition-eng"},
        "recorded_at_by_match": {"7": RECORDED},
    }


def _build(**overrides):
    args = _inputs()
    args.update(overrides)
    return build_openplay_team_match_features(**args)


def test_openplay_features_keep_canonical_ids_and_xg_model_provenance():
    rows = _build()
    assert len(rows) == 2
    home = next(row for row in rows if row.canonical_team_id == "team-home")
    assert home.canonical_opponent_id == "team-away"
    assert home.canonical_competition_id == "competition-eng"
    assert home.xg_model == OPENPLAY_XG_MODEL
    assert home.metrics["team"]["xg"] == 1.8
    assert "possession_pct" not in home.metrics["team"]
    assert home.metrics["excluded_source_metrics"]["possession_pct"] == (
        "SOURCE_VALUES_VIOLATE_DOCUMENTED_PERCENTAGE_RANGE"
    )
    assert home.metrics["players"]["starters"] == 1
    assert home.metrics["players"]["minutes_played_total"] == 120
    assert home.metrics["lineup"]["squad_size"] == 2
    assert home.metrics["shots"]["shot_xg"] == 0.4
    assert home.metrics["cards"]["red_cards"] == 1
    assert home.metrics["formation_spells"][0]["formation"] == "4231"
    assert home.commercial_use_allowed is False
    assert len(home.feature_sha256) == 64


def test_openplay_postmatch_features_are_not_backdated_before_veltrix_import():
    rows = _build()
    assert eligible_openplay_team_match_features(
        rows, cutoff_at=CUTOFF_BEFORE_IMPORT
    ) == ()
    eligible = eligible_openplay_team_match_features(
        rows, cutoff_at=CUTOFF_AFTER_IMPORT
    )
    assert len(eligible) == 2


def test_unmapped_team_or_competition_is_quarantined_without_guessing():
    args = _inputs()
    args["team_crosswalk"] = {"100": "team-home"}
    assert build_openplay_team_match_features(**args) == ()


def test_duplicate_team_match_stats_fail_closed():
    args = _inputs()
    args["team_match_stats"].append(dict(args["team_match_stats"][0]))
    with pytest.raises(ValueError, match="OPENPLAY_TEAM_MATCH_STATS_DUPLICATE_NATURAL_KEY"):
        build_openplay_team_match_features(**args)


def test_recording_clock_cannot_precede_source_page_save():
    args = _inputs()
    args["recorded_at_by_match"] = {
        "7": datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    }
    with pytest.raises(ValueError, match="OPENPLAY_RECORDED_BEFORE_SOURCE_PAGE_SAVE"):
        build_openplay_team_match_features(**args)


def test_unexpected_xg_model_is_rejected_instead_of_mixed():
    args = _inputs()
    args["matches"][0]["xg_model"] = "another-model"
    with pytest.raises(ValueError, match="OPENPLAY_XG_MODEL_ID_UNEXPECTED"):
        build_openplay_team_match_features(**args)
