"""Deterministic fixture reconciliation after verified team/competition mapping.

No fuzzy team-name matching occurs here. Provider identities must first resolve
through explicit, verified, competition- and squad-scoped mappings.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Sequence


class SquadCategory(StrEnum):
    SENIOR_MEN = "SENIOR_MEN"
    SENIOR_WOMEN = "SENIOR_WOMEN"
    YOUTH = "YOUTH"
    RESERVE = "RESERVE"
    OTHER = "OTHER"


class ReconciliationStatus(StrEnum):
    NEW_CANONICAL_FIXTURE = "NEW_CANONICAL_FIXTURE"
    MATCHED_EXISTING = "MATCHED_EXISTING"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED_IDENTITY = "UNRESOLVED_IDENTITY"


@dataclass(frozen=True, slots=True)
class ProviderFixtureIdentity:
    provider: str
    provider_fixture_id: str
    provider_competition_id: str
    canonical_competition_id: str | None
    squad_category: SquadCategory
    canonical_home_team_id: str | None
    canonical_away_team_id: str | None
    kickoff_at_utc: datetime


@dataclass(frozen=True, slots=True)
class CanonicalFixtureIdentity:
    canonical_fixture_id: str
    canonical_competition_id: str
    squad_category: SquadCategory
    canonical_home_team_id: str
    canonical_away_team_id: str
    kickoff_at_utc: datetime


@dataclass(frozen=True, slots=True)
class ReconciliationDecision:
    status: ReconciliationStatus
    canonical_fixture_id: str | None
    candidate_fixture_ids: tuple[str, ...]
    provider_record: ProviderFixtureIdentity


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("kickoff timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def reconcile_provider_fixture(
    provider_record: ProviderFixtureIdentity,
    existing: Sequence[CanonicalFixtureIdentity],
    *,
    kickoff_tolerance: timedelta = timedelta(minutes=15),
) -> ReconciliationDecision:
    """Match only exact canonical identities and a bounded kickoff window.

    A provider record is returned unchanged in every decision so the caller can
    persist its provenance even when it is new, ambiguous or unresolved.
    """
    if not provider_record.provider.strip():
        raise ValueError("provider name is required")
    if not provider_record.provider_fixture_id.strip():
        raise ValueError("provider fixture ID is required")
    if not provider_record.provider_competition_id.strip():
        raise ValueError("provider competition ID is required")
    if kickoff_tolerance < timedelta(0):
        raise ValueError("kickoff_tolerance cannot be negative")

    if (
        not provider_record.canonical_competition_id
        or not provider_record.canonical_home_team_id
        or not provider_record.canonical_away_team_id
        or provider_record.canonical_home_team_id == provider_record.canonical_away_team_id
    ):
        return ReconciliationDecision(
            ReconciliationStatus.UNRESOLVED_IDENTITY,
            None,
            (),
            provider_record,
        )

    kickoff = _as_utc(provider_record.kickoff_at_utc)
    matches: list[str] = []
    for fixture in existing:
        if (
            fixture.canonical_competition_id != provider_record.canonical_competition_id
            or fixture.squad_category is not provider_record.squad_category
            or fixture.canonical_home_team_id != provider_record.canonical_home_team_id
            or fixture.canonical_away_team_id != provider_record.canonical_away_team_id
        ):
            continue
        existing_kickoff = _as_utc(fixture.kickoff_at_utc)
        if abs(existing_kickoff - kickoff) <= kickoff_tolerance:
            matches.append(fixture.canonical_fixture_id)

    if len(matches) == 1:
        return ReconciliationDecision(
            ReconciliationStatus.MATCHED_EXISTING,
            matches[0],
            tuple(matches),
            provider_record,
        )
    if len(matches) > 1:
        return ReconciliationDecision(
            ReconciliationStatus.AMBIGUOUS,
            None,
            tuple(sorted(matches)),
            provider_record,
        )
    return ReconciliationDecision(
        ReconciliationStatus.NEW_CANONICAL_FIXTURE,
        None,
        (),
        provider_record,
    )
