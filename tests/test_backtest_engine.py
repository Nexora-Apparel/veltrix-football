from app.backtest_engine import chronological_backtest, poisson_1x2


def test_poisson_probabilities_sum_to_one():
    probabilities = poisson_1x2(1.4, 0.9)
    assert set(probabilities) == {"H", "D", "A"}
    assert abs(sum(probabilities.values()) - 1.0) < 1e-10
    assert all(0 <= value <= 1 for value in probabilities.values())


def test_backtest_predicts_only_after_training_and_is_deterministic():
    matches = []
    # One match per date keeps the chronology explicit.
    from datetime import date, timedelta
    start = date(2024, 1, 1)
    for i in range(160):
        matches.append({
            "match_date": (start + timedelta(days=i)).isoformat(),
            "division": "L1",
            "home_team": "Alpha" if i % 2 == 0 else "Beta",
            "away_team": "Beta" if i % 2 == 0 else "Alpha",
            "home_goals": 2 if i % 3 else 0,
            "away_goals": 0 if i % 3 else 1,
        })
    result = chronological_backtest(matches, min_training_matches=50)
    assert result["test_matches"] > 0
    assert result["first_test_date"] > matches[49]["match_date"]
    assert set(result["models"]) == {"poisson", "elo"}
    assert result["models"]["poisson"]["matches"] == result["test_matches"]
    assert result["models"]["elo"]["brier_score"] >= 0
