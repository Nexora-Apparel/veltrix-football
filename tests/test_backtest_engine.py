from app.backtest_engine import (
    _historical_over_under_25_price_audit,
    _normalize_match,
    chronological_backtest,
    poisson_1x2,
)


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
    assert result["goal_markets"]["metrics"]["matches"] == result["test_matches"]
    assert result["goal_markets"]["recent_holdout"]["matches"] > 0
    assert set(result["goal_markets"]["metrics"]["markets"]) == {
        "btts_yes", "btts_no", "over_1_5", "under_1_5",
        "over_2_5", "under_2_5", "over_3_5", "under_3_5",
    }
    assert all(
        metrics["matches"] > 0 and 0 <= metrics["brier_score"] <= 1
        and metrics["log_loss"] >= 0 and 0 <= metrics["accuracy"] <= 1
        for metrics in result["goal_markets"]["metrics"]["markets"].values()
    )
    assert result["first_test_date"] > matches[49]["match_date"]
    assert set(result["models"]) == {"poisson", "elo"}
    live = result["live_pipeline"]
    assert live["model"] == "experimental_recent_goals_poisson"
    assert live["goal_markets"]["metrics"]["matches"] == live["matches"]
    assert live["goal_markets"]["recent_holdout"]["matches"] > 0
    assert set(live["goal_markets"]["metrics"]["markets"]) == {
        "btts_yes", "btts_no", "over_1_5", "under_1_5",
        "over_2_5", "under_2_5", "over_3_5", "under_3_5",
    }
    assert live["matches"] > 0
    dc = live["dixon_coles_alternative"]
    assert dc["model"] == "experimental_recency_weighted_dixon_coles"
    assert dc["model_validated"] is False
    assert dc["metrics"]["matches"] == live["matches"]
    assert dc["metrics"]["brier_score"] >= 0
    assert dc["metrics"]["log_loss"] >= 0
    assert live["recent_holdout"]["dixon_coles_alternative"]["metrics"]["matches"] > 0
    assert live["first_test_date"] >= "2024-01-01"
    assert live["metrics"]["brier_score"] >= 0
    assert live["recent_holdout"]["matches"] > 0
    assert live["elo_alternative"]["model"] == "experimental_elo_by_competition"
    assert live["elo_alternative"]["matches"] > 0
    assert live["elo_alternative"]["metrics"]["matches"] == live["elo_alternative"]["matches"]
    assert live["elo_alternative"]["recent_holdout"]["matches"] > 0
    assert "L1" in live["metrics_by_competition"]
    competition = live["metrics_by_competition"]["L1"]
    assert competition["live_eligible_matches"] == live["matches"]
    assert competition["poisson"]["matches"] == live["matches"]
    assert abs(competition["poisson"]["brier_score"] - live["metrics"]["brier_score"]) < 1e-12
    assert competition["elo"]["matches"] == live["elo_alternative"]["matches"]
    assert abs(competition["elo"]["brier_score"] - live["elo_alternative"]["metrics"]["brier_score"]) < 1e-12
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
    assert live["metrics_by_competition"]["L1"]["historical_odds_matches"] == live["matches"]
    assert set(live["historical_odds_subset"]["models_compared_on_same_matches"]) == {"live_poisson", "market"}
    assert set(holdout_market["models_compared_on_same_matches"]) == {"poisson", "elo", "market"}
    for model in ("poisson", "elo", "market"):
        calibration = subset["models_compared_on_same_matches"][model]["calibration"]
        assert set(calibration) == {"H", "D", "A"}
        for outcome in calibration.values():
            assert 0 <= outcome["expected_calibration_error"] <= 1
            assert outcome["reliability_bins"]


