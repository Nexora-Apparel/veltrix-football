from __future__ import annotations

from datetime import date, datetime, timedelta

from app.provider_adapters import (
    FiveDollarFootballClient,
    TheOddsAPIClient,
    enrich_report_with_multi_source_odds,
    normalize_fivedollar_fixture,
    supplement_fixtures_from_odds_api,
    supplement_fixtures_from_infersports,
)


# [run-live-verification] Check mapped competition eligibility in a fresh report.
def test_brazil_serie_a_short_label_maps_to_existing_historical_division():
    from app.provider_adapters import LEAGUE_CODES

    assert LEAGUE_CODES["bra a"] == "BSA"
    assert LEAGUE_CODES["allsvenskan"] == "SWE"


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


def test_odds_api_supplements_only_future_same_day_fixtures_and_keeps_primary_rows():
    class FakeEventClient:
        api_key = "configured"

        def __init__(self):
            self.calls = []

        def events_for_sport(self, sport_key):
            self.calls.append(sport_key)
            if sport_key == "soccer_epl":
                return [
                    {
                        "id": "epl-1", "commence_time": "2026-10-29T16:00:00Z",
                        "home_team": "Arsenal", "away_team": "Chelsea",
                    },
                    {
                        "id": "duplicate-primary", "commence_time": "2026-10-29T18:00:00Z",
                        "home_team": "Frosinone", "away_team": "Lecce",
                    },
                    {
                        "id": "epl-2", "commence_time": "2026-10-30T12:00:00Z",
                        "home_team": "Tomorrow FC", "away_team": "Later FC",
                    },
                    {
                        "id": "epl-3", "commence_time": "2026-10-29T08:00:00Z",
                        "home_team": "Already Started", "away_team": "Past FC",
                    },
                ]
            return []

    client = FakeEventClient()
    payload = {
        "response": [{
            "fixture": {
                "id": "primary-1", "date": "2026-10-29T17:30:00Z",
                "status": {"short": "NS"},
            },
            "teams": {"home": {"name": "Frosinone"}, "away": {"name": "Lecce"}},
            "league": {"name": "Italy Serie A", "code": "SA"},
            "_veltrix_source": "5DollarFootballAPI",
        }],
        "_veltrix_meta": {"provider": "5DollarFootballAPI"},
    }
    now = datetime.fromisoformat("2026-10-29T10:00:00+01:00")
    result = supplement_fixtures_from_odds_api(
        payload, "2026-10-29", client=client, now=now,
    )
    rows = result["response"]
    assert len(rows) == 2
    assert rows[0]["teams"]["home"]["name"] == "Frosinone"
    added = rows[1]
    assert added["_veltrix_source"] == "The Odds API"
    assert added["fixture"]["id"] == "epl-1"
    assert added["fixture"]["status"]["short"] == "NS"
    assert added["league"]["code"] == "PL"
    assert result["_veltrix_meta"]["supplemental_fixtures_added"] == 1
    assert "soccer_epl" in client.calls


def test_odds_api_fixture_supplement_is_noop_without_key():
    class NoKeyClient:
        api_key = ""

        def events_for_sport(self, sport_key):
            raise AssertionError("must not call events endpoint without a key")

    payload = {"response": []}
    result = supplement_fixtures_from_odds_api(
        payload, "2026-10-29", client=NoKeyClient(),
    )
    assert result["response"] == []
    assert "_veltrix_meta" not in result


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
    assert prediction["five_dollar_market_odds"]["bookmakers"][0]["1x2"] == {"home": 2.0, "draw": 3.2, "away": 3.9}
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


