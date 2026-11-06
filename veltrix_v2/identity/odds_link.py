"""Exact, verified alias linkage for odds feeds that lack stable team IDs."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Sequence

from veltrix_v2.domain.identity import CanonicalFixtureIdentity, SquadCategory
from veltrix_v2.identity.registry import (
    MappingResolutionStatus,
    MappingVerificationState,
    ProviderCompetitionMapping,
    _choose_mapping,
)


class OddsFixtureLinkStatus(StrEnum):
    MATCHED = "MATCHED"
    COMPETITION_UNRESOLVED = "COMPETITION_UNRESOLVED"
    COMPETITION_AMBIGUOUS = "COMPETITION_AMBIGUOUS"
    TEAM_ALIAS_UNRESOLVED = "TEAM_ALIAS_UNRESOLVED"
    TEAM_ALIAS_AMBIGUOUS = "TEAM_ALIAS_AMBIGUOUS"
    SQUAD_CATEGORY_MISMATCH = "SQUAD_CATEGORY_MISMATCH"
    FIXTURE_UNRESOLVED = "FIXTURE_UNRESOLVED"
    FIXTURE_AMBIGUOUS = "FIXTURE_AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class ProviderOddsEventIdentity:
    provider: str
    source_id: str
    provider_event_id: str
    provider_competition_id: str
    home_team_name: str
    away_team_name: str
    kickoff_at_utc: datetime


@dataclass(frozen=True, slots=True)
class VerifiedTeamNameAlias:
    provider: str
    source_id: str
    normalized_name: str
    canonical_team_id: str
    squad_category: SquadCategory
    state: MappingVerificationState
    mapping_version: str
    evidence_ref: str
    valid_from_utc: datetime
    valid_to_utc: datetime | None
    verified_at_utc: datetime | None


@dataclass(frozen=True, slots=True)
class OddsFixtureLinkDecision:
    status: OddsFixtureLinkStatus
    provider_event_id: str
    canonical_fixture_id: str | None
    reason_code: str
    evidence_refs: tuple[str, ...]
    kickoff_delta_seconds: int | None


def normalize_team_name_alias_key(value: str) -> str:
    """Deterministic exact-key normalization; deliberately performs no fuzzy matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    characters = [character if character.isalnum() else " " for character in normalized]
    return " ".join("".join(characters).split())


def _select_alias(
    aliases: Sequence[VerifiedTeamNameAlias],
    *,
    provider: str,
    source_id: str,
    normalized_name: str,
    kickoff_at_utc: datetime,
    evaluated_at_utc: datetime,
):
    for alias in aliases:
        if (
            alias.provider != provider
            or alias.source_id != source_id
            or alias.normalized_name != normalized_name
        ):
            return "INVALID", None
    active = []
    for alias in aliases:
        start = alias.valid_from_utc
        end = alias.valid_to_utc
        if start.tzinfo is None or start.utcoffset() is None:
            raise ValueError("alias valid_from_utc must be timezone-aware")
        if end is not None and (end.tzinfo is None or end.utcoffset() is None):
            raise ValueError("alias valid_to_utc must be timezone-aware")
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc) if end else None
        if start_utc <= kickoff_at_utc and (end_utc is None or kickoff_at_utc < end_utc):
            active.append(alias)
    verified = []
    for alias in active:
        if alias.state is not MappingVerificationState.VERIFIED:
            continue
        if not alias.evidence_ref.strip() or not alias.mapping_version.strip():
            continue
        if alias.verified_at_utc is None:
            continue
        if alias.verified_at_utc.tzinfo is None or alias.verified_at_utc.utcoffset() is None:
            raise ValueError("alias verified_at_utc must be timezone-aware")
        if alias.verified_at_utc.astimezone(timezone.utc) <= evaluated_at_utc:
            verified.append(alias)
    if len(verified) > 1:
        return "AMBIGUOUS", None
    if len(verified) == 1:
        return "VERIFIED", verified[0]
    if active:
        return "UNVERIFIED", None
    return "UNRESOLVED", None


