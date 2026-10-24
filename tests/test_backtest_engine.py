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
    live = result["live_pipeline"]
    assert live["model"] == "experimental_recent_goals_poisson"
    assert live["matches"] > 0
    assert live["first_test_date"] >= "2024-01-01"
    assert live["metrics"]["brier_score"] >= 0
    assert live["recent_holdout"]["matches"] > 0
    assert result["models"]["poisson"]["matches"] == result["test_matches"]
    assert result["models"]["elo"]["brier_score"] >= 0
    holdout = result["recent_holdout"]
    assert holdout["matches"] > 0
    assert holdout["start_date"] <= holdout["end_date"]
    assert holdout["matches"] <= result["test_matches"]
    assert set(holdout["models"]) == {"poisson", "elo"}


def test_market_reference_is_reported_on_covered_fixtures():
    from datetime import date, timedelta
    matches = []
    start = date(2025, 1, 1)
    for i in range(130):
        matches.append({
            "match_date": (start + timedelta(days=i)).isoformat(),
            "division": "L1", "home_team": "Alpha", "away_team": "Beta",
            "home_goals": 2 if i % 2 else 0, "away_goals": 0 if i % 2 else 1,
            "home_odds": 2.0, "draw_odds": 3.2, "away_odds": 4.0,
        })
    result = chronological_backtest(matches, min_training_matches=50)
    subset = result["historical_odds_subset"]
    assert subset["matches_with_valid_1x2_odds"] == result["test_matches"]
    assert set(subset["models_compared_on_same_matches"]) == {"poisson", "elo", "market"}
    assert subset["models_compared_on_same_matches"]["market"]["matches"] == result["test_matches"]
    holdout_market = result["recent_holdout"]["historical_odds_subset"]
    assert holdout_market["matches_with_valid_1x2_odds"] == result["recent_holdout"]["matches"]
    live = result["live_pipeline"]
    assert live["historical_odds_subset"]["matches_with_valid_1x2_odds"] == live["matches"]
    assert set(live["historical_odds_subset"]["models_compared_on_same_matches"]) == {"live_poisson", "market"}
    assert set(holdout_market["models_compared_on_same_matches"]) == {"poisson", "elo", "market"}
    for model in ("poisson", "elo", "market"):
        calibration = subset["models_compared_on_same_matches"][model]["calibration"]
        assert set(calibration) == {"H", "D", "A"}
        for outcome in calibration.values():
            assert 0 <= outcome["expected_calibration_error"] <= 1
            assert outcome["reliability_bins"]



def test_match_normalizer_rejects_fractional_or_invalid_scores():
    from app.backtest_engine import _normalize_match
    base = {
        "match_date": "2025-01-01",
        "division": "L1",
        "home_team": "Alpha",
        "away_team": "Beta",
        "home_goals": 2,
        "away_goals": 1,
    }
    assert _normalize_match(base)["home_goals"] == 2
    for bad_value in (1.5, -1, "NaN", "inf", "not-a-score"):
        assert _normalize_match({**base, "home_goals": bad_value}) is None
        assert _normalize_match({**base, "away_goals": bad_value}) is None
