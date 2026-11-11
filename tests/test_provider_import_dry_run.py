from datetime import datetime, timezone

from scripts.provider_import_dry_run import (
    assert_isolated_database_target,
    compare_existing,
    inspect_rows,
)


def game(game_id="fx-1", home_id="h1", away_id="a1", home_score=2, away_score=1,
         kickoff="2026-08-01T17:00:00Z"):
    return {
        "game_id": game_id,
        "date": "2026-08-01",
        "starts_at": kickoff,
        "status": "final",
        "home": {"team_id": home_id, "name": "Home Club", "score": home_score},
        "away": {"team_id": away_id, "name": "Away Club", "score": away_score},
    }


def test_provider_record_carries_hash_scope_and_utc_timestamp():
    result = inspect_rows([game()], "soccer", "strikerapi-free-fixtures-epl")
    assert result["records_normalized"] == 1
    row = result["records"][0]
    assert len(row["payload_sha256"]) == 64
    assert row["rights_approval_id"] == "strikerapi-free-fixtures-epl"
    assert row["kickoff_utc"] == "2026-08-01T17:00:00+00:00"


def test_duplicate_provider_ids_are_quarantined():
    result = inspect_rows([game(), game()], "soccer", "approval")
    assert result["duplicate_provider_ids"] == 1
    assert any(x["kind"] == "duplicate_provider_fixture_id" for x in result["issues"])


def test_duplicate_team_identity_is_rejected():
    result = inspect_rows([game(home_id="same", away_id="same")], "soccer", "approval")
    assert any(x["kind"] == "identity_collision" for x in result["issues"])


def test_timezone_naive_kickoff_is_rejected():
    result = inspect_rows([game(kickoff="2026-08-01T17:00:00")], "soccer", "approval")
    assert result["records_normalized"] == 0
    assert any(x["reason"] == "timezone_missing_from_kickoff_timestamp"
               for x in result["issues"])


def test_existing_provider_id_with_different_score_is_a_conflict():
    candidate = inspect_rows([game()], "soccer", "approval")["records"][0]
    existing = {
        ("strikerapi", "fx-1"): {
            "kickoff_at": datetime(2026, 8, 1, 17, tzinfo=timezone.utc),
            "competition_provider": "strikerapi",
            "provider_competition_id": "soccer",
            "status": "FINISHED",
            "home_provider_team_id": "h1",
            "away_provider_team_id": "a1",
            "home_score": 1,
            "away_score": 1,
        }
    }
    conflicts = compare_existing([candidate], existing)
    assert [x["kind"] for x in conflicts] == ["provider_id_score_conflict"]



def test_dry_run_database_target_accepts_only_isolated_neon_host():
    dsn = "postgresql://user:pass@ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech/veltrix-football"
    assert assert_isolated_database_target(dsn) == "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"


def test_dry_run_database_target_rejects_production_or_unknown_host():
    import pytest

    with pytest.raises(RuntimeError, match="isolated Neon branch"):
        assert_isolated_database_target(
            "postgresql://user:pass@production-main.neon.tech/veltrix-football"
        )
