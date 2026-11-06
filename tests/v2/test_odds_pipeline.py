import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from veltrix_v2.domain.identity import CanonicalFixtureIdentity, SquadCategory
from veltrix_v2.identity.odds_link import VerifiedTeamNameAlias, normalize_team_name_alias_key
from veltrix_v2.identity.registry import MappingVerificationState, ProviderCompetitionMapping
from veltrix_v2.ingestion.ports import RawProviderRecord, StoredSourceRecord
from veltrix_v2.odds.market_mapping import CanonicalMarket, VerifiedMarketKeyMapping
from veltrix_v2.odds.pipeline import process_odds_event_record


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)
FETCHED = NOW


def payload():
    return [{
        "id": "event-1", "sport_key": "soccer_epl",
        "commence_time": "2026-11-06T12:00:00Z",
        "home_team": "Home FC", "away_team": "Away FC",
        "bookmakers": [{
            "key": "book-a", "title": "Book A",
            "markets": [
                {"key": "h2h", "last_update": "2026-11-06T08:59:00Z",
                 "outcomes": [{"name": "Home FC", "price": 1.9}, {"name": "Draw", "price": 3.3}, {"name": "Away FC", "price": 4.0}]},
                {"key": "totals", "last_update": "2026-11-06T08:59:00Z",
                 "outcomes": [{"name": "Over", "price": 1.8, "point": 2.5}, {"name": "Under", "price": 2.0, "point": 2.5}]},
                {"key": "btts", "last_update": "2026-11-06T08:59:00Z",
                 "outcomes": [{"name": "Yes", "price": 1.7}, {"name": "No", "price": 2.1}]},
            ],
        }],
    }]


def records(body=None):
    raw_bytes = json.dumps(body if body is not None else payload()).encode()
    raw = RawProviderRecord(
        provider="The Odds API", source_id="the-odds-api",
        provider_record_id="event-1", provider_fixture_id="event-1",
        provider_competition_id="soccer_epl", data_class="odds",
        raw_payload=raw_bytes,
    )
    stored = StoredSourceRecord(
        source_record_id="stored-source-1", payload_reference="blob://sha",
        raw_payload_sha256=sha256(raw_bytes).hexdigest(), duplicate=False,
    )
    # The ingestion envelope's fetch timestamp is immutable and separate from provider quote times.
    object.__setattr__(raw, "fetched_at_utc", FETCHED)
    return raw, stored


def mappings():
    competition = ProviderCompetitionMapping(
        provider="The Odds API", source_id="the-odds-api",
        provider_competition_id="soccer_epl", canonical_competition_id="epl",
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="comp-evidence", valid_from_utc=NOW - timedelta(days=1),
        verified_at_utc=NOW,
    )
    home = VerifiedTeamNameAlias(
        provider="The Odds API", source_id="the-odds-api",
        normalized_name=normalize_team_name_alias_key("Home FC"),
        canonical_team_id="home", squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="home-evidence", valid_from_utc=NOW - timedelta(days=1),
        valid_to_utc=None, verified_at_utc=NOW,
    )
    away = VerifiedTeamNameAlias(
        provider="The Odds API", source_id="the-odds-api",
        normalized_name=normalize_team_name_alias_key("Away FC"),
        canonical_team_id="away", squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="away-evidence", valid_from_utc=NOW - timedelta(days=1),
        valid_to_utc=None, verified_at_utc=NOW,
    )
    markets = tuple(
        VerifiedMarketKeyMapping(
            provider="The Odds API", source_id="the-odds-api",
            provider_market_key=key, canonical_market=market,
            mapping_version="v1", evidence_ref=f"market-{key}",
            valid_from_utc=NOW - timedelta(days=1), verified_at_utc=NOW,
        )
        for key, market in (
            ("h2h", CanonicalMarket.ONE_X_TWO),
            ("totals", CanonicalMarket.TOTALS),
            ("btts", CanonicalMarket.BTTS),
        )
    )
    fixture = CanonicalFixtureIdentity(
        canonical_fixture_id="canonical-fx", canonical_competition_id="epl",
        squad_category=SquadCategory.SENIOR_MEN,
        canonical_home_team_id="home", canonical_away_team_id="away",
        kickoff_at_utc=NOW + timedelta(hours=3),
    )
    return competition, home, away, markets, fixture


def process(raw, stored, home_alias=None, market_maps=None):
    competition, home, away, markets, fixture = mappings()
    return process_odds_event_record(
        raw, stored, (competition,),
        (home_alias,) if home_alias is not None else (home,),
        (away,), (fixture,),
        market_maps if market_maps is not None else markets,
        evaluated_at_utc=NOW,
    )


def test_full_odds_event_pipeline_links_and_maps_all_verified_markets():
    raw, stored = records()
    result = process(raw, stored)
    assert result.fixture_link.canonical_fixture_id == "canonical-fx"
    assert len(result.normalized_quotes) == 7
    assert {item.canonical_market for item in result.normalized_quotes} == {
        CanonicalMarket.ONE_X_TWO, CanonicalMarket.TOTALS, CanonicalMarket.BTTS
    }
    assert all(item.source_record_id == "stored-source-1" for item in result.normalized_quotes)


def test_unresolved_team_alias_withholds_all_event_quotes():
    raw, stored = records()
    result = process(raw, stored, home_alias=VerifiedTeamNameAlias(
        provider="The Odds API", source_id="the-odds-api",
        normalized_name="different name", canonical_team_id="home",
        squad_category=SquadCategory.SENIOR_MEN,
        state=MappingVerificationState.VERIFIED, mapping_version="v1",
        evidence_ref="other-evidence", valid_from_utc=NOW - timedelta(days=1),
        valid_to_utc=None, verified_at_utc=NOW,
    ))
    assert result.normalized_quotes == ()
    assert result.fixture_link.canonical_fixture_id is None


def test_unmapped_market_quotes_are_rejected_individually():
    raw, stored = records()
    _, _, _, all_markets, _ = mappings()
    result = process(raw, stored, market_maps=all_markets[:2])
    assert len(result.normalized_quotes) == 5
    assert len(result.rejected_quotes) == 2
    assert all(item.reason_code == "PROVIDER_MARKET_KEY_UNMAPPED" for item in result.rejected_quotes)


def test_raw_payload_digest_mismatch_blocks_processing():
    raw, stored = records()
    wrong = StoredSourceRecord(
        source_record_id="stored-source-1", payload_reference="blob://sha",
        raw_payload_sha256="f" * 64, duplicate=False,
    )
    with pytest.raises(ValueError, match="DIGEST_MISMATCH"):
        process_odds_event_record(
            raw, wrong, *mappings()[:3], (mappings()[4],), mappings()[3],
            evaluated_at_utc=NOW,
        )
