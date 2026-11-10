import unittest
from datetime import date, timedelta

from app.independent_market_models import (
    FEATURES,
    MODEL_FAMILY,
    ResultsModelError,
    fit_independent_market_models,
    predict_independent_markets,
)


def training_rows(count=120):
    rows = []
    start = date(2026, 7, 1)
    for index in range(count):
        day = start + timedelta(days=index % 90)
        home_score = (index * 3 + index // 4) % 4
        away_score = (index * 5 + index // 7) % 3
        values = {
            "home_attack_goals_rate": 1.0 + (index % 5) * 0.2,
            "home_defence_conceded_rate": 0.8 + (index % 4) * 0.15,
            "away_attack_goals_rate": 0.9 + (index % 6) * 0.17,
            "away_defence_conceded_rate": 0.85 + (index % 3) * 0.2,
            "elo_difference_home": float((index % 9) * 80 - 320),
            "home_form_points_rate": (index % 10) / 10,
            "away_form_points_rate": ((index * 3) % 10) / 10,
            "home_rest_days": float(3 + index % 6),
            "away_rest_days": float(2 + (index * 2) % 7),
            "competition_home_goals_rate": 1.4 + (index % 3) * 0.1,
            "competition_away_goals_rate": 1.1 + (index % 4) * 0.08,
        }
        rows.append({
            "fixture_id": f"fixture-{index:04d}",
            "kickoff_at": f"{day.isoformat()}T15:00:00Z",
            "feature_as_of": f"{(day - timedelta(days=1)).isoformat()}T12:00:00Z",
            "settled_at": f"{(day + timedelta(hours=1)).isoformat()}T18:00:00Z",
            "features": values,
            "home_score": home_score,
            "away_score": away_score,
            "source_record_sha256": f"{index + 1:064x}",
        })
    return rows

class IndependentMarketModelTests(unittest.TestCase):
    def fit(self, rows=None):
        return fit_independent_market_models(
            training_rows=training_rows() if rows is None else rows,
            training_cutoff_at="2026-10-01T00:00:00Z",
            trained_at="2026-10-02T00:00:00Z",
            epochs=150,
        )

    def test_fits_three_independent_market_heads_and_infers(self):
        model = self.fit()
        self.assertEqual(model["model_family"], MODEL_FAMILY)
        self.assertEqual(set(model["market_models"]), {"1x2", "btts", "over_2_5"})
        features = training_rows(1)[0]["features"]
        result = predict_independent_markets(
            model=model, features=features,
            prediction_as_of="2026-10-03T00:00:00Z",
        )
        self.assertAlmostEqual(sum(result["probabilities"]["1x2"].values()), 1.0)
        for market in ("btts", "over_2_5"):
            self.assertAlmostEqual(sum(result["probabilities"][market].values()), 1.0)
        self.assertFalse(result["publication_allowed"])
        self.assertFalse(result["value_betting_enabled"])
        self.assertFalse(result["legacy_model_dependency"])
        self.assertFalse(result["fallback_prior_used"])

    def test_rejects_rows_after_training_cutoff(self):
        rows = training_rows()
        rows[0]["kickoff_at"] = "2026-10-03T15:00:00Z"
        rows[0]["feature_as_of"] = "2026-10-02T12:00:00Z"
        rows[0]["settled_at"] = "2026-10-03T18:00:00Z"
        with self.assertRaisesRegex(ResultsModelError, "after_training_cutoff"):
            self.fit(rows)

    def test_rejects_feature_timestamp_at_or_after_kickoff(self):
        rows = training_rows()
        rows[0]["feature_as_of"] = rows[0]["kickoff_at"]
        with self.assertRaisesRegex(ResultsModelError, "temporal_order_invalid"):
            self.fit(rows)

    def test_rejects_duplicate_fixture_ids(self):
        rows = training_rows()
        rows[1]["fixture_id"] = rows[0]["fixture_id"]
        with self.assertRaisesRegex(ResultsModelError, "duplicate_training_fixture"):
            self.fit(rows)

    def test_rejects_future_model_at_prediction_time(self):
        model = self.fit()
        with self.assertRaisesRegex(ResultsModelError, "trained_after_prediction_cutoff"):
            predict_independent_markets(
                model=model, features=training_rows(1)[0]["features"],
                prediction_as_of="2026-10-01T12:00:00Z",
            )

    def test_rejects_model_digest_tampering(self):
        model = self.fit()
        model["market_models"]["btts"]["weights"][0] += 0.1
        with self.assertRaisesRegex(ResultsModelError, "model_digest_mismatch"):
            predict_independent_markets(
                model=model, features=training_rows(1)[0]["features"],
                prediction_as_of="2026-10-03T00:00:00Z",
            )

    def test_insufficient_training_sample_is_rejected(self):
        with self.assertRaisesRegex(ResultsModelError, "below_minimum"):
            self.fit(training_rows(99))


if __name__ == "__main__":
    unittest.main()
