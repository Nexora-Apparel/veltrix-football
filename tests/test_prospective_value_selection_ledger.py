import unittest

from app.bookmaker_odds_evidence import (
    append_odds_observations, build_odds_observation,
)
from app.prospective_value_selection_ledger import (
    ProspectiveValueLedgerError, append_prospective_selections,
    export_settled_certification_rows, settle_prospective_selection,
)


POLICY = {
    "policy_id": "veltrix-paper-edge-v1",
    "policy_version": "1.0.0",
    "allowed_bookmakers": ["book-a"],
    "min_model_probability": 0.45,
    "min_edge": 0.05,
    "min_expected_return": 0.05,
    "min_odds_decimal": 1.5,
    "max_odds_decimal": 4.0,
    "stake_units": 1.0,
}

PROBABILITIES = {
    "1x2": {"home": 0.7, "draw": 0.2, "away": 0.1},
    "btts": {"no": 0.3, "yes": 0.7},
    "over_2_5": {"no": 0.35, "yes": 0.65},
}

PRICES = {
    "1x2": {"home": 2.0, "draw": 4.0, "away": 5.0},
    "btts": {"no": 2.0, "yes": 2.0},
    "over_2_5": {"no": 2.0, "yes": 2.0},
}


def odds_ledger(captured_at="2026-11-10T10:30:00Z"):
    observations = []
    for market, prices in PRICES.items():
        observations.append(build_odds_observation(
            provider="the_odds_api", provider_event_id="event-1",
            fixture_id="fixture-1", market=market, bookmaker="book-a",
            captured_at=captured_at, kickoff_at="2026-11-10T12:00:00Z",
            decimal_odds=prices, raw_payload={"event": "event-1", "market": market},
            source_payload_sha256="a" * 64,
            crosswalk_evidence_sha256="b" * 64,
        ))
    return append_odds_observations(
        {"schema_version": 1, "observations": []}, observations,
    )["ledger"]


def prediction(probabilities=None):
    return {
        "fixture_id": "fixture-1",
        "kickoff_at": "2026-11-10T12:00:00Z",
        "prediction_as_of": "2026-11-10T09:00:00Z",
        "decision_at": "2026-11-10T11:00:00Z",
        "model_sha256": "c" * 64,
        "feature_snapshot_sha256": "d" * 64,
        "probabilities": probabilities or PROBABILITIES,
    }


