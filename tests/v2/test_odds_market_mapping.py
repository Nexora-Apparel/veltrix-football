from datetime import datetime, timedelta, timezone
from decimal import Decimal

from veltrix_v2.identity.odds_link import OddsFixtureLinkDecision, OddsFixtureLinkStatus
from veltrix_v2.odds.contracts import ProviderOddsQuote
from veltrix_v2.odds.market_mapping import (
    CanonicalMarket,
    CanonicalSelection,
    VerifiedMarketKeyMapping,
)
from veltrix_v2.odds.market_normalization import map_provider_quote


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def quote(market="h2h", outcome="Home FC", point=None):
    return ProviderOddsQuote(
        provider="The Odds API", source_id="the-odds-api",
        provider_event_id="event-1", provider_competition_id="soccer_epl",
        source_record_id="src-1", home_team_name="Home FC",
        away_team_name="Away FC", kickoff_at_utc=NOW + timedelta(hours=2),
        bookmaker_key="book-a", bookmaker_title="Book A",
        provider_market_key=market, outcome_name=outcome,
        decimal_odds=Decimal("1.95"), point=Decimal(str(point)) if point is not None else None,
        quote_updated_at_utc=NOW, fetched_at_utc=NOW,
        raw_response_sha256="a" * 64,
    )


def mapping(key="h2h", market=CanonicalMarket.ONE_X_TWO, **changes):
    values = dict(
        provider="The Odds API", source_id="the-odds-api",
        provider_market_key=key, canonical_market=market,
        mapping_version="v1", evidence_ref="market-map-evidence",
        valid_from_utc=NOW - timedelta(days=1), verified_at_utc=NOW,
        valid_to_utc=None,
    )
    values.update(changes)
    return VerifiedMarketKeyMapping(**values)


def link(event_id="event-1", status=OddsFixtureLinkStatus.MATCHED):
    return OddsFixtureLinkDecision(
        status=status, provider_event_id=event_id,
        canonical_fixture_id="canonical-fx" if status is OddsFixtureLinkStatus.MATCHED else None,
        reason_code="LINKED", evidence_refs=("fixture-link-evidence",),
        kickoff_delta_seconds=0,
    )


def test_h2h_home_draw_away_map_to_canonical_selections():
    for outcome, selection in (
        ("Home FC", CanonicalSelection.HOME),
        ("Draw", CanonicalSelection.DRAW),
        ("Away FC", CanonicalSelection.AWAY),
    ):
        result = map_provider_quote(
            quote(outcome=outcome), (mapping(),), link(), evaluated_at_utc=NOW
        )
        assert result.allowed is True
        assert result.normalized_quote.selection is selection
        assert result.normalized_quote.canonical_fixture_id == "canonical-fx"


def test_totals_requires_line_and_maps_over_under():
    for outcome, selection in (("Over", CanonicalSelection.OVER), ("Under", CanonicalSelection.UNDER)):
        result = map_provider_quote(
            quote("totals", outcome, 2.5),
            (mapping("totals", CanonicalMarket.TOTALS),),
            link(), evaluated_at_utc=NOW,
        )
        assert result.allowed is True
        assert result.normalized_quote.selection is selection
        assert result.normalized_quote.line == Decimal("2.5")


def test_btts_maps_only_yes_and_no_when_key_is_explicitly_verified():
    for outcome, selection in (("Yes", CanonicalSelection.YES), ("No", CanonicalSelection.NO)):
        result = map_provider_quote(
            quote("btts", outcome),
            (mapping("btts", CanonicalMarket.BTTS),),
            link(), evaluated_at_utc=NOW,
        )
        assert result.allowed is True
        assert result.normalized_quote.selection is selection


def test_unmapped_provider_market_key_is_rejected():
    result = map_provider_quote(quote("btts", "Yes"), (), link(), evaluated_at_utc=NOW)
    assert result.allowed is False
    assert result.reason_code == "PROVIDER_MARKET_KEY_UNMAPPED"


def test_fixture_link_must_be_verified_and_same_event():
    result = map_provider_quote(
        quote(), (mapping(),), link(status=OddsFixtureLinkStatus.FIXTURE_UNRESOLVED),
        evaluated_at_utc=NOW,
    )
    assert result.reason_code == "FIXTURE_LINK_NOT_VERIFIED"


def test_market_mapping_must_match_provider_source_and_key():
    wrong = mapping(provider="another-provider")
    result = map_provider_quote(quote(), (wrong,), link(), evaluated_at_utc=NOW)
    assert result.reason_code == "PROVIDER_MARKET_KEY_UNMAPPED"


def test_totals_without_point_are_rejected():
    result = map_provider_quote(
        quote("totals", "Over"), (mapping("totals", CanonicalMarket.TOTALS),),
        link(), evaluated_at_utc=NOW,
    )
    assert result.reason_code == "TOTALS_LINE_REQUIRED"


def test_ambiguous_active_market_mappings_are_rejected():
    result = map_provider_quote(
        quote(), (mapping(), mapping(evidence_ref="other-evidence")),
        link(), evaluated_at_utc=NOW,
    )
    assert result.reason_code == "PROVIDER_MARKET_KEY_MAPPING_AMBIGUOUS"


def test_mapping_verified_after_evaluation_time_is_rejected():
    future = mapping(verified_at_utc=NOW + timedelta(hours=1))
    result = map_provider_quote(quote(), (future,), link(), evaluated_at_utc=NOW)
    assert result.reason_code == "PROVIDER_MARKET_KEY_MAPPING_UNVERIFIED_OR_INACTIVE"
