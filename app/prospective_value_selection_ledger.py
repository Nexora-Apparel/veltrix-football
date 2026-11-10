"""Paper-only prospective value selection and settlement evidence ledger.

Selection thresholds are supplied explicitly as a versioned pre-registered
policy. No default strategy, real-money execution, persistence or publication
is provided by this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

from app.bookmaker_odds_evidence import (
    BookmakerOddsEvidenceError, latest_pre_kickoff_snapshot,
)
from app.market_probability_calibration import _time as _calibration_time
from app.market_release_certification import MARKETS


class ProspectiveValueLedgerError(ValueError):
    pass


_POLICY_KEYS = {
    "policy_id", "policy_version", "allowed_bookmakers",
    "min_model_probability", "min_edge", "min_expected_return",
    "min_odds_decimal", "max_odds_decimal", "stake_units",
}


def _canonical_hash(value: Any) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise ProspectiveValueLedgerError("payload_not_canonical_json") from None
    return hashlib.sha256(encoded).hexdigest()


def _time(value: Any, field: str) -> datetime:
    try:
        return _calibration_time(value, field)
    except ValueError as exc:
        raise ProspectiveValueLedgerError(str(exc)) from None


def _digest(value: Any, field: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)):
        raise ProspectiveValueLedgerError(f"{field}_invalid")
    return value


def validate_selection_policy(policy: Any) -> dict:
    if not isinstance(policy, dict) or set(policy) != _POLICY_KEYS:
        raise ProspectiveValueLedgerError("selection_policy_shape_invalid")
    if not isinstance(policy["policy_id"], str) or not policy["policy_id"].strip():
        raise ProspectiveValueLedgerError("selection_policy_id_invalid")
    if not isinstance(policy["policy_version"], str) or not policy["policy_version"].strip():
        raise ProspectiveValueLedgerError("selection_policy_version_invalid")
    books = policy["allowed_bookmakers"]
    if (not isinstance(books, list) or not books
            or any(not isinstance(book, str) or not book.strip() for book in books)
            or len(set(books)) != len(books)):
        raise ProspectiveValueLedgerError("selection_policy_bookmakers_invalid")
    ranges = {
        "min_model_probability": (0.0, 1.0),
        "min_edge": (0.0, 1.0),
        "min_expected_return": (0.0, 100.0),
        "min_odds_decimal": (1.000001, 1000.0),
        "max_odds_decimal": (1.000001, 1000.0),
        "stake_units": (0.000001, 1000000.0),
    }
    normalized = dict(policy)
    for field, (lower, upper) in ranges.items():
        value = policy[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProspectiveValueLedgerError(f"selection_policy_{field}_invalid")
        value = float(value)
        if not math.isfinite(value) or not lower <= value <= upper:
            raise ProspectiveValueLedgerError(f"selection_policy_{field}_out_of_range")
        normalized[field] = value
    if normalized["min_odds_decimal"] >= normalized["max_odds_decimal"]:
        raise ProspectiveValueLedgerError("selection_policy_odds_range_invalid")
    normalized["allowed_bookmakers"] = list(policy["allowed_bookmakers"])
    return {
        "policy": normalized,
        "policy_sha256": _canonical_hash(normalized),
    }


def _validate_probabilities(probabilities: Any, market: str) -> dict:
    classes = MARKETS[market]
    if not isinstance(probabilities, dict) or set(probabilities) != set(classes):
        raise ProspectiveValueLedgerError(f"prediction_market_classes_invalid:{market}")
    output = {}
    for outcome in classes:
        value = probabilities[outcome]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProspectiveValueLedgerError(f"prediction_probability_invalid:{market}:{outcome}")
        value = float(value)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ProspectiveValueLedgerError(f"prediction_probability_out_of_range:{market}:{outcome}")
        output[outcome] = value
    if abs(sum(output.values()) - 1.0) > 1e-6:
        raise ProspectiveValueLedgerError(f"prediction_probabilities_not_normalized:{market}")
    return output


def _validate_ledger(ledger: Any) -> dict:
    if not isinstance(ledger, dict) or set(ledger) != {
        "schema_version", "selections", "settlements"
    }:
        raise ProspectiveValueLedgerError("ledger_shape_invalid")
    if (ledger["schema_version"] != 1
            or not isinstance(ledger["selections"], list)
            or not isinstance(ledger["settlements"], list)):
        raise ProspectiveValueLedgerError("ledger_schema_invalid")
    seen_ids, fixture_market = set(), set()
    for item in ledger["selections"]:
        required = {
            "schema_version", "fixture_id", "market", "selection", "bookmaker",
            "odds_provider", "odds_observation_id", "odds_source_evidence_sha256",
            "odds_captured_at", "kickoff_at", "prediction_as_of", "decision_at",
            "model_sha256", "feature_snapshot_sha256", "model_probability",
            "bookmaker_probability", "decimal_odds", "edge", "expected_return",
            "stake_units", "policy_id", "policy_version", "policy_sha256",
            "selection_id",
        }
        if not isinstance(item, dict) or set(item) != required or item["schema_version"] != 1:
            raise ProspectiveValueLedgerError("selection_record_shape_invalid")
        if (not isinstance(item["market"], str) or item["market"] not in MARKETS
                or not isinstance(item["selection"], str)
                or item["selection"] not in MARKETS[item["market"]]):
            raise ProspectiveValueLedgerError("selection_record_market_invalid")
        if item["odds_provider"] != "the_odds_api":
            raise ProspectiveValueLedgerError("selection_record_provider_invalid")
        for field in ("model_sha256", "feature_snapshot_sha256",
                      "odds_source_evidence_sha256", "policy_sha256"):
            _digest(item[field], field)
        for field in ("fixture_id", "bookmaker", "policy_id", "policy_version",
                      "odds_observation_id"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ProspectiveValueLedgerError(f"selection_record_{field}_invalid")
        kickoff = _time(item["kickoff_at"], "kickoff_at")
        prediction_time = _time(item["prediction_as_of"], "prediction_as_of")
        decision_time = _time(item["decision_at"], "decision_at")
        odds_time = _time(item["odds_captured_at"], "odds_captured_at")
        if not prediction_time <= decision_time < kickoff or odds_time > decision_time:
            raise ProspectiveValueLedgerError("selection_record_time_order_invalid")
        numeric = {}
        for field in ("model_probability", "bookmaker_probability", "decimal_odds",
                      "edge", "expected_return", "stake_units"):
            value = item[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProspectiveValueLedgerError(f"selection_record_{field}_invalid")
            value = float(value)
            if not math.isfinite(value):
                raise ProspectiveValueLedgerError(f"selection_record_{field}_invalid")
            numeric[field] = value
        if (not 0 <= numeric["model_probability"] <= 1
                or not 0 <= numeric["bookmaker_probability"] <= 1
                or numeric["decimal_odds"] <= 1 or numeric["stake_units"] <= 0):
            raise ProspectiveValueLedgerError("selection_record_numeric_range_invalid")
        expected_edge = numeric["model_probability"] - numeric["bookmaker_probability"]
        expected_return = numeric["model_probability"] * numeric["decimal_odds"] - 1.0
        if (not math.isclose(numeric["edge"], expected_edge, rel_tol=1e-12, abs_tol=1e-12)
                or not math.isclose(numeric["expected_return"], expected_return,
                                    rel_tol=1e-12, abs_tol=1e-12)):
            raise ProspectiveValueLedgerError("selection_record_value_integrity_mismatch")
        selection_id = item["selection_id"]
        if not isinstance(selection_id, str) or len(selection_id) != 64:
            raise ProspectiveValueLedgerError("selection_record_digest_invalid")
        payload = {key: value for key, value in item.items() if key != "selection_id"}
        if _canonical_hash(payload) != selection_id or selection_id in seen_ids:
            raise ProspectiveValueLedgerError("selection_record_digest_invalid")
        seen_ids.add(selection_id)
        identity = (item["fixture_id"], item["market"])
        if identity in fixture_market:
            raise ProspectiveValueLedgerError("existing_fixture_market_duplicate")
        fixture_market.add(identity)

    settled_ids = set()
    for item in ledger["settlements"]:
        required = {
            "schema_version", "selection_id", "actual", "settled_at",
            "settlement_source_evidence_sha256", "settlement_id",
        }
        if not isinstance(item, dict) or set(item) != required or item["schema_version"] != 1:
            raise ProspectiveValueLedgerError("settlement_record_shape_invalid")
        if (not isinstance(item["selection_id"], str)
                or item["selection_id"] not in seen_ids
                or item["selection_id"] in settled_ids):
            raise ProspectiveValueLedgerError("settlement_record_identity_invalid")
        selection = next(row for row in ledger["selections"]
                         if row["selection_id"] == item["selection_id"])
        if item["actual"] not in MARKETS[selection["market"]]:
            raise ProspectiveValueLedgerError("settlement_record_actual_invalid")
        if _time(item["settled_at"], "settled_at") <= _time(selection["kickoff_at"], "kickoff_at"):
            raise ProspectiveValueLedgerError("settlement_record_time_invalid")
        _digest(item["settlement_source_evidence_sha256"],
                "settlement_source_evidence_sha256")
        payload = {key: value for key, value in item.items() if key != "settlement_id"}
        if (not isinstance(item["settlement_id"], str)
                or _canonical_hash(payload) != item["settlement_id"]):
            raise ProspectiveValueLedgerError("settlement_record_digest_invalid")
        settled_ids.add(item["selection_id"])
    return ledger


def _selection_record(*, prediction: dict, market: str, selection: str,
                      bookmaker: str, snapshot: dict, model_probability: float,
                      policy: dict, policy_sha256: str) -> dict:
    odds = float(snapshot["decimal_odds"][selection])
    market_probability = float(snapshot["implied_probabilities"][selection])
    edge = model_probability - market_probability
    expected_return = model_probability * odds - 1.0
    return {
        "schema_version": 1,
        "fixture_id": prediction["fixture_id"],
        "market": market,
        "selection": selection,
        "bookmaker": bookmaker,
        "odds_provider": "the_odds_api",
        "odds_observation_id": snapshot["observation_id"],
        "odds_source_evidence_sha256": snapshot["source_payload_sha256"],
        "odds_captured_at": snapshot["captured_at"],
        "kickoff_at": prediction["kickoff_at"],
        "prediction_as_of": prediction["prediction_as_of"],
        "decision_at": prediction["decision_at"],
        "model_sha256": prediction["model_sha256"],
        "feature_snapshot_sha256": prediction["feature_snapshot_sha256"],
        "model_probability": model_probability,
        "bookmaker_probability": market_probability,
        "decimal_odds": odds,
        "edge": edge,
        "expected_return": expected_return,
        "stake_units": policy["stake_units"],
        "policy_id": policy["policy_id"],
        "policy_version": policy["policy_version"],
        "policy_sha256": policy_sha256,
    }


def append_prospective_selections(*, ledger: dict, predictions: list[dict],
                                  odds_ledger: dict, policy: dict) -> dict:
    """Apply an explicit policy to already-produced forecasts and odds snapshots."""
    ledger = _validate_ledger(ledger)
    if not isinstance(predictions, list):
        raise ProspectiveValueLedgerError("predictions_must_be_list")
    validated_policy = validate_selection_policy(policy)
    policy, policy_sha256 = validated_policy["policy"], validated_policy["policy_sha256"]
    if not isinstance(odds_ledger, dict) or odds_ledger.get("schema_version") != 1:
        raise ProspectiveValueLedgerError("odds_ledger_schema_invalid")
    raw_odds = odds_ledger.get("observations")
    if not isinstance(raw_odds, list):
        raise ProspectiveValueLedgerError("odds_ledger_observations_invalid")
    provider_ledger = {
        "schema_version": 1,
        "observations": [
            item for item in raw_odds
            if isinstance(item, dict) and item.get("provider") == "the_odds_api"
        ],
    }

    selections = list(ledger["selections"])
    settlements = list(ledger["settlements"])
    seen_ids = set()
    fixture_market = set()
    for item in selections:
        if not isinstance(item, dict) or item.get("schema_version") != 1:
            raise ProspectiveValueLedgerError("existing_selection_invalid")
        selection_id = item.get("selection_id")
        if not isinstance(selection_id, str) or selection_id in seen_ids:
            raise ProspectiveValueLedgerError("existing_selection_identity_invalid")
        seen_ids.add(selection_id)
        key = (item.get("fixture_id"), item.get("market"))
        if key in fixture_market:
            raise ProspectiveValueLedgerError("existing_fixture_market_duplicate")
        fixture_market.add(key)
    settled_ids = set()
    for item in settlements:
        if not isinstance(item, dict) or item.get("schema_version") != 1:
            raise ProspectiveValueLedgerError("existing_settlement_invalid")
        sid = item.get("selection_id")
        if sid in settled_ids or sid not in seen_ids:
            raise ProspectiveValueLedgerError("existing_settlement_identity_invalid")
        settled_ids.add(sid)

    added = 0
    candidate_count = 0
    rejected: list[dict] = []
    for index, prediction in enumerate(predictions):
        if not isinstance(prediction, dict):
            rejected.append({"prediction_index": index, "reason": "prediction_not_object"})
            continue
        try:
            fixture_id = prediction["fixture_id"]
            kickoff_at = prediction["kickoff_at"]
            prediction_as_of = prediction["prediction_as_of"]
            decision_at = prediction["decision_at"]
            model_sha = _digest(prediction["model_sha256"], "model_sha256")
            feature_sha = _digest(prediction["feature_snapshot_sha256"], "feature_snapshot_sha256")
            kickoff = _time(kickoff_at, "kickoff_at")
            prediction_time = _time(prediction_as_of, "prediction_as_of")
            decision_time = _time(decision_at, "decision_at")
            if not isinstance(fixture_id, str) or not fixture_id.strip():
                raise ProspectiveValueLedgerError("fixture_id_invalid")
            if prediction_time > decision_time or decision_time >= kickoff:
                raise ProspectiveValueLedgerError("prediction_decision_time_order_invalid")
        except (KeyError, ProspectiveValueLedgerError) as exc:
            rejected.append({"prediction_index": index, "reason": str(exc)[:120]})
            continue

        for market in MARKETS:
            try:
                probs = _validate_probabilities(prediction["probabilities"][market], market)
            except (KeyError, TypeError, ProspectiveValueLedgerError) as exc:
                rejected.append({
                    "prediction_index": index, "market": market,
                    "reason": str(exc)[:120],
                })
                continue
            candidates = []
            for bookmaker in policy["allowed_bookmakers"]:
                try:
                    snapshot = latest_pre_kickoff_snapshot(
                        provider_ledger, fixture_id=fixture_id, market=market,
                        bookmaker=bookmaker, kickoff_at=kickoff_at,
                    )
                except BookmakerOddsEvidenceError as exc:
                    rejected.append({
                        "prediction_index": index, "market": market,
                        "bookmaker": bookmaker, "reason": str(exc)[:120],
                    })
                    continue
                if snapshot is None:
                    continue
                quote_time = _time(snapshot["captured_at"], "odds_captured_at")
                if quote_time > decision_time:
                    continue
                for outcome in MARKETS[market]:
                    price = float(snapshot["decimal_odds"][outcome])
                    model_p = probs[outcome]
                    market_p = float(snapshot["implied_probabilities"][outcome])
                    edge = model_p - market_p
                    expected_return = model_p * price - 1.0
                    if (
                        model_p >= policy["min_model_probability"]
                        and edge >= policy["min_edge"]
                        and expected_return >= policy["min_expected_return"]
                        and policy["min_odds_decimal"] <= price <= policy["max_odds_decimal"]
                    ):
                        candidates.append((
                            expected_return, edge, price, bookmaker, outcome, snapshot, model_p,
                        ))
            candidate_count += len(candidates)
            if not candidates:
                continue
            # Deterministic best qualifying paper quote; one selection per
            # fixture/market prevents duplicate exposure in the prospective set.
            chosen = max(candidates, key=lambda row: (
                row[0], row[1], row[2], row[3], row[4],
            ))
            _, _, _, bookmaker, outcome, snapshot, model_p = chosen
            record = _selection_record(
                prediction=prediction, market=market, selection=outcome,
                bookmaker=bookmaker, snapshot=snapshot, model_probability=model_p,
                policy=policy, policy_sha256=policy_sha256,
            )
            selection_id = _canonical_hash(record)
            record["selection_id"] = selection_id
            key = (fixture_id, market)
            if key in fixture_market:
                existing = next(item for item in selections
                                if (item["fixture_id"], item["market"]) == key)
                if existing.get("selection_id") != selection_id:
                    raise ProspectiveValueLedgerError("fixture_market_selection_conflict")
                continue
            selections.append(record)
            seen_ids.add(selection_id)
            fixture_market.add(key)
            added += 1
    return {
        "ledger": {
            "schema_version": 1,
            "selections": selections,
            "settlements": settlements,
        },
        "added_count": added,
        "candidate_count": candidate_count,
        "rejected_count": len(rejected),
        "rejected": rejected,
        "selection_policy_sha256": policy_sha256,
        "database_writes": 0,
        "real_money_orders": 0,
        "prediction_publications": 0,
        "telegram_deliveries": 0,
    }


def settle_prospective_selection(*, ledger: dict, selection_id: str,
                                actual: str, settled_at: str,
                                settlement_source_evidence_sha256: str) -> dict:
    """Append one independently sourced result settlement; never overwrite."""
    ledger = _validate_ledger(ledger)
    matches = [item for item in ledger["selections"]
               if item.get("selection_id") == selection_id]
    if len(matches) != 1:
        raise ProspectiveValueLedgerError("selection_not_found_or_ambiguous")
    selection = matches[0]
    if actual not in MARKETS[selection["market"]]:
        raise ProspectiveValueLedgerError("settlement_actual_invalid")
    settled = _time(settled_at, "settled_at")
    kickoff = _time(selection["kickoff_at"], "kickoff_at")
    if settled <= kickoff:
        raise ProspectiveValueLedgerError("settlement_not_after_kickoff")
    source_digest = _digest(
        settlement_source_evidence_sha256,
        "settlement_source_evidence_sha256",
    )
    event = {
        "schema_version": 1,
        "selection_id": selection_id,
        "actual": actual,
        "settled_at": settled.isoformat(),
        "settlement_source_evidence_sha256": source_digest,
    }
    event["settlement_id"] = _canonical_hash(event)
    existing = [item for item in ledger["settlements"]
                if item["selection_id"] == selection_id]
    if existing:
        if existing[0] == event:
            return {
                "ledger": ledger, "added": False,
                "database_writes": 0, "real_money_orders": 0,
            }
        raise ProspectiveValueLedgerError("selection_already_settled_conflict")
    return {
        "ledger": {
            "schema_version": 1,
            "selections": list(ledger["selections"]),
            "settlements": [*ledger["settlements"], event],
        },
        "added": True,
        "database_writes": 0,
        "real_money_orders": 0,
    }


def export_settled_certification_rows(*, ledger: dict, evaluated_at: str) -> dict:
    """Export the exact prospective evidence rows consumed by certification."""
    ledger = _validate_ledger(ledger)
    evaluated = _time(evaluated_at, "evaluated_at")
    settlements = {item["selection_id"]: item for item in ledger["settlements"]}
    output = {market: [] for market in MARKETS}
    for selection in ledger["selections"]:
        settlement = settlements.get(selection["selection_id"])
        if settlement is None:
            continue
        if _time(settlement["settled_at"], "settled_at") > evaluated:
            raise ProspectiveValueLedgerError("settlement_after_evaluation")
        output[selection["market"]].append({
            "fixture_id": selection["fixture_id"],
            "kickoff_at": selection["kickoff_at"],
            "settled_at": settlement["settled_at"],
            "odds_captured_at": selection["odds_captured_at"],
            "settlement_source_evidence_sha256": settlement[
                "settlement_source_evidence_sha256"
            ],
            "odds_source_evidence_sha256": selection["odds_source_evidence_sha256"],
            "selection": selection["selection"],
            "actual": settlement["actual"],
            "odds_decimal": selection["decimal_odds"],
            "stake_units": selection["stake_units"],
        })
    for market in output:
        output[market].sort(key=lambda row: (row["kickoff_at"], row["fixture_id"]))
    return {
        "prospective": output,
        "settled_selection_count": sum(len(rows) for rows in output.values()),
        "database_writes": 0,
        "real_money_orders": 0,
        "prediction_publications": 0,
        "telegram_deliveries": 0,
    }
