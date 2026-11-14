"""Read-only adapter from persisted evidence rows to coverage audit inputs.

The caller supplies rows from a read-only query. This module opens no database
connection and never upgrades incomplete persisted evidence into eligibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Iterable, Mapping

from veltrix_v2.data.competition_coverage import CoverageFixture, DomainEvidence
from veltrix_v2.data.provider_registry import DataDomain


_DATA_TYPES = {
    "fixture_result": DataDomain.RESULTS,
    "result": DataDomain.RESULTS,
    "fixture": DataDomain.FIXTURES,
    "team_form": DataDomain.TEAM_FORM,
    "team_strength": DataDomain.TEAM_STRENGTH,
    "rest_days": DataDomain.REST_DAYS,
    "expected_goals": DataDomain.EXPECTED_GOALS,
    "lineup": DataDomain.LINEUPS,
    "injury": DataDomain.INJURIES,
    "player_stat": DataDomain.PLAYER_STATS,
    "odds_1x2": DataDomain.ODDS_1X2,
    "odds_totals": DataDomain.ODDS_TOTALS,
    "odds_btts": DataDomain.ODDS_BTTS,
}


@dataclass(frozen=True, slots=True)
class PersistedCoverageInputs:
    fixtures: tuple[CoverageFixture, ...]
    evidence: tuple[DomainEvidence, ...]
    rejected_fixture_rows: int
    rejected_observation_rows: int
    unsupported_data_types: tuple[str, ...]


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _payload(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return None
        return decoded if isinstance(decoded, Mapping) else None
    return None


def adapt_persisted_coverage_rows(
    fixture_rows: Iterable[Mapping[str, object]],
    observation_rows: Iterable[Mapping[str, object]],
) -> PersistedCoverageInputs:
    """Normalize aliased, read-only SQL rows without inferring missing fields.

    Fixture query columns must be aliased as fixture_id, competition_id and
    kickoff_at. Observation rows use source_observations columns plus JSONB
    payload. The payload must explicitly contain rights_approved,
    rights_evaluated_at and rights_evidence_sha256.
    """
    fixtures: list[CoverageFixture] = []
    rejected_fixtures = 0
    for row in tuple(fixture_rows):
        if not isinstance(row, Mapping):
            rejected_fixtures += 1
            continue
        kickoff = _datetime(row.get("kickoff_at"))
        fixture_id = row.get("fixture_id")
        competition_id = row.get("competition_id")
        if (
            not isinstance(fixture_id, str) or not fixture_id.strip()
            or not isinstance(competition_id, str) or not competition_id.strip()
            or kickoff is None
        ):
            rejected_fixtures += 1
            continue
        fixtures.append(CoverageFixture(fixture_id, competition_id, kickoff))

    evidence: list[DomainEvidence] = []
    rejected_observations = 0
    unsupported: set[str] = set()
    for row in tuple(observation_rows):
        if not isinstance(row, Mapping):
            rejected_observations += 1
            continue
        data_type = row.get("data_type")
        domain = _DATA_TYPES.get(data_type) if isinstance(data_type, str) else None
        if domain is None:
            unsupported.add(data_type if isinstance(data_type, str) else "UNKNOWN")
            continue
        payload = _payload(row.get("payload"))
        if payload is None:
            rejected_observations += 1
            continue
        available_at = _datetime(row.get("available_at"))
        recorded_at = _datetime(row.get("recorded_at"))
        rights_evaluated_at = _datetime(payload.get("rights_evaluated_at"))
        fixture_id = row.get("fixture_id", payload.get("fixture_id"))
        competition_id = row.get("competition_id", payload.get("competition_id"))
        point_in_time = row.get("point_in_time_certifiable", payload.get("point_in_time_certifiable"))
        values = (
            fixture_id, competition_id,
            row.get("provider"), row.get("source_id"),
            row.get("payload_sha256"), row.get("rights_approval_id"),
            payload.get("rights_evidence_sha256"),
        )
        if (
            available_at is None or recorded_at is None or rights_evaluated_at is None
            or not all(isinstance(value, str) and value.strip() for value in values)
            or type(payload.get("rights_approved")) is not bool
            or type(point_in_time) is not bool
        ):
            rejected_observations += 1
            continue
        evidence.append(DomainEvidence(
            fixture_id=fixture_id,
            competition_id=competition_id,
            domain=domain,
            provider=row["provider"],
            source_id=row["source_id"],
            available_at=available_at,
            recorded_at=recorded_at,
            payload_sha256=row["payload_sha256"],
            rights_approved=payload["rights_approved"],
            rights_approval_id=row["rights_approval_id"],
            rights_evidence_sha256=payload["rights_evidence_sha256"],
            rights_evaluated_at=rights_evaluated_at,
            point_in_time_certifiable=point_in_time,
        ))

    return PersistedCoverageInputs(
        fixtures=tuple(fixtures),
        evidence=tuple(evidence),
        rejected_fixture_rows=rejected_fixtures,
        rejected_observation_rows=rejected_observations,
        unsupported_data_types=tuple(sorted(unsupported)),
    )
