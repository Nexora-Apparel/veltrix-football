import pytest
from veltrix_v2.data.provider_registry import (
    CapabilityState, DataDomain, PROVIDER_REGISTRY, ProviderState,
    assert_provider_dispatch_allowed, dispatchable_providers_for, providers_for,
)


def test_exhausted_credit_providers_are_hard_blocked():
    for name in ("GOAL API", "StrikerAPI"):
        profile = next(p for p in PROVIDER_REGISTRY if p.provider == name)
        assert profile.state is ProviderState.SUSPENDED_CREDITS
        assert not profile.collection_allowed
        with pytest.raises(PermissionError, match="PROVIDER_COLLECTION_DISABLED"):
            assert_provider_dispatch_allowed(name)


def test_fivedollar_is_only_live_fixture_source_and_results_have_archive_supplement():
    assert [p.provider for p in providers_for(DataDomain.FIXTURES)] == ["5DollarFootballAPI"]
    assert [p.provider for p in providers_for(DataDomain.RESULTS)] == ["5DollarFootballAPI", "OpenFootball"]


def test_archive_and_odds_provider_are_not_dispatchable_by_default():
    for name in ("OpenFootball", "The Odds API"):
        with pytest.raises(PermissionError):
            assert_provider_dispatch_allowed(name)


def test_odds_markets_remain_conditional_not_enabled():
    profile = next(p for p in PROVIDER_REGISTRY if p.provider == "The Odds API")
    for domain in (DataDomain.ODDS_1X2, DataDomain.ODDS_TOTALS, DataDomain.ODDS_BTTS):
        assert profile.capability(domain).state is CapabilityState.CONDITIONAL
        assert profile in providers_for(domain, include_conditional=True)
        assert profile not in dispatchable_providers_for(domain, include_conditional=True)


def test_xg_lineups_injuries_and_player_stats_are_not_fabricated():
    for domain in (DataDomain.EXPECTED_GOALS, DataDomain.LINEUPS, DataDomain.INJURIES, DataDomain.PLAYER_STATS):
        assert providers_for(domain) == ()


def test_internal_form_and_strength_features_have_explicit_derived_status():
    profile = next(p for p in PROVIDER_REGISTRY if p.provider == "5DollarFootballAPI")
    assert profile.capability(DataDomain.TEAM_FORM).state is CapabilityState.DERIVED
    archive = next(p for p in PROVIDER_REGISTRY if p.provider == "OpenFootball")
    assert archive.capability(DataDomain.TEAM_FORM).state is CapabilityState.EXPLORATORY_ONLY
    assert profile.capability(DataDomain.TEAM_STRENGTH).state is CapabilityState.DERIVED

def test_statsbomb_is_historical_research_only_xg_and_lineup_candidate():
    profile = next(p for p in PROVIDER_REGISTRY if p.provider == "StatsBomb Open Data")
    assert profile.state is ProviderState.ARCHIVE_ONLY
    assert not profile.collection_allowed
    for domain in (DataDomain.EXPECTED_GOALS, DataDomain.LINEUPS):
        assert profile.capability(domain).state is CapabilityState.CONDITIONAL
        assert profile in providers_for(domain, include_conditional=True)
        assert profile not in dispatchable_providers_for(domain, include_conditional=True)
    with pytest.raises(PermissionError):
        assert_provider_dispatch_allowed("StatsBomb Open Data")
