import copy
import unittest
from datetime import date, timedelta

from app.value_bet_certification import (
    ValueBetCertificationError,
    certify_value_bet_markets,
    validate_value_bet_certification_report,
)


def synthetic_records():
    records = []
    start = date(2026, 1, 1)
    odds_by_market = {
        "1x2": {"home": 2.2, "draw": 3.0, "away": 3.6},
        "btts": {"yes": 2.0, "no": 1.9},
        "over_2_5": {"yes": 2.1, "no": 1.8},
    }
    for market, odds in odds_by_market.items():
        for index in range(1000):
            day_index = index % 100
            cycle = index // 100
            local_day = start + timedelta(days=day_index)
            won = (cycle + day_index) % 5 < 3
            if market == "1x2":
                actual = "home" if won else ("draw" if cycle % 2 else "away")
                probabilities = {"home": 0.6, "draw": 0.2, "away": 0.2}
                bookmaker = dict(odds)
            else:
                actual = "yes" if won else "no"
                probabilities = None
                bookmaker = None
            selected = index < 300
            pick = "home" if market == "1x2" else "yes"
            records.append({
                "market": market,
                "fixture_id": f"{market}-{index}",
                "competition_key": "4160026622",
                "kickoff_at": f"{local_day.isoformat()}T12:00:00Z",
                "prediction_as_of": f"{local_day.isoformat()}T05:00:00Z",
                "walk_forward": True,
                "is_prospective": selected,
                "selected": selected,
                "selection": pick if selected else None,
                "stake_units": 1.0 if selected else 0.0,
                "decimal_odds": odds[pick] if selected else None,
                "odds": dict(odds),
                "odds_observed_at": f"{local_day.isoformat()}T04:45:00Z",
                "odds_retrieved_at": f"{local_day.isoformat()}T04:50:00Z",
                "settled_at": f"{local_day.isoformat()}T15:00:00Z",
                "actual_outcome": actual,
                "model_probabilities": probabilities,
                "bookmaker_odds": bookmaker,
            })
    return records


class ValueBetCertificationTests(unittest.TestCase):
    def test_all_markets_pass_only_with_complete_walk_forward_and_prospective_evidence(self):
        records = synthetic_records()
        report = certify_value_bet_markets(evaluation_records=records)
        verified = validate_value_bet_certification_report(
            report, evaluation_records=records,
        )
        self.assertTrue(verified["valid"])
        self.assertTrue(verified["value_betting_enabled"])
        for market in ("1x2", "btts", "over_2_5"):
            self.assertTrue(report["markets"][market]["certified"])
            self.assertEqual(report["markets"][market]["walk_forward_matches"], 1000)
            self.assertEqual(report["markets"][market]["prospective_settled_selections"], 300)
            self.assertEqual(report["markets"][market]["distinct_dates"], 100)
            self.assertGreater(report["markets"][market]["roi_confidence_interval_95_clustered_by_date"]["lower"], 0)
        self.assertLess(report["markets"]["1x2"]["brier"]["model"], report["markets"]["1x2"]["brier"]["bookmaker"])
        self.assertLess(report["markets"]["1x2"]["log_loss"]["model"], report["markets"]["1x2"]["log_loss"]["bookmaker"])

    def test_insufficient_walk_forward_sample_keeps_value_betting_locked(self):
        records = synthetic_records()
        records = [row for row in records if not (
            row["market"] == "btts" and row["fixture_id"] == "btts-999"
        )]
        report = certify_value_bet_markets(evaluation_records=records)
        self.assertFalse(report["value_betting_enabled"])
        self.assertFalse(report["markets"]["btts"]["certified"])
        verified = validate_value_bet_certification_report(report)
        self.assertFalse(verified["value_betting_enabled"])

    def test_future_odds_and_post_cutoff_quotes_are_rejected(self):
        records = synthetic_records()
        records[0]["odds_observed_at"] = "2026-01-01T05:01:00Z"
        with self.assertRaisesRegex(ValueBetCertificationError, "odds_temporal_order_invalid"):
            certify_value_bet_markets(evaluation_records=records)

    def test_1x2_must_beat_both_bookmaker_metrics(self):
        records = synthetic_records()
        raw = {key: 1.0 / value for key, value in {
            "home": 2.2, "draw": 3.0, "away": 3.6,
        }.items()}
        total = sum(raw.values())
        same_as_bookmaker = {key: value / total for key, value in raw.items()}
        for row in records:
            if row["market"] == "1x2":
                row["model_probabilities"] = dict(same_as_bookmaker)
        report = certify_value_bet_markets(evaluation_records=records)
        self.assertFalse(report["markets"]["1x2"]["checks"]["beats_bookmaker_brier"])
        self.assertFalse(report["markets"]["1x2"]["checks"]["beats_bookmaker_log_loss"])
        self.assertFalse(report["value_betting_enabled"])

    def test_certification_summary_cannot_be_enabled_without_source_records(self):
        report = certify_value_bet_markets(evaluation_records=synthetic_records())
        with self.assertRaisesRegex(ValueBetCertificationError, "source_records_required"):
            validate_value_bet_certification_report(report)

    def test_source_records_must_match_certification_digest(self):
        records = synthetic_records()
        report = certify_value_bet_markets(evaluation_records=records)
        changed = copy.deepcopy(records)
        changed[0]["actual_outcome"] = "away"
        with self.assertRaisesRegex(ValueBetCertificationError, "source_records_hash_mismatch"):
            validate_value_bet_certification_report(report, evaluation_records=changed)

    def test_duplicate_market_fixture_records_are_rejected(self):
        records = synthetic_records()
        records.append(copy.deepcopy(records[0]))
        with self.assertRaisesRegex(ValueBetCertificationError, "duplicate_evaluation_fixture"):
            certify_value_bet_markets(evaluation_records=records)


if __name__ == "__main__":
    unittest.main()
