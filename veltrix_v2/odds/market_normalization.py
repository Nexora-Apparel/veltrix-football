"""Map provider-native quotes only through verified, explicit market mappings."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from veltrix_v2.identity.odds_link import (
    OddsFixtureLinkDecision,
    OddsFixtureLinkStatus,
    normalize_team_name_alias_key,
)
from veltrix_v2.odds.contracts import ProviderOddsQuote
from veltrix_v2.odds.market_mapping import (
    CanonicalMarket,
    CanonicalSelection,
    MarketMappingDecision,
    NormalizedOddsQuote,
    VerifiedMarketKeyMapping,
)


def _active(mapping: VerifiedMarketKeyMapping, at_utc: datetime, evaluated_at: datetime) -> bool:
    if mapping.valid_from_utc.tzinfo is None or mapping.valid_from_utc.utcoffset() is None:
        raise ValueError("market mapping valid_from_utc must be timezone-aware")
    if mapping.verified_at_utc.tzinfo is None or mapping.verified_at_utc.utcoffset() is None:
        raise ValueError("market mapping verified_at_utc must be timezone-aware")
    start = mapping.valid_from_utc.astimezone(timezone.utc)
    verified = mapping.verified_at_utc.astimezone(timezone.utc)
    end = mapping.valid_to_utc.astimezone(timezone.utc) if mapping.valid_to_utc else None
    if mapping.valid_to_utc is not None and (
        mapping.valid_to_utc.tzinfo is None or mapping.valid_to_utc.utcoffset() is None
    ):
        raise ValueError("market mapping valid_to_utc must be timezone-aware")
    return (
        start <= at_utc
        and (end is None or at_utc < end)
        and verified <= evaluated_at
        and bool(mapping.mapping_version.strip())
        and bool(mapping.evidence_ref.strip())
    )


def map_provider_quote(
    quote: ProviderOddsQuote,
    mappings: Sequence[VerifiedMarketKeyMapping],
    fixture_link: OddsFixtureLinkDecision,
    *,
    evaluated_at_utc: datetime,
) -> MarketMappingDecision:
    if evaluated_at_utc.tzinfo is None or evaluated_at_utc.utcoffset() is None:
        raise ValueError("evaluated_at_utc must be timezone-aware")
    if fixture_link.status is not OddsFixtureLinkStatus.MATCHED or not fixture_link.canonical_fixture_id:
        return MarketMappingDecision(False, "FIXTURE_LINK_NOT_VERIFIED", None)
    if fixture_link.provider_event_id != quote.provider_event_id:
        return MarketMappingDecision(False, "PROVIDER_EVENT_ID_MISMATCH", None)

    exact = [
        mapping for mapping in mappings
        if mapping.provider == quote.provider
        and mapping.source_id == quote.source_id
        and mapping.provider_market_key == quote.provider_market_key
    ]
    if not exact:
        return MarketMappingDecision(False, "PROVIDER_MARKET_KEY_UNMAPPED", None)
    quote_time = quote.quote_updated_at_utc.astimezone(timezone.utc)
    evaluated = evaluated_at_utc.astimezone(timezone.utc)
    active = [mapping for mapping in exact if _active(mapping, quote_time, evaluated)]
    if len(active) > 1:
        return MarketMappingDecision(False, "PROVIDER_MARKET_KEY_MAPPING_AMBIGUOUS", None)
    if not active:
        return MarketMappingDecision(False, "PROVIDER_MARKET_KEY_MAPPING_UNVERIFIED_OR_INACTIVE", None)
    mapping = active[0]

    outcome_key = normalize_team_name_alias_key(quote.outcome_name)
    if mapping.canonical_market is CanonicalMarket.ONE_X_TWO:
        if outcome_key == normalize_team_name_alias_key(quote.home_team_name):
            selection = CanonicalSelection.HOME
        elif outcome_key == normalize_team_name_alias_key(quote.away_team_name):
            selection = CanonicalSelection.AWAY
        elif outcome_key == "draw":
            selection = CanonicalSelection.DRAW
        else:
            return MarketMappingDecision(False, "ONE_X_TWO_OUTCOME_UNRECOGNIZED", None)
        if quote.point is not None:
            return MarketMappingDecision(False, "ONE_X_TWO_POINT_NOT_ALLOWED", None)
        line = None
    elif mapping.canonical_market is CanonicalMarket.BTTS:
        if outcome_key == "yes":
            selection = CanonicalSelection.YES
        elif outcome_key == "no":
            selection = CanonicalSelection.NO
        else:
            return MarketMappingDecision(False, "BTTS_OUTCOME_UNRECOGNIZED", None)
        if quote.point is not None:
            return MarketMappingDecision(False, "BTTS_POINT_NOT_ALLOWED", None)
        line = None
    elif mapping.canonical_market is CanonicalMarket.TOTALS:
        if outcome_key == "over":
            selection = CanonicalSelection.OVER
        elif outcome_key == "under":
            selection = CanonicalSelection.UNDER
        else:
            return MarketMappingDecision(False, "TOTALS_OUTCOME_UNRECOGNIZED", None)
        if quote.point is None or quote.point <= 0:
            return MarketMappingDecision(False, "TOTALS_LINE_REQUIRED", None)
        line = quote.point
    else:
        return MarketMappingDecision(False, "CANONICAL_MARKET_UNSUPPORTED", None)

    normalized = NormalizedOddsQuote(
        canonical_fixture_id=fixture_link.canonical_fixture_id,
        canonical_market=mapping.canonical_market,
        selection=selection,
        line=line,
        decimal_odds=quote.decimal_odds,
        bookmaker_key=quote.bookmaker_key,
        bookmaker_title=quote.bookmaker_title,
        provider=quote.provider,
        source_id=quote.source_id,
        provider_event_id=quote.provider_event_id,
        source_record_id=quote.source_record_id,
        provider_market_key=quote.provider_market_key,
        quote_updated_at_utc=quote.quote_updated_at_utc,
        fetched_at_utc=quote.fetched_at_utc,
        raw_response_sha256=quote.raw_response_sha256,
        mapping_evidence_ref=mapping.evidence_ref,
    )
    return MarketMappingDecision(True, "PROVIDER_QUOTE_MAPPED", normalized)
