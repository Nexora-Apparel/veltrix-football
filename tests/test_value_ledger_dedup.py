from app.paper_tracking import merge_paper_ledger


def test_market_ledger_counts_one_earliest_selection_per_fixture():
    base = {
        "matches": [],
        "fixtures_scored": 0,
        "completed_forecasts_scored": 0,
        "awaiting_result_or_match": 0,
        "withheld_or_invalid_forecasts": 0,
    }
    first = {
        **base,
        "report_date": "2026-10-28",
        "goal_market_matches": [{
            "fixture_id": "same-fixture", "market": "btts", "selection": "yes",
            "model": "v1", "odds_fetched_at": "2026-10-28T10:00:00Z",
            "quote_updated_at": "2026-10-28T09:55:00Z",
            "kickoff": "2026-10-28T18:00:00+01:00",
            "actual_outcome": True, "unit_stake": 1.0, "unit_profit": 0.8,
        }],
    }
    second = {
        **base,
        "report_date": "2026-10-29",
        "goal_market_matches": [{
            "fixture_id": "same-fixture", "market": "btts", "selection": "no",
            "model": "v2", "odds_fetched_at": "2026-10-28T11:00:00Z",
            "quote_updated_at": "2026-10-28T10:55:00Z",
            "kickoff": "2026-10-28T18:00:00+01:00",
            "actual_outcome": False, "unit_stake": 1.0, "unit_profit": -1.0,
        }],
    }
    ledger = merge_paper_ledger({}, first)
    ledger = merge_paper_ledger(ledger, second)
    assert len(ledger["goal_market_scored"]) == 1
    assert ledger["goal_market_scored"][0]["selection"] == "yes"
    assert ledger["goal_market_scored"][0]["model"] == "v1"
