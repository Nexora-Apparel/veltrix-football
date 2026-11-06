"""Explicit, versioned provider-ID mapping before canonical fixture reconciliation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, Sequence

from veltrix_v2.domain.identity import ProviderFixtureIdentity, SquadCategory


class MappingVerificationState(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    REVOKED = "REVOKED"


class MappingResolutionStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNVERIFIED = "UNVERIFIED"
    SQUAD_CATEGORY_MISMATCH = "SQUAD_CATEGORY_MISMATCH"
    INVALID_MAPPING = "INVALID_MAPPING"


@dataclass(frozen=True, slots=True)
class ProviderFixtureSourceIdentity:
    provider: str
    source_id: str
    provider_fixture_id: str
    provider_competition_id: str
    provider_home_team_id: str
    provider_away_team_id: str
    squad_category: SquadCategory | None
    kickoff_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ProviderCompetitionMapping:
    provider: str
    source_id: str
    provider_competition_id: str
    canonical_competition_id: str
    squad_category: SquadCategory
    state: MappingVerificationState
    mapping_version: str
    evidence_ref: str
    valid_from_utc: datetime
    valid_to_utc: datetime | None = None
    verified_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        required = (
            self.provider, self.source_id, self.provider_competition_id,
            self.canonical_competition_id, self.mapping_version, self.evidence_ref,
        )
        if any(not value or not value.strip() for value in required):
            raise ValueError("competition mapping identity and evidence fields are required")
        start = _utc(self.valid_from_utc, "valid_from_utc")
        end = _utc(self.valid_to_utc, "valid_to_utc") if self.valid_to_utc else None
        if end is not None and end <= start:
            raise ValueError("valid_to_utc must be after valid_from_utc")
        if self.state is MappingVerificationState.VERIFIED:
            if self.verified_at_utc is None:
                raise ValueError("verified mappings require verified_at_utc")
            _utc(self.verified_at_utc, "verified_at_utc")


@dataclass(frozen=True, slots=True)
class ProviderTeamMapping:
    provider: str
    source_id: str
    provider_team_id: str
    canonical_team_id: str
    squad_category: SquadCategory
    state: MappingVerificationState
    mapping_version: str
    evidence_ref: str
    valid_from_utc: datetime
    valid_to_utc: datetime | None = None
    verified_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        required = (
            self.provider, self.source_id, self.provider_team_id,
            self.canonical_team_id, self.mapping_version, self.evidence_ref,
        )
        if any(not value or not value.strip() for value in required):
            raise ValueError("team mapping identity and evidence fields are required")
        start = _utc(self.valid_from_utc, "valid_from_utc")
        end = _utc(self.valid_to_utc, "valid_to_utc") if self.valid_to_utc else None
        if end is not None and end <= start:
            raise ValueError("valid_to_utc must be after valid_from_utc")
        if self.state is MappingVerificationState.VERIFIED:
            if self.verified_at_utc is None:
                raise ValueError("verified mappings require verified_at_utc")
            _utc(self.verified_at_utc, "verified_at_utc")


@dataclass(frozen=True, slots=True)
class ResolvedProviderFixture:
    status: MappingResolutionStatus
    source_identity: ProviderFixtureSourceIdentity
    canonical_identity: ProviderFixtureIdentity | None
    reason_code: str
    evidence_refs: tuple[str, ...]


class IdentityMappingRepository(Protocol):
    def get_competition_mappings(
        self, *, provider: str, source_id: str, provider_competition_id: str,
    ) -> Sequence[ProviderCompetitionMapping]: ...

    def get_team_mappings(
        self, *, provider: str, source_id: str, provider_team_id: str,
    ) -> Sequence[ProviderTeamMapping]: ...


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _active(mapping, fixture_kickoff_utc: datetime) -> bool:
    start = _utc(mapping.valid_from_utc, "valid_from_utc")
    end = _utc(mapping.valid_to_utc, "valid_to_utc") if mapping.valid_to_utc else None
    return start <= fixture_kickoff_utc and (
        end is None or fixture_kickoff_utc < end
    )


def choose_verified_mapping(
    mappings,
    fixture_kickoff_utc: datetime,
    evaluated_at_utc: datetime,
    expected_fields: dict[str, str],
):
    for mapping in mappings:
        for field, expected in expected_fields.items():
            if getattr(mapping, field) != expected:
                return (
                    MappingResolutionStatus.INVALID_MAPPING,
                    None,
                    "MAPPING_SOURCE_IDENTITY_MISMATCH",
                )
    active = [
        mapping for mapping in mappings
        if _active(mapping, fixture_kickoff_utc)
    ]
    if not active:
        return MappingResolutionStatus.UNRESOLVED, None, "VERIFIED_MAPPING_NOT_FOUND"
    verified = [
        mapping for mapping in active
        if mapping.state is MappingVerificationState.VERIFIED
        and bool(mapping.evidence_ref.strip())
        and bool(mapping.mapping_version.strip())
        and mapping.verified_at_utc is not None
        and _utc(mapping.verified_at_utc, "verified_at_utc") <= evaluated_at_utc
    ]
    if len(verified) > 1:
        return MappingResolutionStatus.AMBIGUOUS, None, "MULTIPLE_ACTIVE_VERIFIED_MAPPINGS"
    if len(verified) == 0:
        if any(
            mapping.state is MappingVerificationState.UNVERIFIED
            or (
                mapping.state is MappingVerificationState.VERIFIED
                and (
                    mapping.verified_at_utc is None
                    or _utc(mapping.verified_at_utc, "verified_at_utc") > evaluated_at_utc
                )
            )
            for mapping in active
        ):
            return MappingResolutionStatus.UNVERIFIED, None, "MAPPING_NOT_VERIFIED"
        return MappingResolutionStatus.UNRESOLVED, None, "NO_ACTIVE_VERIFIED_MAPPING"
    return MappingResolutionStatus.VERIFIED, verified[0], "MAPPING_VERIFIED"


def resolve_provider_fixture(
    source: ProviderFixtureSourceIdentity,
    repository: IdentityMappingRepository,
    *,
    evaluated_at_utc: datetime,
) -> ResolvedProviderFixture:
    """Resolve exact provider IDs through verified mappings; never fuzzy-match names."""
    required = (
        source.provider, source.source_id, source.provider_fixture_id,
        source.provider_competition_id, source.provider_home_team_id,
        source.provider_away_team_id,
    )
    if any(not value or not value.strip() for value in required):
        raise ValueError("provider/source/fixture/competition/home/away IDs are required")
    if source.provider_home_team_id == source.provider_away_team_id:
        raise ValueError("provider home and away team IDs must differ")
    kickoff = _utc(source.kickoff_at_utc, "kickoff_at_utc")
    evaluated = _utc(evaluated_at_utc, "evaluated_at_utc")

    competition_rows = repository.get_competition_mappings(
        provider=source.provider, source_id=source.source_id,
        provider_competition_id=source.provider_competition_id,
    )
    status, competition, reason = choose_verified_mapping(
        competition_rows, kickoff, evaluated,
        {
            "provider": source.provider,
            "source_id": source.source_id,
            "provider_competition_id": source.provider_competition_id,
        },
    )
    if status is not MappingResolutionStatus.VERIFIED:
        return ResolvedProviderFixture(
            status, source, None, f"COMPETITION_{reason}", ()
        )

    team_results = []
    for provider_team_id in (source.provider_home_team_id, source.provider_away_team_id):
        rows = repository.get_team_mappings(
            provider=source.provider, source_id=source.source_id,
            provider_team_id=provider_team_id,
        )
        team_results.append(_choose_mapping(
            rows, kickoff, evaluated,
            {
                "provider": source.provider,
                "source_id": source.source_id,
                "provider_team_id": provider_team_id,
            },
        ))

    for status, mapping, reason in team_results:
        if status is not MappingResolutionStatus.VERIFIED:
            return ResolvedProviderFixture(
                status, source, None, f"TEAM_{reason}", (competition.evidence_ref,)
            )

    home, away = team_results[0][1], team_results[1][1]
    mappings = (competition, home, away)
    if (
        source.squad_category is not None
        and competition.squad_category is not source.squad_category
    ) or any(
        mapping.squad_category is not competition.squad_category
        for mapping in (home, away)
    ):
        return ResolvedProviderFixture(
            MappingResolutionStatus.SQUAD_CATEGORY_MISMATCH,
            source, None, "SQUAD_CATEGORY_MAPPING_CONFLICT",
            tuple(mapping.evidence_ref for mapping in mappings),
        )
    if home.canonical_team_id == away.canonical_team_id:
        return ResolvedProviderFixture(
            MappingResolutionStatus.INVALID_MAPPING,
            source, None, "HOME_AWAY_CANONICAL_TEAM_COLLISION",
            tuple(mapping.evidence_ref for mapping in mappings),
        )

    canonical = ProviderFixtureIdentity(
        provider=source.provider,
        provider_fixture_id=source.provider_fixture_id,
        provider_competition_id=source.provider_competition_id,
        canonical_competition_id=competition.canonical_competition_id,
        squad_category=competition.squad_category,
        canonical_home_team_id=home.canonical_team_id,
        canonical_away_team_id=away.canonical_team_id,
        kickoff_at_utc=kickoff,
    )
    return ResolvedProviderFixture(
        MappingResolutionStatus.VERIFIED,
        source,
        canonical,
        "PROVIDER_IDS_RESOLVED",
        tuple(mapping.evidence_ref for mapping in mappings),
    )
