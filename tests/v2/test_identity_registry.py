from datetime import datetime, timedelta, timezone

from veltrix_v2.domain.identity import SquadCategory
from veltrix_v2.identity.registry import (
    MappingResolutionStatus,
    MappingVerificationState,
    ProviderCompetitionMapping,
    ProviderFixtureSourceIdentity,
    ProviderTeamMapping,
    resolve_provider_fixture,
)


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


class MappingRepo:
    def __init__(self, competitions=(), teams=None):
        self.competitions = tuple(competitions)
        self.teams = teams or {}

    def get_competition_mappings(self, **kwargs):
        return self.competitions

    def get_team_mappings(self, *, provider, source_id, provider_team_id):
        return self.teams.get(provider_team_id, ())


def source(**changes):
    values = dict(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_fixture_id="fixture-9", provider_competition_id="league-7",
        provider_home_team_id="home-1", provider_away_team_id="away-2",
        squad_category=SquadCategory.SENIOR_MEN, kickoff_at_utc=NOW,
    )
    values.update(changes)
    return ProviderFixtureSourceIdentity(**values)


def comp(**changes):
    values = dict(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_competition_id="league-7", canonical_competition_id="comp-epl",
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="competition-audit-1", valid_from_utc=NOW - timedelta(days=30),
        verified_at_utc=NOW - timedelta(days=1),
    )
    values.update(changes)
    return ProviderCompetitionMapping(**values)


def team(provider_id, canonical_id, **changes):
    values = dict(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_team_id=provider_id, canonical_team_id=canonical_id,
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref=f"team-audit-{provider_id}", valid_from_utc=NOW - timedelta(days=30),
        verified_at_utc=NOW - timedelta(days=1),
    )
    values.update(changes)
    return ProviderTeamMapping(**values)


def repo(**changes):
    return MappingRepo(
        competitions=changes.get("competitions", (comp(),)),
        teams=changes.get("teams", {
            "home-1": (team("home-1", "canonical-home"),),
            "away-2": (team("away-2", "canonical-away"),),
        }),
    )


def resolve(source_record=None, repository=None, evaluated_at=NOW):
    return resolve_provider_fixture(
        source_record or source(),
        repository or repo(),
        evaluated_at_utc=evaluated_at,
    )


def test_exact_verified_provider_ids_resolve_to_canonical_fixture_identity():
    result = resolve()
    assert result.status is MappingResolutionStatus.VERIFIED
    assert result.canonical_identity.canonical_home_team_id == "canonical-home"
    assert result.canonical_identity.canonical_away_team_id == "canonical-away"
    assert result.source_identity.provider_fixture_id == "fixture-9"
    assert len(result.evidence_refs) == 3


def test_missing_competition_mapping_is_unresolved():
    result = resolve(repository=repo(competitions=()))
    assert result.status is MappingResolutionStatus.UNRESOLVED
    assert result.canonical_identity is None


def test_unverified_team_alias_is_never_used():
    unverified = team("home-1", "canonical-home", state=MappingVerificationState.UNVERIFIED)
    result = resolve(repository=repo(teams={
        "home-1": (unverified,),
        "away-2": (team("away-2", "canonical-away"),),
    }))
    assert result.status is MappingResolutionStatus.UNVERIFIED
    assert result.canonical_identity is None


def test_multiple_active_verified_team_mappings_are_ambiguous():
    result = resolve(repository=repo(teams={
        "home-1": (
            team("home-1", "canonical-home"),
            team("home-1", "another-home"),
        ),
        "away-2": (team("away-2", "canonical-away"),),
    }))
    assert result.status is MappingResolutionStatus.AMBIGUOUS


def test_squad_category_mismatch_is_quarantined():
    women_comp = comp(squad_category=SquadCategory.SENIOR_WOMEN)
    result = resolve(repository=repo(competitions=(women_comp,)))
    assert result.status is MappingResolutionStatus.SQUAD_CATEGORY_MISMATCH
    assert result.canonical_identity is None


def test_expired_mapping_does_not_resolve():
    expired = team(
        "home-1", "canonical-home",
        valid_to_utc=NOW - timedelta(seconds=1),
    )
    result = resolve(repository=repo(teams={
        "home-1": (expired,),
        "away-2": (team("away-2", "canonical-away"),),
    }))
    assert result.status is MappingResolutionStatus.UNRESOLVED


def test_mapping_for_different_provider_or_source_is_invalid():
    wrong = comp(provider="other-provider")
    result = resolve(repository=repo(competitions=(wrong,)))
    assert result.status is MappingResolutionStatus.INVALID_MAPPING


def test_same_canonical_team_on_both_sides_is_invalid():
    result = resolve(repository=repo(teams={
        "home-1": (team("home-1", "same-team"),),
        "away-2": (team("away-2", "same-team"),),
    }))
    assert result.status is MappingResolutionStatus.INVALID_MAPPING
    assert result.reason_code == "HOME_AWAY_CANONICAL_TEAM_COLLISION"


def test_home_away_provider_order_is_preserved():
    reversed_source = source(
        provider_home_team_id="away-2",
        provider_away_team_id="home-1",
    )
    result = resolve(source_record=reversed_source)
    assert result.canonical_identity.canonical_home_team_id == "canonical-away"
    assert result.canonical_identity.canonical_away_team_id == "canonical-home"


def test_retrospectively_verified_mapping_can_resolve_historical_fixture():
    retroactive = comp(verified_at_utc=NOW - timedelta(hours=1))
    result = resolve(repository=repo(competitions=(retroactive,)))
    assert result.status is MappingResolutionStatus.VERIFIED


def test_mapping_verified_after_evaluation_time_is_not_usable():
    future_verified = comp(verified_at_utc=NOW + timedelta(hours=1))
    result = resolve(repository=repo(competitions=(future_verified,)))
    assert result.status is MappingResolutionStatus.UNVERIFIED


def test_squad_category_can_be_derived_from_verified_competition_mapping():
    result = resolve(source_record=source(squad_category=None))
    assert result.status is MappingResolutionStatus.VERIFIED
    assert result.canonical_identity.squad_category is SquadCategory.SENIOR_MEN