def resolve_odds_event(
    event: ProviderOddsEventIdentity,
    competition_mappings: Sequence[ProviderCompetitionMapping],
    home_aliases: Sequence[VerifiedTeamNameAlias],
    away_aliases: Sequence[VerifiedTeamNameAlias],
    candidate_fixtures: Sequence[CanonicalFixtureIdentity],
    *,
    evaluated_at_utc: datetime,
    kickoff_tolerance_minutes: int = 15,
) -> OddsFixtureLinkDecision:
    """Link a supplemental odds event to an existing canonical fixture by exact aliases."""
    required = (
        event.provider, event.source_id, event.provider_event_id,
        event.provider_competition_id, event.home_team_name, event.away_team_name,
    )
    if any(not value or not value.strip() for value in required):
        raise ValueError("odds event provider, source, event, competition and team names are required")
    if kickoff_tolerance_minutes < 0:
        raise ValueError("kickoff_tolerance_minutes cannot be negative")
    if event.kickoff_at_utc.tzinfo is None or event.kickoff_at_utc.utcoffset() is None:
        raise ValueError("odds event kickoff must be timezone-aware")
    if evaluated_at_utc.tzinfo is None or evaluated_at_utc.utcoffset() is None:
        raise ValueError("evaluated_at_utc must be timezone-aware")
    kickoff = event.kickoff_at_utc.astimezone(timezone.utc)
    evaluated = evaluated_at_utc.astimezone(timezone.utc)

    status, competition, reason = _choose_mapping(
        competition_mappings, kickoff, evaluated,
        {
            "provider": event.provider,
            "source_id": event.source_id,
            "provider_competition_id": event.provider_competition_id,
        },
    )
    if status is not MappingResolutionStatus.VERIFIED:
        link_status = (
            OddsFixtureLinkStatus.COMPETITION_AMBIGUOUS
            if status is MappingResolutionStatus.AMBIGUOUS
            else OddsFixtureLinkStatus.COMPETITION_UNRESOLVED
        )
        return OddsFixtureLinkDecision(
            link_status, event.provider_event_id, None,
            f"COMPETITION_{reason}", (), None,
        )

    home_key = normalize_team_name_alias_key(event.home_team_name)
    away_key = normalize_team_name_alias_key(event.away_team_name)
    home_status, home = _select_alias(
        home_aliases, provider=event.provider, source_id=event.source_id,
        normalized_name=home_key, kickoff_at_utc=kickoff,
        evaluated_at_utc=evaluated,
    )
    away_status, away = _select_alias(
        away_aliases, provider=event.provider, source_id=event.source_id,
        normalized_name=away_key, kickoff_at_utc=kickoff,
        evaluated_at_utc=evaluated,
    )
    if home_status != "VERIFIED" or away_status != "VERIFIED":
        statuses = (home_status, away_status)
        link_status = (
            OddsFixtureLinkStatus.TEAM_ALIAS_AMBIGUOUS
            if "AMBIGUOUS" in statuses
            else OddsFixtureLinkStatus.TEAM_ALIAS_UNRESOLVED
        )
        return OddsFixtureLinkDecision(
            link_status, event.provider_event_id, None,
            "TEAM_ALIAS_" + "_AND_".join(statuses),
            (competition.evidence_ref,), None,
        )

    if (
        home.squad_category is not competition.squad_category
        or away.squad_category is not competition.squad_category
    ):
        return OddsFixtureLinkDecision(
            OddsFixtureLinkStatus.SQUAD_CATEGORY_MISMATCH,
            event.provider_event_id, None, "TEAM_ALIAS_SQUAD_CATEGORY_CONFLICT",
            (competition.evidence_ref, home.evidence_ref, away.evidence_ref), None,
        )
    if home.canonical_team_id == away.canonical_team_id:
        return OddsFixtureLinkDecision(
            OddsFixtureLinkStatus.TEAM_ALIAS_UNRESOLVED,
            event.provider_event_id, None, "HOME_AWAY_ALIAS_COLLISION",
            (competition.evidence_ref, home.evidence_ref, away.evidence_ref), None,
        )

    tolerance_seconds = kickoff_tolerance_minutes * 60
    matches = []
    for fixture in candidate_fixtures:
        if fixture.canonical_competition_id != competition.canonical_competition_id:
            continue
        if fixture.squad_category is not competition.squad_category:
            continue
        if fixture.canonical_home_team_id != home.canonical_team_id:
            continue
        if fixture.canonical_away_team_id != away.canonical_team_id:
            continue
        fixture_kickoff = fixture.kickoff_at_utc.astimezone(timezone.utc)
        delta = abs(int((fixture_kickoff - kickoff).total_seconds()))
        if delta <= tolerance_seconds:
            matches.append((fixture, delta))

    evidence = (competition.evidence_ref, home.evidence_ref, away.evidence_ref)
    if not matches:
        return OddsFixtureLinkDecision(
            OddsFixtureLinkStatus.FIXTURE_UNRESOLVED,
            event.provider_event_id, None, "NO_CANONICAL_FIXTURE_WITHIN_IDENTITY_WINDOW",
            evidence, None,
        )
    if len(matches) > 1:
        return OddsFixtureLinkDecision(
            OddsFixtureLinkStatus.FIXTURE_AMBIGUOUS,
            event.provider_event_id, None, "MULTIPLE_CANONICAL_FIXTURES_MATCH",
            evidence, None,
        )
    fixture, delta = matches[0]
    return OddsFixtureLinkDecision(
        OddsFixtureLinkStatus.MATCHED,
        event.provider_event_id,
        fixture.canonical_fixture_id,
        "ODDS_EVENT_LINKED_BY_VERIFIED_EXACT_ALIASES",
        evidence,
        delta,
    )
