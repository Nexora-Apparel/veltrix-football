from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.contracts import FixtureIdentity, ForecastCutoff, ProviderObservation


NOW = datetime(2026, 11, 11, 7, tzinfo=timezone.utc)
HASH = "a" * 64


def observation(**overrides):
    values = dict(
        provider="strikerapi", endpoint="list_games", entity_type="fixture",
        provider_entity_id="fx-1", competition_key="EPL", season="2026",
        retrieved_at_utc=NOW, source_event_time_utc=NOW,
        available_at_utc=NOW, payload_sha256=HASH, schema_version="1",
        rights_approval_id="strikerapi-free-fixtures-epl", values={"status": "final"},
    )
    values.update(overrides)
    return ProviderObservation(**values)


def test_observation_is_immutable_and_normalizes_utc():
    item = observation(retrieved_at_utc=NOW.astimezone(timezone(timedelta(hours=1))))
    assert item.retrieved_at_utc == NOW
    with pytest.raises((AttributeError, TypeError)):
        item.provider = "other"


def test_rejects_naive_timestamps():
    with pytest.raises(ValueError, match="timezone-aware"):
        observation(available_at_utc=datetime(2026, 11, 11, 7))


def test_rejects_invalid_payload_hash():
    with pytest.raises(ValueError, match="SHA-256"):
        observation(payload_sha256="not-a-hash")


def test_point_in_time_cutoff_excludes_late_observation():
    later = NOW + timedelta(seconds=1)
    item = observation(retrieved_at_utc=later, available_at_utc=later)
    assert not ForecastCutoff(NOW).permits(item)
    assert ForecastCutoff(NOW + timedelta(seconds=1)).permits(item)


def test_fixture_identity_requires_distinct_teams_and_aware_kickoff():
    with pytest.raises(ValueError, match="must differ"):
        FixtureIdentity("strikerapi", "1", "EPL", "2026", "7", "7", NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        FixtureIdentity("strikerapi", "1", "EPL", "2026", "7", "8", datetime(2026, 11, 11))
