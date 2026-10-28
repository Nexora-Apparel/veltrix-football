from datetime import date, timedelta

from app.goal_market_backtest import chronological_goal_market_backtest


def _matches(count=180):
    rows = []
    start = date(2024, 1, 1)
    for i in range(count):
        rows.append({
            "match_date": (start + timedelta(days=i)).isoformat(),
            "division": "L1",
            "home_team": "Alpha" if i % 2 == 0 else "Beta",
            "away_team": "Beta" if i % 2 == 0 else "Alpha",
            "home_goals": 2 if i % 4 else 0,
            "away_goals": 1 if i % 3 else 0,
        })
    return rows


def test_goal_market_backtest_reports_btts_and_totals():
    result = chronological_goal_market_backtest(_matches(), min_training_matches=50)
    assert result["test_matches"] > 0
    assert result["first_test_date"] > "2024-02-19"
    assert set(result["markets"]) == {
        "btts_yes", "btts_no", "over_1_5", "under_1_5",
        "over_2_5", "under_2_5", "over_3_5", "under_3_5",
    }
    for market in result["markets"].values():
        for model in ("model", "historical_rate_baseline"):
            metrics = market[model]
            assert metrics["matches"] == result["test_matches"]
            assert 0 <= metrics["accuracy"] <= 1
            assert 0 <= metrics["brier_score"] <= 1
            assert metrics["log_loss"] >= 0


def test_same_day_results_do_not_leak_into_same_day_forecasts():
    rows = _matches(80)
    target_day = (date(2024, 1, 1) + timedelta(days=80)).isoformat()
    day_matches = [
        {
            "match_date": target_day, "division": "L1",
            "home_team": "Alpha", "away_team": "Beta",
            "home_goals": 4, "away_goals": 0,
        },
        {
            "match_date": target_day, "division": "L1",
            "home_team": "Gamma", "away_team": "Delta",
            "home_goals": 1, "away_goals": 1,
        },
    ]
    changed = [{**day_matches[0], "home_goals": 0, "away_goals": 5}, day_matches[1]]
    first = chronological_goal_market_backtest(rows + day_matches, min_training_matches=50)
    second = chronological_goal_market_backtest(rows + changed, min_training_matches=50)

    def target(report):
        return next(p for p in report["predictions"] if p["match_date"] == target_day and p["home_team"] == "Gamma")

    assert target(first)["model"] == target(second)["model"]
    assert target(first)["baseline"] == target(second)["baseline"]
