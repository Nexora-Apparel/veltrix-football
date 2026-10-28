from __future__ import annotations

from datetime import date

from app.provider_adapters import (
    FiveDollarFootballClient,
    TheOddsAPIClient,
    enrich_report_with_multi_source_odds,
    normalize_fivedollar_fixture,
)


def test_normalize_fivedollar_fixture_to_veltrix_shape():
    row = normalize_fivedollar_fixture({
        "id": 123,
        "kickoff_utc": "2026-10-29T18:00:00+00:00",
        "status": "finished",
        "league": {"id": 39, "name": "Premier League"},
        "teams": {"home": {"id": 1, "name": "Arsenal"}, "away": {"id": 2, "name": "Chelsea"}},
        "goals": {"home": 2, "away": 1},
    })
    assert row["fixture"]["id"] == 123
    assert row["fixture"]["status"]["short"] == "FT"
    assert row["teams"]["home"]["name"] == "Arsenal"
    assert row["league"]["code"] == "PL"
    assert row["goals"] == {"home": 2, "away": 1}
    assert row["_veltrix_source"] == "5DollarFootballAPI"


def test_fivedollar_fixtures_fetch_paginates_and_converts_lagos_day():
    client = FiveDollarFootballClient("test-key")
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        page = params["page"]
        rows = [{"id": page, "kickoff_utc": "2026-10-29T12:00:00+00:00",
                 "status": "scheduled", "league": {"name": "Premier League"},
                 "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
                 "goals": {"home": None, "away": None}}]
        payload = {"data": rows, "pagination": {"has_more": page == 1}}
        return payload, {"X-RateLimit-Remaining": "55"}

    client._get = fake_get
    result = client.fixtures("2026-10-29", "Africa/Lagos")
    assert len(result["response"]) == 2
    assert result["pagination"]["pagesFetched"] == 2
    assert result["_veltrix_meta"]["requests_remaining"] == "55"
    assert calls[0][1]["start_time"] < calls[0][1]["end_time"]
    assert calls[1][1]["page"] == 2


class FakeFiveDollar:
    api_key = "configured"

    def fixture_odds(self, fixture_id):
        return {"data": {"bookmakers": [{
            "name": "Bet365",
            "odds": {
                "btts": {"closing": {"yes": 1.8, "no": 2.0}},
                "goal_line": {"closing": {"line": 2.5, "over": 1.91, "under": 1.91}},
                "goal_line_fixed": [{"line": 2.5, "closing": {"over": 1.9, "under": 1.95}}],
                "1x2": {"closing": {"home": 2.0, "draw": 3.2, "away": 3.9}},
            },
        }]}}


class FakeOddsAPI:
    api_key = "configured"
    last_quota = {"remaining": "480", "used": "20", "last_cost": "1"}

    def __init__(self):
        self.odds_calls = []
        self.btts_calls = []

    def odds_for_sport(self, sport_key, *, regions, markets):
        self.odds_calls.append((sport_key, regions, markets))
        return [{
            "id": "event-1", "sport_key": sport_key,
            "commence_time": "2026-10-29T15:00:00Z",
            "home_team": "Arsenal", "away_team": "Chelsea",
            "bookmakers": [{
                "key": "book-a", "title": "Book A",
                "markets": [
                    {"key": "h2h", "last_update": "2026-10-29T12:00:00Z", "outcomes": [
                        {"name": "Arsenal", "price": 2.0}, {"name": "Draw", "price": 3.2}, {"name": "Chelsea", "price": 3.9}]},
                    {"key": "totals", "last_update": "2026-10-29T12:00:00Z", "outcomes": [
                        {"name": "Over", "price": 1.9, "point": 2.5}, {"name": "Under", "price": 1.95, "point": 2.5}]},
                ],
            }],
        }]

    def event_btts(self, sport_key, event_id, *, regions):
        self.btts_calls.append((sport_key, event_id, regions))
        return [{
            "id": event_id, "sport_key": sport_key,
            "commence_time": "2026-10-29T15:00:00Z",
            "home_team": "Arsenal", "away_team": "Chelsea",
            "bookmakers": [{
                "key": "book-a", "title": "Book A",
                "markets": [{"key": "btts", "last_update": "2026-10-29T12:00:00Z", "outcomes": [
                    {"name": "Yes", "price": 1.8}, {"name": "No", "price": 2.0}]}],
            }],
        }]


