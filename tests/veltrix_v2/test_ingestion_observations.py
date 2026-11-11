from datetime import datetime, timezone

from veltrix_v2.ingestion import build_observation, stable_payload_sha256

T = datetime(2026, 11, 11, 6, tzinfo=timezone.utc)


def test_payload_hash_is_order_independent():
    assert stable_payload_sha256({"home": 1, "away": 0}) == stable_payload_sha256({"away": 0, "home": 1})


def test_build_observation_binds_provenance_and_hash():
    item = build_observation(
        provider="strikerapi", endpoint="list_games", entity_type="fixture",
        provider_entity_id="fx-42", competition_key="EPL", season="2026",
        retrieved_at_utc=T, source_event_time_utc=T, available_at_utc=T,
        schema_version="v1", rights_approval_id="approval-epl-fixtures",
        payload={"game_id": 42, "score": [1, 0]},
        normalized_values={"home_score": 1, "away_score": 0},
    )
    assert item.provider_entity_id == "fx-42"
    assert len(item.payload_sha256) == 64
    assert item.values["home_score"] == 1