def test_infersports_totals_are_attached_only_when_explicitly_enabled():
    class FakeInferSports:
        def __init__(self):
            self.odds_calls = []

        def events_for_date(self, day, timezone_name):
            return [{
                "id": "evt_123", "sport": "football", "status": "scheduled",
                "scheduled_at": "2026-10-29T15:00:00Z",
                "home_team": {"name": "Arsenal"}, "away_team": {"name": "Chelsea"},
                "league": {"name": "Premier League"},
            }]

        def event_odds(self, event_id):
            self.odds_calls.append(event_id)
            return {
                "event_id": event_id, "as_of": "2026-10-29T12:00:00Z", "stale": False,
                "odds": [{
                    "bookmaker": "Pinnacle", "market_type": "totals",
                    "period": "full_time", "line": 2.5, "status": "active",
                    "prices": {"over": 1.88, "under": 1.98},
                    "as_of": "2026-10-29T12:00:00Z",
                }],
            }

    report = {
        "as_of_date": "2026-10-29",
        "predictions": [{
            "fixture_id": 123, "home_team": "Arsenal", "away_team": "Chelsea",
            "kickoff_local": "2026-10-29T16:00:00+01:00", "league": "Premier League",
            "probabilities": {"over_2_5": 0.55},
        }],
    }
    fixtures = {"response": [{
        "fixture": {"id": 123, "date": "2026-10-29T15:00:00+00:00", "status": {"short": "NS"}},
        "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
    }]}
    infer = FakeInferSports()
    result = enrich_report_with_multi_source_odds(
        report, fixtures, five_dollar_client=FakeFiveDollar(),
        odds_api_client=FakeOddsAPI(), infer_sports_client=infer,
        enable_infersports=True,
    )
    attached = result["predictions"][0]["infer_sports_market_odds"]
    assert attached["provider"] == "InferSports"
    assert attached["markets"]["totals"][0]["outcomes"][0] == {"name": "Over", "price": 1.88, "point": 2.5}
    assert result["multi_source_odds_sync"]["infer_sports"]["status"] == "AVAILABLE"
    assert infer.odds_calls == ["evt_123"]


def test_infersports_is_disabled_by_default_for_safe_rollout(monkeypatch):
    monkeypatch.delenv("VELTRIX_ENABLE_INFERSports", raising=False)
    report = {"as_of_date": "2026-10-29", "predictions": [{
        "home_team": "Arsenal", "away_team": "Chelsea",
        "kickoff_local": "2026-10-29T16:00:00+01:00", "league": "Premier League",
    }]}
    fixtures = {"response": [{
        "fixture": {"id": 123, "date": "2026-10-29T15:00:00+00:00", "status": {"short": "NS"}},
        "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
    }]}
    result = enrich_report_with_multi_source_odds(
        report, fixtures, five_dollar_client=FakeFiveDollar(),
        odds_api_client=FakeOddsAPI(),
    )
    assert result["multi_source_odds_sync"]["infer_sports"]["status"] == "DISABLED"


def test_empty_past_day_is_not_marked_as_covered():
    client = FiveDollarFootballClient("test-key")

    def fake_fixtures(day, timezone="Africa/Lagos"):
        if day == "2026-10-26":
            return {"response": [], "_veltrix_meta": {"requests_made": 1}}
        return {
            "response": [{
                "fixture": {"id": 27, "date": "2026-10-27T12:00:00+00:00", "status": {"short": "FT"}},
                "teams": {"home": {"name": "Home"}, "away": {"name": "Away"}},
                "league": {"name": "Premier League", "code": "PL"},
                "goals": {"home": 1, "away": 0},
            }],
            "_veltrix_meta": {"requests_made": 1, "requests_remaining": "50"},
        }

    client.fixtures = fake_fixtures
    result = client.fixtures_between("2026-10-26", "2026-10-27")
    meta = result["_veltrix_meta"]
    assert meta["successful_dates"] == ["2026-10-27"]
    assert meta["failed_dates"] == ["2026-10-26"]
    assert meta["empty_response_dates"] == ["2026-10-26"]
    assert "retryable" in meta["warning"]



