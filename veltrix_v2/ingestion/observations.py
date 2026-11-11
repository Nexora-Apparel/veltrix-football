"""Provider-neutral ingestion primitives for immutable observations."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Mapping

from veltrix_v2.contracts import ProviderObservation


def stable_payload_sha256(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_observation(
    *,
    provider: str,
    endpoint: str,
    entity_type: str,
    provider_entity_id: str,
    competition_key: str,
    season: str,
    retrieved_at_utc: datetime,
    source_event_time_utc: datetime,
    available_at_utc: datetime,
    schema_version: str,
    rights_approval_id: str,
    payload: Mapping[str, object],
    normalized_values: Mapping[str, object],
) -> ProviderObservation:
    """Create a content-addressed observation; never overwrites prior versions."""
    return ProviderObservation(
        provider=provider,
        endpoint=endpoint,
        entity_type=entity_type,
        provider_entity_id=provider_entity_id,
        competition_key=competition_key,
        season=season,
        retrieved_at_utc=retrieved_at_utc,
        source_event_time_utc=source_event_time_utc,
        available_at_utc=available_at_utc,
        payload_sha256=stable_payload_sha256(payload),
        schema_version=schema_version,
        rights_approval_id=rights_approval_id,
        values=dict(normalized_values),
    )
