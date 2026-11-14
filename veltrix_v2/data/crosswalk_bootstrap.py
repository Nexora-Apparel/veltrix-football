"""Evidence-backed, read-only bootstrap of 5Dollar canonical crosswalks.

Mappings are derived only from exact provider payloads already linked to
canonical fixture rows. Every mapping is checked for uniqueness and hashed
with its supporting observation evidence. The registry is valid only from
the verification instant forward; it is never backdated.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from types import MappingProxyType
import re
from typing import Iterable, Mapping

from veltrix_v2.data.provider_evidence_capture import ResolvedFixtureCrosswalk
from veltrix_v2.data.contracts import FixtureStatus, HistoricalFixture
from veltrix_v2.models.engine import PredictionTarget


_HASH = re.compile(r"^[0-9a-f]{64}$")
_PROVIDER = "5DollarFootballAPI"
_SOURCE = "5dollarfootballapi"


def _canonical_hash(value: object) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _id(value: object, field: str) -> str:
    if isinstance(value, bool):
        raise ValueError(f"CROSSWALK_{field}_INVALID")
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.strip().isdigit() and int(value.strip()) > 0:
        return str(int(value.strip()))
    raise ValueError(f"CROSSWALK_{field}_INVALID")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"CROSSWALK_{field}_MISSING")
    return value.strip()


@dataclass(frozen=True, slots=True)
class EntityCrosswalk:
    provider_entity_id: str
    canonical_entity_id: str
    mapping_version: int
    valid_from: datetime
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class CrosswalkRegistry:
    provider: str
    source_id: str
    verified_at: datetime
    fixture_crosswalks: Mapping[str, ResolvedFixtureCrosswalk]
    team_crosswalks: Mapping[str, EntityCrosswalk]
    competition_crosswalks: Mapping[str, EntityCrosswalk]

    def to_prediction_target(self, fixture: HistoricalFixture) -> PredictionTarget:
        if not isinstance(fixture, HistoricalFixture):
            raise TypeError("HISTORICAL_FIXTURE_REQUIRED")
        if (fixture.provider, fixture.source_id) != (self.provider, self.source_id):
            raise ValueError("CROSSWALK_TARGET_PROVIDER_MISMATCH")
        if fixture.status is not FixtureStatus.SCHEDULED:
            raise ValueError("CROSSWALK_TARGET_MUST_BE_SCHEDULED")
        if fixture.retrieved_at_utc < self.verified_at:
            raise ValueError("CROSSWALK_TARGET_PRECEDES_VERIFICATION")
        if fixture.kickoff_at_utc <= fixture.retrieved_at_utc:
            raise ValueError("CROSSWALK_TARGET_NOT_FUTURE")
        competition = self.competition_crosswalks.get(fixture.provider_competition_id)
        home = self.team_crosswalks.get(fixture.provider_home_team_id)
        away = self.team_crosswalks.get(fixture.provider_away_team_id)
        if competition is None:
            raise ValueError("CROSSWALK_COMPETITION_NOT_FOUND")
        if home is None or away is None:
            raise ValueError("CROSSWALK_TEAM_NOT_FOUND")
        if home.canonical_entity_id == away.canonical_entity_id:
            raise ValueError("CROSSWALK_TARGET_TEAM_COLLISION")
        return PredictionTarget(
            fixture_id=f"{fixture.source_id}:{fixture.provider_fixture_id}",
            competition_id=competition.canonical_entity_id,
            home_team_id=home.canonical_entity_id,
            away_team_id=away.canonical_entity_id,
            kickoff_at=fixture.kickoff_at_utc,
            provider=fixture.provider,
            source_id=fixture.source_id,
            source_fixture_id=fixture.provider_fixture_id,
            retrieved_at=fixture.retrieved_at_utc,
            payload_sha256=fixture.payload_sha256,
            rights_approval_id=fixture.rights_approval_id,
            home_team_name=fixture.home_team_name,
            away_team_name=fixture.away_team_name,
        )

    def summary(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "source_id": self.source_id,
            "verified_at": self.verified_at.isoformat(),
            "fixture_crosswalks": len(self.fixture_crosswalks),
            "team_crosswalks": len(self.team_crosswalks),
            "competition_crosswalks": len(self.competition_crosswalks),
            "validity": "VERIFIED_FROM_VERIFIED_AT_FORWARD_ONLY",
        }


def build_fivedollar_crosswalk_registry(
    rows: Iterable[Mapping[str, object]], *, verified_at: datetime
) -> CrosswalkRegistry:
    """Build deterministic mappings from exact linked provider observations."""
    if not isinstance(verified_at, datetime) or verified_at.tzinfo is None or verified_at.utcoffset() is None:
        raise ValueError("CROSSWALK_VERIFICATION_TIME_MUST_BE_AWARE")

    source_rows = tuple(rows)
    if not source_rows:
        raise ValueError("CROSSWALK_SOURCE_ROWS_EMPTY")

    fixture_crosswalks: dict[str, ResolvedFixtureCrosswalk] = {}
    team_support: dict[str, dict[str, list[dict[str, str]]]] = {}
    competition_support: dict[str, dict[str, list[dict[str, str]]]] = {}

    for row in source_rows:
        provider = _text(row.get("provider"), "PROVIDER")
        source_id = _text(row.get("source_id"), "SOURCE_ID")
        if (provider, source_id) != (_PROVIDER, _SOURCE):
            raise ValueError("CROSSWALK_PROVIDER_NOT_APPROVED")
        canonical_fixture = _text(row.get("canonical_fixture_id"), "CANONICAL_FIXTURE_ID")
        canonical_competition = _text(row.get("canonical_competition_id"), "CANONICAL_COMPETITION_ID")
        canonical_home = _text(row.get("canonical_home_team_id"), "CANONICAL_HOME_TEAM_ID")
        canonical_away = _text(row.get("canonical_away_team_id"), "CANONICAL_AWAY_TEAM_ID")
        if canonical_home == canonical_away:
            raise ValueError("CROSSWALK_CANONICAL_TEAM_COLLISION")

        payload = row.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("CROSSWALK_PAYLOAD_INVALID")
        payload_hash = _text(row.get("payload_sha256"), "PAYLOAD_HASH").lower()
        if not _HASH.fullmatch(payload_hash) or _canonical_hash(payload) != payload_hash:
            raise ValueError("CROSSWALK_PAYLOAD_HASH_MISMATCH")

        provider_fixture = _id(payload.get("id"), "PROVIDER_FIXTURE_ID")
        league = payload.get("league")
        teams = payload.get("teams")
        if not isinstance(league, Mapping) or not isinstance(teams, Mapping):
            raise ValueError("CROSSWALK_PAYLOAD_IDENTITY_MISSING")
        provider_competition = _id(league.get("id"), "PROVIDER_COMPETITION_ID")
        home_row, away_row = teams.get("home"), teams.get("away")
        if not isinstance(home_row, Mapping) or not isinstance(away_row, Mapping):
            raise ValueError("CROSSWALK_PROVIDER_TEAMS_MISSING")
        provider_home = _id(home_row.get("id"), "PROVIDER_HOME_TEAM_ID")
        provider_away = _id(away_row.get("id"), "PROVIDER_AWAY_TEAM_ID")
        if provider_home == provider_away:
            raise ValueError("CROSSWALK_PROVIDER_TEAM_COLLISION")

        observation_id_value = row.get("source_observation_id")
        if observation_id_value is None:
            raise ValueError("CROSSWALK_SOURCE_OBSERVATION_ID_MISSING")
        observation_id = _text(str(observation_id_value), "SOURCE_OBSERVATION_ID")
        evidence_item = {
            "source_observation_id": observation_id,
            "payload_sha256": payload_hash,
        }
        fixture_evidence = {
            "schema": "veltrix-fivedollar-fixture-crosswalk-v1",
            "provider": provider,
            "source_id": source_id,
            "provider_fixture_id": provider_fixture,
            "provider_competition_id": provider_competition,
            "provider_home_team_id": provider_home,
            "provider_away_team_id": provider_away,
            "canonical_fixture_id": canonical_fixture,
            "canonical_competition_id": canonical_competition,
            "canonical_home_team_id": canonical_home,
            "canonical_away_team_id": canonical_away,
            "supporting_observation": evidence_item,
            "verified_at": verified_at.isoformat(),
        }
        if provider_fixture in fixture_crosswalks:
            raise ValueError("CROSSWALK_PROVIDER_FIXTURE_DUPLICATE")
        fixture_crosswalks[provider_fixture] = ResolvedFixtureCrosswalk(
            provider=provider,
            source_id=source_id,
            provider_fixture_id=provider_fixture,
            provider_competition_id=provider_competition,
            provider_home_team_id=provider_home,
            provider_away_team_id=provider_away,
            canonical_fixture_id=canonical_fixture,
            canonical_competition_id=canonical_competition,
            canonical_home_team_id=canonical_home,
            canonical_away_team_id=canonical_away,
            mapping_version=1,
            mapping_status="RESOLVED",
            valid_from=verified_at,
            evidence_sha256=_canonical_hash(fixture_evidence),
        )

        team_support.setdefault(provider_home, {}).setdefault(canonical_home, []).append(evidence_item)
        team_support.setdefault(provider_away, {}).setdefault(canonical_away, []).append(evidence_item)
        competition_support.setdefault(provider_competition, {}).setdefault(canonical_competition, []).append(evidence_item)

    if any(len(mapping) != 1 for mapping in team_support.values()):
        raise ValueError("CROSSWALK_TEAM_MAPPING_AMBIGUOUS")
    if any(len(mapping) != 1 for mapping in competition_support.values()):
        raise ValueError("CROSSWALK_COMPETITION_MAPPING_AMBIGUOUS")

    team_crosswalks: dict[str, EntityCrosswalk] = {}
    for provider_id, mappings in team_support.items():
        canonical_id, evidence_rows = next(iter(mappings.items()))
        team_crosswalks[provider_id] = EntityCrosswalk(
            provider_entity_id=provider_id,
            canonical_entity_id=canonical_id,
            mapping_version=1,
            valid_from=verified_at,
            evidence_sha256=_canonical_hash({
                "schema": "veltrix-fivedollar-team-crosswalk-v1",
                "provider": _PROVIDER,
                "source_id": _SOURCE,
                "provider_team_id": provider_id,
                "canonical_team_id": canonical_id,
                "supporting_observations": sorted(
                    evidence_rows, key=lambda item: (item["source_observation_id"], item["payload_sha256"])
                ),
                "verified_at": verified_at.isoformat(),
            }),
        )

    competition_crosswalks: dict[str, EntityCrosswalk] = {}
    for provider_id, mappings in competition_support.items():
        canonical_id, evidence_rows = next(iter(mappings.items()))
        competition_crosswalks[provider_id] = EntityCrosswalk(
            provider_entity_id=provider_id,
            canonical_entity_id=canonical_id,
            mapping_version=1,
            valid_from=verified_at,
            evidence_sha256=_canonical_hash({
                "schema": "veltrix-fivedollar-competition-crosswalk-v1",
                "provider": _PROVIDER,
                "source_id": _SOURCE,
                "provider_competition_id": provider_id,
                "canonical_competition_id": canonical_id,
                "supporting_observations": sorted(
                    evidence_rows, key=lambda item: (item["source_observation_id"], item["payload_sha256"])
                ),
                "verified_at": verified_at.isoformat(),
            }),
        )

    return CrosswalkRegistry(
        provider=_PROVIDER,
        source_id=_SOURCE,
        verified_at=verified_at,
        fixture_crosswalks=MappingProxyType(fixture_crosswalks),
        team_crosswalks=MappingProxyType(team_crosswalks),
        competition_crosswalks=MappingProxyType(competition_crosswalks),
    )
