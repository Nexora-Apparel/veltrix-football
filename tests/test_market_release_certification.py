import unittest
from datetime import date, timedelta

from app.market_release_certification import (
    CertificationError, evaluate_market_release_certification,
)

CLASSES = {
    "1x2": ("home", "draw", "away"),
    "btts": ("no", "yes"),
    "over_2_5": ("no", "yes"),
}


def evidence_fixture(walk_count=1000, prospective_count=300):
    evidence = {}
    for market, classes in CLASSES.items():
        walk = []
        for i in range(walk_count):
            actual = classes[i % len(classes)]
            day = (date(2026, 1, 1) + timedelta(days=i % 100)).isoformat()
            walk.append({
                "fixture_id": f"{market}-wf-{i}",
                "kickoff_at": f"{day}T12:00:00+01:00",
                "label_available_at": f"{day}T14:00:00+01:00",
                "target": actual,
                "probabilities": {
                    outcome: (0.8 if outcome == actual else 0.2 / (len(classes) - 1))
                    for outcome in classes
                },
                "bookmaker_odds_at": f"{day}T10:00:00+01:00",
                "bookmaker_odds_decimal": {outcome: float(len(classes)) for outcome in classes},
            })
        prospective = []
        for i in range(prospective_count):
            day = (date(2026, 1, 1) + timedelta(days=i % 100)).isoformat()
            selected = classes[i % len(classes)]
            prospective.append({
                "fixture_id": f"{market}-prospective-{i}",
                "kickoff_at": f"{day}T12:00:00+01:00",
                "settled_at": f"{day}T14:00:00+01:00",
                "odds_captured_at": f"{day}T10:00:00+01:00",
                "selection": selected,
                "actual": selected,
                "odds_decimal": 2.1,
                "stake_units": 1.0,
            })
        evidence[market] = {"walk_forward": walk, "prospective": prospective}
    return evidence


class MarketReleaseCertificationTests(unittest.TestCase):
    def test_all_market_thresholds_and_1x2_benchmarks_can_pass(self):
        report = evaluate_market_release_certification(
            evidence=evidence_fixture(),
            evaluated_at="2026-11-10T20:00:00Z",
        )
        self.assertTrue(report["all_markets_certified"])
        self.assertTrue(report["value_betting_authorized"])
        self.assertFalse(report["publication_authorized"])
        self.assertTrue(report["human_release_approval_required"])
        for market in CLASSES:
            result = report["markets"][market]
            self.assertEqual(result["walk_forward_fixture_count"], 1000)
            self.assertEqual(result["prospective_selection_count"], 300)
            self.assertEqual(result["timestamped_odds_coverage"], 1.0)
            self.assertGreater(result["net_roi_ci_95"]["lower_95"], 0.0)
        self.assertTrue(report["markets"]["1x2"]["checks"]["beats_bookmaker_brier"])
        self.assertTrue(report["markets"]["1x2"]["checks"]["beats_bookmaker_log_loss"])

    def test_shortfall_keeps_everything_locked(self):
        evidence = evidence_fixture(walk_count=999, prospective_count=299)
        report = evaluate_market_release_certification(
            evidence=evidence, evaluated_at="2026-11-10T20:00:00Z",
        )
        self.assertFalse(report["all_markets_certified"])
        self.assertFalse(report["value_betting_authorized"])
        self.assertFalse(report["publication_authorized"])
        self.assertFalse(report["markets"]["btts"]["checks"]["walk_forward_fixtures"])
        self.assertFalse(report["markets"]["over_2_5"]["checks"]["prospective_selections"])

    def test_rejects_walk_forward_label_not_yet_available_at_evaluation(self):
        evidence = evidence_fixture()
        evidence["1x2"]["walk_forward"][0]["label_available_at"] = "2026-11-11T14:00:00Z"
        with self.assertRaisesRegex(CertificationError, "after_evaluation"):
            evaluate_market_release_certification(
                evidence=evidence, evaluated_at="2026-11-10T20:00:00Z",
            )

    def test_rejects_odds_captured_after_kickoff(self):
        evidence = evidence_fixture()
        evidence["1x2"]["walk_forward"][0]["bookmaker_odds_at"] = "2026-01-01T13:00:00+01:00"
        with self.assertRaisesRegex(CertificationError, "odds_after_kickoff"):
            evaluate_market_release_certification(
                evidence=evidence, evaluated_at="2026-11-10T20:00:00Z",
            )

    def test_rejects_duplicate_fixture_ids(self):
        evidence = evidence_fixture()
        evidence["btts"]["prospective"][1]["fixture_id"] = evidence["btts"]["prospective"][0]["fixture_id"]
        with self.assertRaisesRegex(CertificationError, "prospective_fixture_identity_invalid"):
            evaluate_market_release_certification(
                evidence=evidence, evaluated_at="2026-11-10T20:00:00Z",
            )

    def test_rejects_timezone_naive_timestamps(self):
        evidence = evidence_fixture()
        evidence["over_2_5"]["prospective"][0]["settled_at"] = "2026-01-01T14:00:00"
        with self.assertRaisesRegex(CertificationError, "timezone_missing"):
            evaluate_market_release_certification(
                evidence=evidence, evaluated_at="2026-11-10T20:00:00Z",
            )

    def test_rejects_future_evaluation_timestamp_format(self):
        with self.assertRaisesRegex(CertificationError, "evaluated_at_timezone_missing"):
            evaluate_market_release_certification(
                evidence=evidence_fixture(), evaluated_at="2026-11-10T20:00:00",
            )


if __name__ == "__main__":
    unittest.main()
