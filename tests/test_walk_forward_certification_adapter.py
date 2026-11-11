import hashlib
import json
import unittest

from app.bookmaker_odds_evidence import (
    append_odds_observations, build_odds_observation,
)
from app.walk_forward_certification_adapter import (
    WalkForwardCertificationAdapterError, build_market_certification_evidence,
)


MARKETS = {
    "1x2": ({"home": 0.5, "draw": 0.25, "away": 0.25}, "home",
            {"home": 2.0, "draw": 4.0, "away": 4.0}),
    "btts": ({"no": 0.4, "yes": 0.6}, "yes", {"no": 2.5, "yes": 1.7}),
    "over_2_5": ({"no": 0.45, "yes": 0.55}, "yes", {"no": 2.2, "yes": 1.8}),
}


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode()).hexdigest()


def report_fixture():
    records = []
    for index in (1, 2):
        records.append({
            "origin_id": "origin-a",
            "fixture_id": f"fixture-{index}",
            "kickoff_at": f"2026-11-0{index}T12:00:00Z",
            "label_available_at": f"2026-11-0{index}T15:00:00Z",
            "label_source_evidence_sha256": "a" * 64,
            "feature_snapshot_sha256": "b" * 64,
            "probabilities": {market: values[0] for market, values in MARKETS.items()},
            "targets": {market: values[1] for market, values in MARKETS.items()},
        })
    binding = [{
        "origin_id": row["origin_id"],
        "fixture_id": row["fixture_id"],
        "probabilities": row["probabilities"],
        "targets": row["targets"],
    } for row in records]
    return {
        "evaluation_type": "multi_origin_chronological_walk_forward",
        "test_records_sha256": digest(binding),
        "pooled_test_records": records,
    }


def odds_ledger_fixture():
    observations = []
    for market, (_, _, prices) in MARKETS.items():
        observations.append(build_odds_observation(
            provider="the_odds_api", provider_event_id="event-1",
            fixture_id="fixture-1", market=market, bookmaker="book-a",
            captured_at="2026-11-01T10:00:00Z",
            kickoff_at="2026-11-01T12:00:00Z",
            decimal_odds=prices, raw_payload={"event": "event-1", "market": market},
            source_payload_sha256="c" * 64,
            crosswalk_evidence_sha256="d" * 64,
        ))
    return append_odds_observations(
        {"schema_version": 1, "observations": []}, observations,
    )["ledger"]


class WalkForwardCertificationAdapterTests(unittest.TestCase):
    def test_joins_walk_forward_predictions_to_named_bookmaker_quotes(self):
        report = report_fixture()
        result = build_market_certification_evidence(
            walk_forward_report=report,
            odds_ledger=odds_ledger_fixture(),
            prospective_selections={market: [] for market in MARKETS},
            benchmark_bookmaker="book-a",
        )
        evidence = result["evidence"]
        self.assertEqual(result["benchmark_bookmaker"], "book-a")
        for market in MARKETS:
            rows = evidence[market]["walk_forward"]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["fixture_id"], "fixture-1")
            self.assertIn("bookmaker_odds_decimal", rows[0])
            self.assertEqual(rows[0]["odds_source_evidence_sha256"], "c" * 64)
            self.assertEqual(rows[0]["crosswalk_source_evidence_sha256"], "d" * 64)
            self.assertEqual(rows[1]["fixture_id"], "fixture-2")
            self.assertNotIn("bookmaker_odds_decimal", rows[1])
            self.assertEqual(evidence[market]["prospective"], [])
        self.assertEqual(result["side_effects"]["provider_requests"], 0)

    def test_missing_benchmark_bookmaker_is_not_replaced_by_another_book(self):
        result = build_market_certification_evidence(
            walk_forward_report=report_fixture(),
            odds_ledger=odds_ledger_fixture(),
            prospective_selections={market: [] for market in MARKETS},
            benchmark_bookmaker="not-configured",
        )
        self.assertTrue(all(
            "bookmaker_odds_decimal" not in row
            for market in MARKETS
            for row in result["evidence"][market]["walk_forward"]
        ))

    def test_rejects_tampered_walk_forward_record_digest(self):
        report = report_fixture()
        report["pooled_test_records"][0]["targets"]["1x2"] = "away"
        with self.assertRaisesRegex(
            WalkForwardCertificationAdapterError, "records_digest_mismatch"
        ):
            build_market_certification_evidence(
                walk_forward_report=report,
                odds_ledger=odds_ledger_fixture(),
                prospective_selections={market: [] for market in MARKETS},
                benchmark_bookmaker="book-a",
            )

    def test_rejects_missing_prospective_market_partition(self):
        with self.assertRaisesRegex(
            WalkForwardCertificationAdapterError, "prospective_market_set_invalid"
        ):
            build_market_certification_evidence(
                walk_forward_report=report_fixture(),
                odds_ledger=odds_ledger_fixture(),
                prospective_selections={"1x2": []},
                benchmark_bookmaker="book-a",
            )


if __name__ == "__main__":
    unittest.main()