def test_multi_source_odds_enrichment_attaches_btts_and_totals_without_changing_model():
    report = {
        "as_of_date": "2026-10-29",
        "predictions": [{
            "fixture_id": 123, "home_team": "Arsenal", "away_team": "Chelsea",
            "kickoff_local": "2026-10-29T16:00:00+01:00", "league": "Premier League",
            "status": "EXPERIMENTAL_ONLY", "probabilities": {"btts_yes": 0.61},
        }],
    }
    fixtures = {"response": [{
        "fixture": {"id": 123, "date": "2026-10-29T15:00:00+00:00", "status": {"short": "NS"}},
        "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
    }]}
    odds_api = FakeOddsAPI()
    result = enrich_report_with_multi_source_odds(
        report, fixtures, five_dollar_client=FakeFiveDollar(),
        odds_api_client=odds_api, max_btts_events=1,
    )
    prediction = result["predictions"][0]
    assert prediction["probabilities"]["btts_yes"] == 0.61
    assert prediction["fixture_source"] == "5DollarFootballAPI"
    assert prediction["source_fixture_id"] == 123
    assert prediction["five_dollar_market_odds"]["bookmakers"][0]["btts"] == {"yes": 1.8, "no": 2.0}
    assert prediction["five_dollar_market_odds"]["bookmakers"][0]["over_under"]["line"] == 2.5
    assert prediction["the_odds_api_market_odds"]["markets"]["totals"]
    assert prediction["the_odds_api_market_odds"]["markets"]["btts"]
    assert result["multi_source_odds_sync"]["five_dollar"]["status"] == "AVAILABLE"
    assert result["multi_source_odds_sync"]["the_odds_api"]["status"] == "AVAILABLE"
    assert len(odds_api.odds_calls) == 1
    assert len(odds_api.btts_calls) == 1


def test_no_fixtures_does_not_spend_supplemental_odds_quota():
    class MustNotCall:
        api_key = "configured"
        last_quota = {}

        def odds_for_sport(self, *args, **kwargs):
            raise AssertionError("Should not call odds endpoint with no fixtures")

    report = {"predictions": []}
    result = enrich_report_with_multi_source_odds(report, {"response": []}, odds_api_client=MustNotCall())
    assert result["multi_source_odds_sync"]["the_odds_api"]["status"] == "SKIPPED_NO_FUTURE_FIXTURES"


def test_history_window_keeps_successful_dates_when_one_day_fails():
    from app.provider_adapters import ProviderAPIError

    client = FiveDollarFootballClient("test-key")

    def fake_fixtures(day, timezone="Africa/Lagos"):
        if day == "2026-10-27":
            raise ProviderAPIError("Provider request failed with HTTP 403.")
        return {
            "response": [{
                "fixture": {"id": int(day[-2:]), "date": day + "T12:00:00+00:00", "status": {"short": "FT"}},
                "teams": {"home": {"name": "Home"}, "away": {"name": "Away"}},
                "league": {"name": "Premier League", "code": "PL"},
                "goals": {"home": 1, "away": 0},
            }],
            "_veltrix_meta": {"requests_made": 1, "requests_remaining": "50"},
        }

    client.fixtures = fake_fixtures
    result = client.fixtures_between("2026-10-26", "2026-10-28")
    meta = result["_veltrix_meta"]
    assert result["results"] == 2
    assert meta["successful_dates"] == ["2026-10-26", "2026-10-28"]
    assert meta["failed_dates"] == ["2026-10-27"]
