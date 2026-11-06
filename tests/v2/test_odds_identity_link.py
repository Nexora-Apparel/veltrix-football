from datetime import datetime, timedelta, timezone

from veltrix_v2.domain.identity import CanonicalFixtureIdentity, SquadCategory
from veltrix_v2.identity.odds_link import (
    OddsFixtureLinkStatus,
    ProviderOddsEventIdentity,
    VerifiedTeamNameAlias,
    normalize_team_name_alias_key,
    resolve_odds_event,
)
from veltrix_v2.identity.registry import (
    MappingVerificationState,
    ProviderCompetitionMapping,
)


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def event(**changes):
    values = dict(
        provider="The Odds API", source_id="the-odds-api",
        provider_event_id="event-55",
        provider_competition_id="soccer_england_premier_league",
        home_team_name="Manchester City", away_team_name="Arsenal",
        kickoff_at_utc=NOW + timedelta(hours=3),
    )
    values.update(changes)
    return ProviderOddsEventIdentity(**values)


def competition():
    return ProviderCompetitionMapping(
        provider="The Odds API", source_id="the-odds-api",
        provider_competition_id="soccer_england_premier_league",
        canonical_competition_id="epl",
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="odds-comp-map", valid_from_utc=NOW - timedelta(days=1),
        verified_at_utc=NOW,
    )


def alias(name, team_id, **changes):
    values = dict(
        provider="The Odds API", source_id="the-odds-api",
        normalized_name=normalize_team_name_alias_key(name),
        canonical_team_id=team_id, squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref=f"alias-{team_id}", valid_from_utc=NOW - timedelta(days=1),
        valid_to_utc=None, verified_at_utc=NOW,
    )
    values.update(changes)
    return VerifiedTeamNameAlias(**values)


def fixture(**changes):
    values = dict(
        canonical_fixture_id="canonical-fx",
        canonical_competition_id="epl",
        squad_category=SquadCategory.SENIOR_MEN,
        canonical_home_team_id="man-city",
        canonical_away_team_id="arsenal",
        kickoff_at_utc=NOW + timedelta(hours=3, minutes=5),
    )
    values.update(changes)
    return CanonicalFixtureIdentity(**values)


def resolve(event_value=None, candidates=None, home_aliases=None, away_aliases=None):
    return resolve_odds_event(
        event_value or event(),
        (competition(),),
        home_aliases or (alias("Manchester City", "man-city"),),
        away_aliases or (alias("Arsenal", "arsenal"),),
        candidates if candidates is not None else (fixture(),),
        evaluated_at_utc=NOW,
    )


def test_exact_verified_aliases_link_odds_event_to_existing_fixture():
    result = resolve()
    assert result.status is OddsFixtureLinkStatus.MATCHED
    assert result.canonical_fixture_id == "canonical-fx"
    assert result.provider_event_id == "event-55"
    assert result.kickoff_delta_seconds == 300


def test_unverified_alias_does_not_link():
    draft = alias("Manchester City", "man-city", state=MappingVerificationState.UNVERIFIED)
    result = resolve(home_aliases=(draft,))
    assert result.status is OddsFixtureLinkStatus.TEAM_ALIAS_UNRESOLVED
    assert result.canonical_fixture_id is None


def test_ambiguous_alias_is_quarantined():
    result = resolve(home_aliases=(
        alias("Manchester City", "man-city"),
        alias("Manchester City", "another-team"),
    ))
    assert result.status is OddsFixtureLinkStatus.TEAM_ALIAS_AMBIGUOUS


def test_squad_category_mismatch_is_quarantined():
    women = alias(
        "Manchester City", "man-city",
        squad_category=SquadCategory.SENIOR_WOMEN,
    )
    result = resolve(home_aliases=(women,))
    assert result.status is OddsFixtureLinkStatus.SQUAD_CATEGORY_MISMATCH


def test_reversed_home_away_is_not_matched():
    reversed_fixture = fixture(
        canonical_home_team_id="arsenal",
        canonical_away_team_id="man-city",
    )
    result = resolve(candidates=(reversed_fixture,))
    assert result.status is OddsFixtureLinkStatus.FIXTURE_UNRESOLVED


def test_kickoff_outside_tolerance_is_not_matched():
    distant = fixture(kickoff_at_utc=NOW + timedelta(hours=4))
    result = resolve(candidates=(distant,))
    assert result.status is OddsFixtureLinkStatus.FIXTURE_UNRESOLVED


def test_multiple_canonical_candidates_are_ambiguous():
    result = resolve(candidates=(
        fixture(canonical_fixture_id="fx-a"),
        fixture(canonical_fixture_id="fx-b"),
    ))
    assert result.status is OddsFixtureLinkStatus.FIXTURE_AMBIGUOUS


def test_name_normalization_is_deterministic_but_not_fuzzy():
    assert normalize_team_name_alias_key("  MANCHESTER-CITY ") == "manchester city"
    result = resolve(event_value=event(home_team_name="Man City"))
    assert result.status is OddsFixtureLinkStatus.TEAM_ALIAS_UNRESOLVED


def test_odds_event_identity_is_never_used_to_create_a_new_fixture():
    result = resolve(candidates=())
    assert result.status is OddsFixtureLinkStatus.FIXTURE_UNRESOLVED
    assert result.provider_event_id == "event-55"



def test_alias_with_future_verification_timestamp_is_unusable():
    future = alias(
        "Manchester City", "man-city",
        verified_at_utc=NOW + timedelta(hours=1),
    )
    result = resolve(home_aliases=(future,))
    assert result.status is OddsFixtureLinkStatus.TEAM_ALIAS_UNRESOLVED


def test_alias_validity_window_must_be_positive():
    try:
        alias(
            "Manchester City", "man-city",
            valid_to_utc=NOW - timedelta(days=1),
        )
    except ValueError as exc:
        assert "after valid_from_utc" in str(exc)
    else:
        raise AssertionError("invalid alias validity window must be rejected")
