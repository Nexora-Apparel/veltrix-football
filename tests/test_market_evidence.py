from datetime import datetime, timedelta, timezone

import pytest

from app.market_evidence import (
    binary_market_metrics, calculate_clv, capture_odds_snapshot,
    confirmed_lineup_strength, probability_distribution_audit,
    rest_travel_context, verified_xg_pair,
)

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def test_xg_requires_verified_pre_cutoff_source():
    result = verified_xg_pair(
        {"value": 1.4, "source": "licensed-xg-feed", "observed_at": NOW - timedelta(hours=1)},
        {"value": 0.8, "source": "licensed-xg-feed", "observed_at": NOW - timedelta(hours=1)},
        forecast_at=NOW,
    )
    assert result["status"] == "VERIFIED"
    late = verified_xg_pair(
        {"value": 1.4, "source": "feed", "observed_at": NOW + timedelta(minutes=1)},
        {"value": 0.8, "source": "feed", "observed_at": NOW - timedelta(hours=1)},
        forecast_at=NOW,
    )
    assert late["status"] == "REJECTED"


def test_lineups_require_exactly_eleven_confirmed_players():
    players = [{"rating": 6.5, "confirmed_starting_xi": True} for _ in range(11)]
    assert confirmed_lineup_strength(players, source="official-club", confirmed_at=NOW,
                                     forecast_at=NOW)["status"] == "VERIFIED"
    assert confirmed_lineup_strength(players[:10], source="official-club", confirmed_at=NOW,
                                     forecast_at=NOW)["status"] == "REJECTED"


def test_clv_uses_timestamped_open_and_close_quotes():
    opening = capture_odds_snapshot(fixture_id="f1", market="1X2", selection="H",
        decimal_odds=2.2, bookmaker="book", captured_at=NOW, source="odds-api")
    closing = capture_odds_snapshot(fixture_id="f1", market="1X2", selection="H",
        decimal_odds=2.0, bookmaker="book", captured_at=NOW + timedelta(hours=2), source="odds-api")
    result = calculate_clv([opening, closing])
    assert result["quotes_compared"] == 1
    assert result["records"][0]["positive_clv"] is True


def test_class_distribution_audit_flags_home_draw_imbalance():
    rows = [{"probabilities": {"H": .70, "D": .05, "A": .25}, "actual": "H"} for _ in range(50)]
    rows += [{"probabilities": {"H": .70, "D": .05, "A": .25}, "actual": "D"} for _ in range(25)]
    rows += [{"probabilities": {"H": .70, "D": .05, "A": .25}, "actual": "A"} for _ in range(25)]
    result = probability_distribution_audit(rows)
    assert result["home_overprediction"] is True
    assert result["draw_underprediction"] is True


def test_binary_market_metrics_are_proper_and_bounded():
    result = binary_market_metrics([{"probability": .8, "actual": 1}, {"probability": .2, "actual": 0}])
    assert result["matches"] == 2
    assert result["brier_score"] == pytest.approx(.04)
    assert result["log_loss"] > 0


def test_rest_and_travel_use_only_prior_dated_matches():
    previous = [{"team_id": "t1", "played_at": NOW - timedelta(days=4),
                 "venue_latitude": 51.5, "venue_longitude": -0.1},
                {"team_id": "t1", "played_at": NOW + timedelta(days=1),
                 "venue_latitude": 0, "venue_longitude": 0}]
    result = rest_travel_context(previous, "t1", NOW, 48.8, 2.3)
    assert result["rest_hours"] == 96
    assert result["matches_last_7d"] == 1
    assert result["travel_distance_km"] > 100


def test_ppda_and_shot_conversion_require_verified_inputs():
    from app.market_evidence import ppda_feature, shot_conversion_feature
    assert ppda_feature(120, 20, source="licensed-stats", observed_at=NOW,
                        forecast_at=NOW)["value"] == 6
    assert ppda_feature(120, 0, source="licensed-stats", observed_at=NOW,
                        forecast_at=NOW)["status"] == "REJECTED"
    assert shot_conversion_feature(4, 10, source="licensed-stats", observed_at=NOW,
                                   forecast_at=NOW)["value"] == .4


def test_market_experiment_keeps_markets_independent():
    from app.market_evidence import chronological_market_experiment
    rows = []
    for day in range(1, 21):
        rows.append({"match_date": f"2026-10-{day:02d}",
                     "p_1x2": {"H": .45, "D": .25, "A": .30}, "actual_1x2": "H",
                     "p_btts": .65, "actual_btts": 1,
                     "p_over25": .60, "actual_over25": 1})
    result = chronological_market_experiment(rows, {
        "1X2": {"probability_key": "p_1x2", "actual_key": "actual_1x2"},
        "BTTS": {"probability_key": "p_btts", "actual_key": "actual_btts"},
        "OVER_2_5": {"probability_key": "p_over25", "actual_key": "actual_over25"},
    }, minimum_training_matches=1, minimum_test_matches=1)
    assert set(result["markets"]) == {"1X2", "BTTS", "OVER_2_5"}
    assert all(value["evaluated_folds"] > 0 for value in result["markets"].values())
