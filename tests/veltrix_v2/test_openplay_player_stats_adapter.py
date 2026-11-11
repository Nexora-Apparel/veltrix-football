from veltrix_v2.ingestion.openplay_player_stats import adapt_player_match_row


def sample(**overrides):
    row = {
        "match_id": 101,
        "player_id": 202,
        "team_id": 303,
        "comp": "EPL",
        "season": "2024/25",
        "date": "2024-10-05",
        "minutes_played": 90,
        "goals": 1,
        "assists": 0,
        "xg": 0.71,
        "npxg": 0.71,
        "xa": None,
        "is_starter": True,
        "position": "FW",
    }
    row.update(overrides)
    return row


def test_adapter_preserves_ids_competition_season_and_source_date():
    item = adapt_player_match_row(sample(), xg_model_id="openplay-xg-v1")
    assert item.provider_match_id == "101"
    assert item.provider_player_id == "202"
    assert item.provider_team_id == "303"
    assert item.competition_code == "EPL"
    assert item.season == "2024/25"
    assert item.source_match_date == "2024-10-05"
    assert item.source_release == "data-v0.1.0"


def test_adapter_does_not_invent_utc_timestamps():
    item = adapt_player_match_row(sample(), xg_model_id="openplay-xg-v1")
    assert item.source_match_date == "2024-10-05"
    assert item.source_scraped_at is None
    assert not hasattr(item, "kickoff_utc")
    assert not hasattr(item, "available_at_utc")


def test_xg_model_identity_is_required_and_preserved():
    import pytest
    with pytest.raises(ValueError, match="XG_MODEL_ID_REQUIRED"):
        adapt_player_match_row(sample(), xg_model_id=None)
    item = adapt_player_match_row(sample(), xg_model_id="openplay-model-v1")
    assert item.xg_model_id == "openplay-model-v1"


def test_missing_values_stay_missing():
    row = sample(goals=None, xg=None, npxg=None)
    item = adapt_player_match_row(row, xg_model_id=None)
    assert item.metrics["goals"] is None
    assert item.metrics["xg"] is None


def test_known_issue_match_is_quarantined():
    item = adapt_player_match_row(
        sample(), xg_model_id="openplay-xg-v1",
        known_issue_match_ids=frozenset({"101"}),
    )
    assert item.quality_state == "quarantined_known_match_issue"


def test_unlisted_competition_season_is_quarantined():
    item = adapt_player_match_row(
        sample(), xg_model_id="openplay-xg-v1",
        covered_competition_seasons=frozenset({("LL", "2024/25")}),
    )
    assert item.quality_state == "quarantined_outside_declared_coverage"


def test_invalid_count_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="NON_INTEGER_COUNT"):
        adapt_player_match_row(sample(goals=1.5), xg_model_id="openplay-xg-v1")


def test_row_hash_is_deterministic():
    a = adapt_player_match_row(sample(), xg_model_id="openplay-xg-v1")
    b = adapt_player_match_row(sample(), xg_model_id="openplay-xg-v1")
    assert a.payload_sha256 == b.payload_sha256
    assert len(a.payload_sha256) == 64
