"""Shared feature-domain catalogue for admission and source coverage reports.

The domain map is descriptive only. Every listed feature must also exist in
FEATURE_CATALOGUE before it contributes to measured feature coverage.
"""

FEATURE_DOMAINS = {
    "team_strength_and_form": [
        "home_team_elo", "away_team_elo", "elo_difference_home",
        "home_attack_goals_rate", "home_defence_conceded_rate",
        "away_attack_goals_rate", "away_defence_conceded_rate",
        "home_attack_strength", "away_attack_strength",
        "home_defence_strength", "away_defence_strength",
        "home_form_points_rate", "away_form_points_rate",
    ],
    "competition_baselines": [
        "competition_home_goals_rate", "competition_away_goals_rate",
    ],
    "expected_goals": [
        "home_rolling_xg_for", "home_rolling_xg_against",
        "away_rolling_xg_for", "away_rolling_xg_against",
    ],
    "lineups": ["home_lineup_strength", "away_lineup_strength"],
    "fatigue_and_travel": [
        "home_rest_days", "away_rest_days", "home_travel_km", "away_travel_km",
    ],
    "market_odds": [
        "odds_home_decimal", "odds_draw_decimal", "odds_away_decimal",
        "odds_btts_yes_decimal", "odds_over_2_5_decimal",
    ],
}
