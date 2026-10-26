from app.bookmaker_odds import APIFootballOddsClient, BookmakerOddsError, normalize_odds_rows


def test_normalizes_btts_totals_and_bookmaker_prices():
    rows = normalize_odds_rows([{
        "match_id": "77", "match_hometeam_name": "Arsenal",
        "match_awayteam_name": "Chelsea", "match_date": "2026-10-26",
        "match_time": "18:00", "odd_bookmakers": "Example Bookmaker",
        "odd_date": "2026-10-26 09:00:00", "odd_1": "1.90", "odd_x": "3.50",
        "odd_2": "4.20", "bts_yes": "1.80", "bts_no": "2.00",
        "o+2.5": "1.95", "u+2.5": "1.85", "o+4.5": "4.50",
    }])
    assert len(rows) == 1
    assert rows[0]["bookmaker"] == "Example Bookmaker"
    assert rows[0]["odds"]["home"] == 1.90
    assert rows[0]["odds"]["yes"] == 1.80
    assert rows[0]["odds"]["over_2_5"] == 1.95
    assert rows[0]["odds"]["under_2_5"] == 1.85
    assert rows[0]["odds"]["over_4_5"] == 4.50


def test_invalid_prices_are_ignored_and_missing_fixture_identity_is_dropped():
    rows = normalize_odds_rows([
        {"match_id": "1", "match_hometeam_name": "A", "match_awayteam_name": "B",
         "match_date": "2026-10-26", "odd_1": "1.0", "odd_x": "NaN", "odd_2": "2.5"},
        {"match_id": "2", "match_hometeam_name": "A", "match_date": "2026-10-26"},
    ])
    assert len(rows) == 1
    assert rows[0]["odds"] == {"away": 2.5}


def test_client_requires_key_without_making_request():
    client = APIFootballOddsClient(api_key="")
    try:
        client.odds_for_date("2026-10-26")
    except BookmakerOddsError as exc:
        assert "APIFOOTBALL_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected missing-key error")


def test_client_sends_date_scoped_request_and_normalizes_response():
    class Response:
        status_code = 200
        def json(self):
            return [{"match_id": "8", "match_hometeam_name": "Home",
                     "match_awayteam_name": "Away", "match_date": "2026-10-26",
                     "odd_bookmakers": "Book", "bts_yes": "1.9"}]
    class Session:
        def __init__(self): self.call = None
        def get(self, url, params=None, timeout=None):
            self.call = (url, params, timeout)
            return Response()
    session = Session()
    result = APIFootballOddsClient("secret-test-key", session=session).odds_for_date("2026-10-26")
    assert session.call[0] == "https://apiv3.apifootball.com/"
    assert session.call[1]["action"] == "get_odds"
    assert session.call[1]["from"] == session.call[1]["to"] == "2026-10-26"
    assert session.call[1]["APIkey"] == "secret-test-key"
    assert result["_veltrix_meta"]["status"] == "AVAILABLE"
    assert result["response"][0]["odds"]["yes"] == 1.9
