from app.value_paper import prospective_value_rows, summarize_value_market_rows


def test_value_tracker_selects_one_best_edge_per_market_and_devigs_same_book():
    prediction = {
        "fixture_id": "event-1",
        "home_team": "Alpha",
        "away_team": "Beta",
        "kickoff_local": "2026-10-30T18:00:00+01:00",
        "probabilities": {"H": 0.60, "D": 0.23, "A": 0.17},
        "market_probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.20},
        "btts_yes": 0.64,
        "over_1_5": 0.82,
        "over_2_5": 0.61,
        "over_3_5": 0.39,
        "the_odds_api_market_odds": {
            "fetched_at": "2026-10-30T15:00:00Z",
            "commence_time": "2026-10-30T17:00:00Z",
            "markets": {
                "h2h": [{
                    "bookmaker": "Book A",
                    "last_update": "2026-10-30T14:55:00Z",
                    "outcomes": [
                        {"name": "Alpha", "price": 1.9},
                        {"name": "Draw", "price": 3.5},
                        {"name": "Beta", "price": 4.5},
                    ],
                }],
                "btts": [{
                    "bookmaker": "Book A",
                    "last_update": "2026-10-30T14:55:00Z",
                    "outcomes": [{"name": "Yes", "price": 1.8}, {"name": "No", "price": 2.1}],
                }],
                "totals": [{
                    "bookmaker": "Book A",
                    "last_update": "2026-10-30T14:55:00Z",
                    "outcomes": [
                        {"name": "Over", "point": 1.5, "price": 1.2},
                        {"name": "Under", "point": 1.5, "price": 5.0},
                        {"name": "Over", "point": 2.5, "price": 1.8},
                        {"name": "Under", "point": 2.5, "price": 2.1},
                        {"name": "Over", "point": 3.5, "price": 2.8},
                        {"name": "Under", "point": 3.5, "price": 1.4},
                    ],
                }],
            },
        },
    }
    rows = prospective_value_rows(prediction, {"home_goals": 2, "away_goals": 1})
    assert {row["market"] for row in rows} == {"1x2", "btts", "over_1_5", "over_2_5", "over_3_5"}
    assert len(rows) == 5
    assert all(row["odds_fetched_at"] and row["quote_updated_at"] for row in rows)
    assert all(row["devigged_market_probability"] > 0 for row in rows)
    summaries = summarize_value_market_rows(rows)
    assert summaries["1x2"]["settled_bets"] == 1
    assert summaries["1x2"]["distinct_match_dates"] == 1
    assert summaries["1x2"]["timestamped_odds_coverage"] == 1.0


def test_value_tracker_rejects_missing_or_post_kickoff_timestamps():
    prediction = {
        "fixture_id": "event-2",
        "home_team": "Alpha",
        "away_team": "Beta",
        "kickoff_local": "2026-10-30T18:00:00+01:00",
        "market_probabilities": {"H": 0.6, "D": 0.2, "A": 0.2},
        "the_odds_api_market_odds": {
            "fetched_at": "2026-10-30T18:01:00Z",
            "commence_time": "2026-10-30T17:00:00Z",
            "markets": {},
        },
    }
    assert prospective_value_rows(prediction, {"home_goals": 1, "away_goals": 0}) == []