# [run-live-verification] Validate source expansion against a fresh live fixture report.
def test_infersports_fixture_supplement_adds_only_future_same_day_and_deduplicates():
    class FakeInfer:
        def __init__(self):
            self.calls = []
        def events_for_date(self, day, timezone_name):
            self.calls.append((day, timezone_name))
            return [
                {"id": "new-1", "scheduled_at": "2026-10-29T16:00:00Z",
                 "home_team": {"name": "Arsenal"}, "away_team": {"name": "Chelsea"},
                 "competition": {"id": 39, "name": "Premier League"}},
                {"id": "dup", "scheduled_at": "2026-10-29T17:00:00Z",
                 "home_team": "Frosinone", "away_team": "Lecce",
                 "league": {"name": "Serie A"}},
                {"id": "tomorrow", "scheduled_at": "2026-10-30T12:00:00Z",
                 "home_team": "Tomorrow FC", "away_team": "Later FC",
                 "league": {"name": "Premier League"}},
                {"id": "past", "scheduled_at": "2026-10-29T08:00:00Z",
                 "home_team": "Past FC", "away_team": "Old FC",
                 "league": {"name": "Premier League"}},
            ]
    payload = {"response": [{
        "fixture": {"id": 10, "date": "2026-10-29T18:00:00Z", "status": {"short": "NS"}},
        "teams": {"home": {"name": "Frosinone"}, "away": {"name": "Lecce"}},
        "league": {"name": "Serie A", "code": "SA"},
    }], "_veltrix_meta": {"provider": "5DollarFootballAPI"}}
    client = FakeInfer()
    result = supplement_fixtures_from_infersports(
        payload, "2026-10-29", client=client,
        now=datetime.fromisoformat("2026-10-29T10:00:00+01:00"),
    )
    assert len(result["response"]) == 2
    added = result["response"][1]
    assert added["_veltrix_source"] == "InferSports"
    assert added["teams"]["home"]["name"] == "Arsenal"
    assert added["league"]["code"] == "PL"
    assert result["_veltrix_meta"]["infersports_fixture_discovery"] == {
        "status": "AVAILABLE", "events_received": 4, "future_same_day_events": 2,
        "duplicates_skipped": 1, "fixtures_added": 1, "error_type": None,
    }
    assert client.calls == [("2026-10-29", "Africa/Lagos")]


def test_infersports_fixture_supplement_failure_keeps_primary_fixtures():
    from app.provider_adapters import ProviderAPIError
    class BrokenInfer:
        def events_for_date(self, day, timezone_name):
            raise ProviderAPIError("unavailable")
    payload = {"response": [{"fixture": {"id": 1}, "teams": {}}]}
    result = supplement_fixtures_from_infersports(
        payload, "2026-10-29", client=BrokenInfer(),
        now=datetime.fromisoformat("2026-10-29T10:00:00+01:00"),
    )
    assert len(result["response"]) == 1
    assert result["_veltrix_meta"]["infersports_fixture_discovery"]["status"] == "FAILED"


def test_fivedollar_1x2_only_odds_are_not_discarded():
    class Only1X2:
        api_key = "configured"
        def fixture_odds(self, fixture_id):
            return {"data": {"bookmakers": [{
                "name": "Book A",
                "odds": {"1x2": {"closing": {"home": 2.0, "draw": 3.2, "away": 3.9}}},
            }]}}

    class NoOddsAPI:
        api_key = ""

    report = {"predictions": [{
        "home_team": "Arsenal", "away_team": "Chelsea",
        "kickoff_local": "2026-10-29T16:00:00+01:00",
        "status": "EXPERIMENTAL_ONLY",
        "probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.20},
    }]}
    fixtures = {"response": [{
        "fixture": {"id": 123, "date": "2026-10-29T15:00:00+00:00", "status": {"short": "NS"}},
        "teams": {"home": {"name": "Arsenal"}, "away": {"name": "Chelsea"}},
    }]}
    result = enrich_report_with_multi_source_odds(
        report, fixtures, five_dollar_client=Only1X2(), odds_api_client=NoOddsAPI()
    )
    prediction = result["predictions"][0]
    assert prediction["five_dollar_market_odds"]["bookmakers"][0]["1x2"] == {
        "home": 2.0, "draw": 3.2, "away": 3.9,
    }
    assert result["multi_source_odds_sync"]["five_dollar"]["status"] == "AVAILABLE"