def test_same_day_results_cannot_change_another_fixture_forecast():
    from datetime import date, timedelta

    matches = []
    start = date(2024, 1, 1)
    for i in range(80):
        matches.append({
            "match_date": (start + timedelta(days=i)).isoformat(),
            "division": "L1",
            "home_team": "Alpha" if i % 2 == 0 else "Beta",
            "away_team": "Beta" if i % 2 == 0 else "Alpha",
            "home_goals": 2 if i % 3 else 0,
            "away_goals": 0 if i % 3 else 1,
        })

    target_day = (start + timedelta(days=80)).isoformat()
    same_day_matches = [
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
    changed_same_day_matches = [
        {**same_day_matches[0], "home_goals": 0, "away_goals": 5},
        same_day_matches[1],
    ]

    baseline = chronological_backtest(matches + same_day_matches, min_training_matches=50)
    changed = chronological_backtest(matches + changed_same_day_matches, min_training_matches=50)

    def target_forecast(report):
        return next(
            row for row in report["predictions"]
            if row["match_date"] == target_day and row["home_team"] == "Gamma"
        )

    baseline_forecast = target_forecast(baseline)
    changed_forecast = target_forecast(changed)
    assert baseline_forecast["poisson"] == changed_forecast["poisson"]
    assert baseline_forecast["elo"] == changed_forecast["elo"]



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



def test_backtest_dataset_provenance_pins_exact_input_bytes(tmp_path):
    import hashlib
    from scripts.run_backtest import dataset_provenance

    path = tmp_path / "matches.csv"
    path.write_bytes(b"match_date,home_team,away_team\n2024-01-01,A,B\n")
    matches = [{"match_date": "2024-01-01"}, {"match_date": "2024-02-01"}]
    provenance = dataset_provenance(path, matches)
    assert provenance["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert provenance["bytes"] == path.stat().st_size
    assert provenance["rows_loaded"] == 2
    assert provenance["first_match_date"] == "2024-01-01"
    assert provenance["last_match_date"] == "2024-02-01"



def test_goal_market_probabilities_are_valid_and_complementary():
    from app.backtest_engine import goal_market_probabilities

    markets = goal_market_probabilities(1.45, 1.05)
    assert 0 <= markets["btts_yes"] <= 1
    assert abs(markets["btts_yes"] + markets["btts_no"] - 1) < 1e-12
    for line in ("1_5", "2_5", "3_5"):
        assert abs(markets[f"over_{line}"] + markets[f"under_{line}"] - 1) < 1e-12
    assert markets["over_1_5"] >= markets["over_2_5"] >= markets["over_3_5"]



def test_goal_market_baseline_uses_prior_dates_only():
    from app.backtest_engine import _score_expanding_goal_baseline

    rows = [
        {"match_date": "2025-01-01", "home_goals": 5, "away_goals": 1},
        {"match_date": "2025-01-02", "home_goals": 0, "away_goals": 0},
        {"match_date": "2025-01-02", "home_goals": 3, "away_goals": 1},
        {"match_date": "2025-01-03", "home_goals": 0, "away_goals": 1},
    ]
    baseline = _score_expanding_goal_baseline(rows)
    assert baseline["matches"] == 4
    assert baseline["method"].startswith("expanding historical base rate")
    # Both fixtures on Jan 2 use the same pre-Jan-2 probability, regardless
    # of their same-day outcomes.
    changed = [rows[0], {**rows[1], "home_goals": 4, "away_goals": 4}, rows[2], rows[3]]
    baseline_changed = _score_expanding_goal_baseline(changed)
    assert baseline["markets"]["over_1_5"]["brier_score"] != baseline_changed["markets"]["over_1_5"]["brier_score"]


def test_goal_calibration_fits_earlier_dates_and_only_reports_later_scores():
    from datetime import date, timedelta
    from app.backtest_engine import _chronological_goal_calibration

    rows = []
    start = date(2020, 1, 1)
    for i in range(800):
        # Synthetic probabilities deliberately overconfident; all probabilities
        # are supplied before the synthetic outcome and each date remains unique.
        p = 0.8 if i % 2 else 0.2
        outcome = (i % 5 == 0) if p > 0.5 else (i % 5 != 0)
        rows.append({
            "match_date": (start + timedelta(days=i)).isoformat(),
            "home_goals": 1 if outcome else 0,
            "away_goals": 1 if outcome else 0,
            "goal_markets": {
                "btts_yes": p,
                "over_1_5": p,
                "over_2_5": p,
                "over_3_5": p,
            },
        })
    report = _chronological_goal_calibration(rows, "goal_markets")
    assert report["status"] == "DIAGNOSTIC_ONLY_NOT_APPLIED"
    assert report["calibration_cutoff_date"] == rows[640]["match_date"]
    assert report["calibration_matches"] == 640
    assert report["test_matches"] == 160
    assert set(report["markets"]) == {"btts_yes", "over_1_5", "over_2_5", "over_3_5"}
    for market in report["markets"].values():
        assert market["status"] == "CALIBRATION_FIT_EVALUATED_ON_LATER_DATES"
        assert market["raw_test"]["matches"] == 160
        assert market["calibrated_test"]["matches"] == 160
        assert 0 <= market["calibrated_test"]["brier_score"] <= 1
        assert market["calibrated_test"]["log_loss"] >= 0



def test_historical_over_under_price_audit_is_explicitly_non_validating():
    normalized = _normalize_match({
        "match_date": "2025-01-01",
        "division": "L1",
        "home_team": "Alpha",
        "away_team": "Beta",
        "home_goals": 2,
        "away_goals": 1,
        "over25_odds": 2.2,
        "under25_odds": 1.7,
    })
    assert normalized["over25_odds"] == 2.2
    assert normalized["under25_odds"] == 1.7
    audit = _historical_over_under_25_price_audit([{
        **normalized,
        "goal_markets": {"over_2_5": 0.60, "under_2_5": 0.40},
    }])
    assert audit["fixtures_with_model_and_any_valid_ou25_price"] == 1
    assert audit["selection_count"] == 1
    assert audit["wins"] == 1
    assert abs(audit["net_units"] - 1.2) < 1e-9
    assert audit["timestamp_quality"].startswith("UNVERIFIED")
    assert audit["profitability_claim_allowed"] is False