class ProspectiveValueSelectionLedgerTests(unittest.TestCase):
    def test_requires_explicit_policy(self):
        with self.assertRaisesRegex(ProspectiveValueLedgerError, "policy_shape_invalid"):
            append_prospective_selections(
                ledger={"schema_version": 1, "selections": [], "settlements": []},
                predictions=[prediction()], odds_ledger=odds_ledger(), policy={},
            )

    def test_creates_paper_only_selections_and_exports_settled_rows(self):
        result = append_prospective_selections(
            ledger={"schema_version": 1, "selections": [], "settlements": []},
            predictions=[prediction()], odds_ledger=odds_ledger(), policy=POLICY,
        )
        ledger = result["ledger"]
        self.assertEqual(result["added_count"], 3)
        self.assertEqual(len(ledger["selections"]), 3)
        self.assertEqual(result["real_money_orders"], 0)
        self.assertEqual(result["database_writes"], 0)
        self.assertEqual({row["market"] for row in ledger["selections"]},
                         {"1x2", "btts", "over_2_5"})
        for selection in list(ledger["selections"]):
            settled = settle_prospective_selection(
                ledger=ledger,
                selection_id=selection["selection_id"],
                actual=selection["selection"],
                settled_at="2026-11-10T14:00:00Z",
                settlement_source_evidence_sha256="e" * 64,
            )
            ledger = settled["ledger"]
        exported = export_settled_certification_rows(
            ledger=ledger, evaluated_at="2026-11-11T00:00:00Z",
        )
        self.assertEqual(exported["settled_selection_count"], 3)
        for market in ("1x2", "btts", "over_2_5"):
            row = exported["prospective"][market][0]
            self.assertEqual(row["fixture_id"], "fixture-1")
            self.assertEqual(row["settlement_source_evidence_sha256"], "e" * 64)
            self.assertEqual(row["odds_source_evidence_sha256"], "a" * 64)
            self.assertEqual(row["stake_units"], 1.0)

    def test_selection_append_is_idempotent(self):
        first = append_prospective_selections(
            ledger={"schema_version": 1, "selections": [], "settlements": []},
            predictions=[prediction()], odds_ledger=odds_ledger(), policy=POLICY,
        )
        second = append_prospective_selections(
            ledger=first["ledger"], predictions=[prediction()],
            odds_ledger=odds_ledger(), policy=POLICY,
        )
        self.assertEqual(first["added_count"], 3)
        self.assertEqual(second["added_count"], 0)
        self.assertEqual(len(second["ledger"]["selections"]), 3)

    def test_rejects_quote_not_available_at_decision_time(self):
        result = append_prospective_selections(
            ledger={"schema_version": 1, "selections": [], "settlements": []},
            predictions=[prediction()],
            odds_ledger=odds_ledger(captured_at="2026-11-10T11:30:00Z"),
            policy=POLICY,
        )
        self.assertEqual(result["added_count"], 0)

    def test_rejects_conflicting_second_selection_for_same_fixture_market(self):
        first = append_prospective_selections(
            ledger={"schema_version": 1, "selections": [], "settlements": []},
            predictions=[prediction()], odds_ledger=odds_ledger(), policy=POLICY,
        )
        changed = prediction()
        changed["probabilities"]["1x2"]["home"] = 0.75
        changed["probabilities"]["1x2"]["draw"] = 0.15
        changed["probabilities"]["1x2"]["away"] = 0.10
        with self.assertRaisesRegex(ProspectiveValueLedgerError, "selection_conflict"):
            append_prospective_selections(
                ledger=first["ledger"], predictions=[changed],
                odds_ledger=odds_ledger(), policy=POLICY,
            )

    def test_rejects_settlement_before_kickoff_and_conflicting_settlement(self):
        first = append_prospective_selections(
            ledger={"schema_version": 1, "selections": [], "settlements": []},
            predictions=[prediction()], odds_ledger=odds_ledger(), policy=POLICY,
        )
        sid = first["ledger"]["selections"][0]["selection_id"]
        with self.assertRaisesRegex(ProspectiveValueLedgerError, "not_after_kickoff"):
            settle_prospective_selection(
                ledger=first["ledger"], selection_id=sid, actual="home",
                settled_at="2026-11-10T11:59:00Z",
                settlement_source_evidence_sha256="e" * 64,
            )
        settled = settle_prospective_selection(
            ledger=first["ledger"], selection_id=sid, actual="home",
            settled_at="2026-11-10T14:00:00Z",
            settlement_source_evidence_sha256="e" * 64,
        )
        idempotent = settle_prospective_selection(
            ledger=settled["ledger"], selection_id=sid, actual="home",
            settled_at="2026-11-10T14:00:00Z",
            settlement_source_evidence_sha256="e" * 64,
        )
        self.assertFalse(idempotent["added"])
        with self.assertRaisesRegex(ProspectiveValueLedgerError, "already_settled_conflict"):
            settle_prospective_selection(
                ledger=settled["ledger"], selection_id=sid, actual="away",
                settled_at="2026-11-10T14:00:00Z",
                settlement_source_evidence_sha256="f" * 64,
            )

    def test_rejects_tampered_selection_value_record(self):
        first = append_prospective_selections(
            ledger={"schema_version": 1, "selections": [], "settlements": []},
            predictions=[prediction()], odds_ledger=odds_ledger(), policy=POLICY,
        )
        first["ledger"]["selections"][0]["edge"] = 0.99
        with self.assertRaisesRegex(ProspectiveValueLedgerError, "value_integrity_mismatch"):
            export_settled_certification_rows(
                ledger=first["ledger"], evaluated_at="2026-11-11T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
