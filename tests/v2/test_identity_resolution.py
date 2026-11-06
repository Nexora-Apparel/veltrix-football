from datetime import datetime, timedelta, timezone

from veltrix_v2.domain.identity import CanonicalFixtureIdentity, SquadCategory
from veltrix_v2.identity.resolution import (
    FixtureIdentityPipelineStatus,
    resolve_and_reconcile_fixture,
)
from veltrix_v2.identity.registry import (
    MappingVerificationState,
    ProviderCompetitionMapping,
    ProviderFixtureSourceIdentity,
    ProviderTeamMapping,
)


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


class Repo:
    def __init__(self, competitions, teams):
        self.competitions = competitions
        self.teams = teams
    def get_competition_mappings(self, **kwargs):
        return self.competitions
    def get_team_mappings(self, *, provider, source_id, provider_team_id):
        return self.teams.get(provider_team_id, ())


def source():
    return ProviderFixtureSourceIdentity(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_fixture_id="provider-fx-1", provider_competition_id="provider-league-1",
        provider_home_team_id="provider-home", provider_away_team_id="provider-away",
        squad_category=SquadCategory.SENIOR_MEN,
        kickoff_at_utc=NOW + timedelta(hours=4),
    )


def repository():
    competition = ProviderCompetitionMapping(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_competition_id="provider-league-1",
        canonical_competition_id="canonical-league",
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="comp-evidence", valid_from_utc=NOW - timedelta(days=1),
        verified_at_utc=NOW,
    )
    home = ProviderTeamMapping(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_team_id="provider-home", canonical_team_id="canonical-home",
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="home-evidence", valid_from_utc=NOW - timedelta(days=1),
        verified_at_utc=NOW,
    )
    away = ProviderTeamMapping(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_team_id="provider-away", canonical_team_id="canonical-away",
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="away-evidence", valid_from_utc=NOW - timedelta(days=1),
        verified_at_utc=NOW,
    )
    return Repo((competition,), {"provider-home": (home,), "provider-away": (away,)})


def existing(fixture_id="canonical-fx-1", kickoff=None):
    return CanonicalFixtureIdentity(
        canonical_fixture_id=fixture_id, canonical_competition_id="canonical-league",
        squad_category=SquadCategory.SENIOR_MEN,
        canonical_home_team_id="canonical-home", canonical_away_team_id="canonical-away",
        kickoff_at_utc=kickoff or NOW + timedelta(hours=4, minutes=5),
    )


def test_resolve_and_reconcile_matches_existing_canonical_fixture():
    result = resolve_and_reconcile_fixture(
        source(), repository(), [existing()], evaluated_at_utc=NOW
    )
    assert result.status == FixtureIdentityPipelineStatus.MATCHED_EXISTING
    assert result.reconciliation.canonical_fixture_id == "canonical-fx-1"
    assert result.source_identity.provider_fixture_id == "provider-fx-1"
    assert len(result.evidence_refs) == 3


def test_new_fixture_requires_verified_mappings_but_no_existing_match():
    result = resolve_and_reconcile_fixture(
        source(), repository(), [], evaluated_at_utc=NOW
    )
    assert result.status == FixtureIdentityPipelineStatus.NEW_CANONICAL_FIXTURE
    assert result.reconciliation.canonical_fixture_id is None


def test_ambiguous_canonical_matches_are_quarantined():
    result = resolve_and_reconcile_fixture(
        source(), repository(),
        [existing("fx-a"), existing("fx-b")],
        evaluated_at_utc=NOW,
    )
    assert result.status == FixtureIdentityPipelineStatus.FIXTURE_AMBIGUOUS
    assert result.reconciliation.candidate_fixture_ids == ("fx-a", "fx-b")


def test_unverified_mapping_never_reaches_fixture_reconciliation():
    repo = repository()
    bad_comp = ProviderCompetitionMapping(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_competition_id="provider-league-1",
        canonical_competition_id="canonical-league",
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.UNVERIFIED, mapping_version="draft",
        evidence_ref="draft-evidence", valid_from_utc=NOW - timedelta(days=1),
    )
    repo.competitions = (bad_comp,)
    result = resolve_and_reconcile_fixture(
        source(), repo, [existing()], evaluated_at_utc=NOW
    )
    assert result.status == FixtureIdentityPipelineStatus.MAPPING_UNVERIFIED
    assert result.reconciliation is None
