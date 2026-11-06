from datetime import datetime, timedelta, timezone

from veltrix_v2.domain.contracts import DataUsePurpose, RightsStatus, SourceRights
from veltrix_v2.domain.identity import SquadCategory
from veltrix_v2.history.importer import build_training_history_match
from veltrix_v2.identity.registry import (
    MappingResolutionStatus,
    ProviderFixtureSourceIdentity,
    ResolvedProviderFixture,
)
from veltrix_v2.ingestion.providers.five_dollar_fixture import (
    FiveDollarFixtureRecord,
    FiveDollarFixtureStatus,
)


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
KICKOFF = NOW - timedelta(days=2)


def fixture(status=FiveDollarFixtureStatus.FINISHED, home=2, away=1):
    source = ProviderFixtureSourceIdentity(
        provider="5DollarFootballAPI", source_id="five-dollar",
        provider_fixture_id="fixture-1", provider_competition_id="league-1",
        provider_home_team_id="provider-home", provider_away_team_id="provider-away",
        squad_category=None, kickoff_at_utc=KICKOFF,
    )
    return FiveDollarFixtureRecord(
        source_identity=source, status=status, raw_status=status.value.lower(),
        home_team_name="Home FC", away_team_name="Away FC",
        competition_name="League", completed_home_goals=home,
        completed_away_goals=away, status_reason=None, status_code="full",
        raw_payload_sha256="a" * 64,
    )


def resolved(source=None, status=MappingResolutionStatus.VERIFIED):
    source = source or fixture().source_identity
    canonical = None
    if status is MappingResolutionStatus.VERIFIED:
        from veltrix_v2.domain.identity import ProviderFixtureIdentity
        canonical = ProviderFixtureIdentity(
            provider="5DollarFootballAPI", provider_fixture_id="fixture-1",
            provider_competition_id="league-1", canonical_competition_id="league-c",
            squad_category=SquadCategory.SENIOR_MEN,
            canonical_home_team_id="team-home", canonical_away_team_id="team-away",
            kickoff_at_utc=KICKOFF,
        )
    return ResolvedProviderFixture(
        status=status, source_identity=source, canonical_identity=canonical,
        reason_code="resolved", evidence_refs=("comp-map", "home-map", "away-map"),
    )


def rights(uses=None):
    return SourceRights(
        source_id="five-dollar", rights_status=RightsStatus.VERIFIED,
        commercial_use_allowed=True,
        permitted_uses=frozenset(uses or {
            DataUsePurpose.HISTORICAL_IMPORT,
            DataUsePurpose.CACHE,
            DataUsePurpose.MODEL_TRAINING,
        }),
        terms_url="https://provider.example/terms", terms_version="2026-11",
        verified_at_utc=NOW, evidence_sha256="b" * 64,
    )


def build(fixture_record=None, identity=None, rights_record=None, cutoff=NOW):
    record = fixture_record or fixture()
    return build_training_history_match(
        record, identity or resolved(record.source_identity),
        "stored-source-record-1", rights_record or rights(),
        "canonical-fixture-1", evaluated_at_utc=cutoff,
    )


def test_settled_rights_cleared_fixture_becomes_training_history():
    result = build()
    assert result.allowed is True
    assert result.historical_match.canonical_fixture_id == "canonical-fixture-1"
    assert result.historical_match.home_goals == 2
    assert result.historical_match.away_goals == 1
    assert result.historical_match.provider_fixture_refs == (
        ("5DollarFootballAPI", "five-dollar", "fixture-1"),
    )


def test_unsettled_or_unknown_fixture_never_enters_history():
    result = build(fixture_record=fixture(FiveDollarFixtureStatus.UNKNOWN, None, None))
    assert result.allowed is False
    assert result.reason_code == "FIXTURE_RESULT_NOT_SETTLED"


def test_scheduled_fixture_never_enters_history():
    result = build(fixture_record=fixture(FiveDollarFixtureStatus.SCHEDULED, None, None))
    assert result.reason_code == "FIXTURE_RESULT_NOT_SETTLED"


def test_unverified_identity_never_enters_history():
    result = build(identity=resolved(status=MappingResolutionStatus.UNVERIFIED))
    assert result.allowed is False
    assert result.reason_code == "PROVIDER_IDENTITY_NOT_VERIFIED"


def test_source_identity_mismatch_never_enters_history():
    wrong_source = fixture().source_identity
    wrong_source = ProviderFixtureSourceIdentity(
        provider=wrong_source.provider, source_id=wrong_source.source_id,
        provider_fixture_id="different-fixture",
        provider_competition_id=wrong_source.provider_competition_id,
        provider_home_team_id=wrong_source.provider_home_team_id,
        provider_away_team_id=wrong_source.provider_away_team_id,
        squad_category=None, kickoff_at_utc=KICKOFF,
    )
    result = build(identity=resolved(wrong_source))
    assert result.reason_code == "PROVIDER_IDENTITY_NOT_VERIFIED"


def test_future_fixture_cannot_be_imported_as_historical():
    future = fixture()
    future_source = ProviderFixtureSourceIdentity(
        provider=future.source_identity.provider, source_id=future.source_identity.source_id,
        provider_fixture_id=future.source_identity.provider_fixture_id,
        provider_competition_id=future.source_identity.provider_competition_id,
        provider_home_team_id=future.source_identity.provider_home_team_id,
        provider_away_team_id=future.source_identity.provider_away_team_id,
        squad_category=None, kickoff_at_utc=NOW + timedelta(hours=1),
    )
    future_fixture = FiveDollarFixtureRecord(
        source_identity=future_source, status=FiveDollarFixtureStatus.FINISHED,
        raw_status="finished", home_team_name="Home", away_team_name="Away",
        competition_name="League", completed_home_goals=2, completed_away_goals=1,
        status_reason=None, status_code="full", raw_payload_sha256="a" * 64,
    )
    result = build(fixture_record=future_fixture, identity=resolved(future_source))
    assert result.reason_code == "FIXTURE_NOT_HISTORICAL_AT_IMPORT_TIME"


def test_training_rights_are_checked_separately_from_cache_rights():
    allowed = {DataUsePurpose.HISTORICAL_IMPORT, DataUsePurpose.CACHE}
    result = build(rights_record=rights(allowed))
    assert result.allowed is False
    assert result.reason_code == "PURPOSE_NOT_PERMITTED"


def test_source_commercial_permission_is_required():
    restricted = SourceRights(
        source_id="five-dollar", rights_status=RightsStatus.VERIFIED,
        commercial_use_allowed=False,
        permitted_uses=frozenset({
            DataUsePurpose.HISTORICAL_IMPORT, DataUsePurpose.CACHE, DataUsePurpose.MODEL_TRAINING,
        }),
        terms_url="https://provider.example/terms", terms_version="2026-11",
        verified_at_utc=NOW, evidence_sha256="b" * 64,
    )
    result = build(rights_record=restricted)
    assert result.allowed is False
