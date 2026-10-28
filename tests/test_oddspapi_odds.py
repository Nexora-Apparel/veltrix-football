from app.oddspapi_odds import normalize_fixture_odds, _key


def test_team_key_normalizes_accents_and_punctuation():
    assert _key("PFC Nasaf") == "pfcnasaf"
    assert _key("São Paulo FC") == "saopaulofc"


def test_normalize_fixture_odds_extracts_btts_and_fulltime_totals():
    fixture = {"fixtureId": "fixture-1"}
    markets = [
        {"marketId": 104, "marketName": "Both Teams To Score", "period": "fulltime", "marketType": "bothteamsscore"},
        {"marketId": 1010, "marketName": "Over Under Full Time", "period": "fulltime", "handicap": 2.5, "marketType": "totals"},
        {"marketId": 10300, "marketName": "Both Teams To Score First Half", "period": "p1", "marketType": "bothteamsscore"},
    ]
    payload = {"bookmakerOdds": {"book-a": {"markets": {
        "104": {"outcomes": {
            "yes": {"outcomeName": "Yes", "players": {"1": {"active": True, "price": 1.8}}},
            "no": {"outcomeName": "No", "players": {"1": {"active": True, "price": 2.0}}},
        }},
        "1010": {"outcomes": {
            "over": {"outcomeName": "Over", "players": {"1": {"active": True, "price": 1.9}}},
            "under": {"outcomeName": "Under", "players": {"1": {"active": True, "price": 1.9}}},
        }},
        "10300": {"outcomes": {
            "yes": {"outcomeName": "Yes", "players": {"1": {"active": True, "price": 1.7}}},
            "no": {"outcomeName": "No", "players": {"1": {"active": True, "price": 2.1}}},
        }},
    }}}}
    result = normalize_fixture_odds(fixture, payload, markets)
    assert result["btts"] == [{"bookmaker": "book-a", "yes": 1.8, "no": 2.0, "market_id": "104"}]
    assert result["over_under"] == [{"bookmaker": "book-a", "line": 2.5, "over": 1.9, "under": 1.9, "market_id": "1010"}]
