from datetime import datetime, timedelta, timezone

from veltrix_v2.domain.identity import (
    CanonicalFixtureIdentity,
    ProviderFixtureIdentity,
    ReconciliationStatus,
    SquadCategory,
    reconcile_provider_fixture,
)


KICKOFF = datetime(2026, 11, 6, 18, 0, tzinfo=timezone.utc)


def provider(**overrides):
    values = dict(
        provider="5DollarFootballAPI",
        provider_fixture_id="provider-fixture-123",
        provider_competition_id="provider-comp-9",
        canonical_competition_id="competition-uel",
        squad_category=SquadCategory.SENIOR_MEN,
        canonical_home_team_id="team-home",
        canonical_away_team_id="team-away",
        kickoff_at_utc=KICKOFF,
    )
    values.update(overrides)
    return ProviderFixtureIdentity(**values)


def canonical(fixture_id="canonical-1", **overrides):
    values = dict(
        canonical_fixture_id=fixture_id,
        canonical_competition_id="competition-uel",
        squad_category=SquadCategory.SENIOR_MEN,
        canonical_home_team_id="team-home",
        canonical_away_team_id="team-away",
        kickoff_at_utc=KICKOFF + timedelta(minutes=5),
    )
    values.update(overrides)
    return CanonicalFixtureIdentity(**values)


def test_exact_canonical_identity_and_kickoff_matches_existing_fixture():
    source = provider()
    decision = reconcile_provider_fixture(source, [canonical()])
    assert decision.status is ReconciliationStatus.MATCHED_EXISTING
    assert decision.canonical_fixture_id == "canonical-1"
    assert decision.provider_record == source


def test_provider_record_is_retained_when_new_canonical_fixture_is_needed():
    source = provider()
    decision = reconcile_provider_fixture(source, [])
    assert decision.status is ReconciliationStatus.NEW_CANONICAL_FIXTURE
    assert decision.provider_record == source


def test_ambiguous_multiple_matches_are_quarantined():
    decision = reconcile_provider_fixture(
        provider(),
        [canonical("canonical-a"), canonical("canonical-b")],
    )
    assert decision.status is ReconciliationStatus.AMBIGUOUS
    assert decision.canonical_fixture_id is None
    assert decision.candidate_fixture_ids == ("canonical-a", "canonical-b")


def test_different_squad_category_never_matches():
    decision = reconcile_provider_fixture(
        provider(squad_category=SquadCategory.SENIOR_WOMEN),
        [canonical()],
    )
    assert decision.status is ReconciliationStatus.NEW_CANONICAL_FIXTURE


def test_home_away_reversal_never_matches():
    decision = reconcile_provider_fixture(
        provider(canonical_home_team_id="team-away", canonical_away_team_id="team-home"),
        [canonical()],
    )
    assert decision.status is ReconciliationStatus.NEW_CANONICAL_FIXTURE


def test_competition_mismatch_never_matches():
    decision = reconcile_provider_fixture(
        provider(canonical_competition_id="competition-other"),
        [canonical()],
    )
    assert decision.status is ReconciliationStatus.NEW_CANONICAL_FIXTURE


def test_kickoff_outside_tolerance_never_matches():
    decision = reconcile_provider_fixture(
        provider(kickoff_at_utc=KICKOFF + timedelta(hours=2)),
        [canonical()],
    )
    assert decision.status is ReconciliationStatus.NEW_CANONICAL_FIXTURE


def test_unverified_team_or_competition_mapping_is_quarantined():
    decision = reconcile_provider_fixture(
        provider(canonical_home_team_id=None),
        [canonical()],
    )
    assert decision.status is ReconciliationStatus.UNRESOLVED_IDENTITY
    assert decision.provider_record.provider_fixture_id == "provider-fixture-123"
