"""Join sealed walk-forward test records to point-in-time odds evidence.

This is a pure adapter. It does not train, poll providers, write databases or
authorize publication; the certification evaluator applies all final gates.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.bookmaker_odds_evidence import (
    BookmakerOddsEvidenceError, latest_pre_kickoff_snapshot,
)
from app.market_release_certification import MARKETS


class WalkForwardCertificationAdapterError(ValueError):
    pass


def _digest(value: Any) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise WalkForwardCertificationAdapterError("walk_forward_report_not_canonical_json") from None
    return hashlib.sha256(encoded).hexdigest()


def build_market_certification_evidence(*, walk_forward_report: dict,
                                        odds_ledger: dict,
                                        prospective_selections: dict,
                                        benchmark_bookmaker: str) -> dict:
    """Create the exact evidence input expected by the certification evaluator.

    A single named bookmaker is used consistently for the 1X2 benchmark.
    Missing quotes remain missing; no cross-bookmaker cherry-picking occurs.
    """
    if not isinstance(walk_forward_report, dict) or walk_forward_report.get(
        "evaluation_type"
    ) != "multi_origin_chronological_walk_forward":
        raise WalkForwardCertificationAdapterError("walk_forward_report_type_invalid")
    records = walk_forward_report.get("pooled_test_records")
    if not isinstance(records, list) or not records:
        raise WalkForwardCertificationAdapterError("walk_forward_test_records_missing")
    digest_payload = [
        {
            "origin_id": row.get("origin_id"),
            "fixture_id": row.get("fixture_id"),
            "probabilities": row.get("probabilities"),
            "targets": row.get("targets"),
        }
        for row in records if isinstance(row, dict)
    ]
    if len(digest_payload) != len(records) or _digest(digest_payload) != walk_forward_report.get(
        "test_records_sha256"
    ):
        raise WalkForwardCertificationAdapterError("walk_forward_test_records_digest_mismatch")
    if not isinstance(benchmark_bookmaker, str) or not benchmark_bookmaker.strip():
        raise WalkForwardCertificationAdapterError("benchmark_bookmaker_required")
    if not isinstance(odds_ledger, dict) or odds_ledger.get("schema_version") != 1:
        raise WalkForwardCertificationAdapterError("odds_ledger_schema_invalid")
    observations = odds_ledger.get("observations")
    if not isinstance(observations, list):
        raise WalkForwardCertificationAdapterError("odds_ledger_observations_invalid")
    # This adapter's contract is specifically the qualified The Odds API
    # response archive. Other providers require separate qualification.
    filtered_ledger = {
        "schema_version": 1,
        "observations": [
            item for item in observations
            if isinstance(item, dict) and item.get("provider") == "the_odds_api"
        ],
    }
    if not isinstance(prospective_selections, dict) or set(prospective_selections) != set(MARKETS):
        raise WalkForwardCertificationAdapterError("prospective_market_set_invalid")

    output = {}
    for market in MARKETS:
        walk_rows = []
        for record in records:
            if not isinstance(record, dict):
                raise WalkForwardCertificationAdapterError("walk_forward_record_invalid")
            try:
                probabilities = record["probabilities"][market]
                target = record["targets"][market]
                fixture_id = record["fixture_id"]
                kickoff_at = record["kickoff_at"]
                label_available_at = record["label_available_at"]
                label_digest = record["label_source_evidence_sha256"]
            except (KeyError, TypeError):
                raise WalkForwardCertificationAdapterError(
                    f"walk_forward_record_fields_missing:{market}"
                ) from None
            row = {
                "fixture_id": fixture_id,
                "kickoff_at": kickoff_at,
                "label_available_at": label_available_at,
                "label_source_evidence_sha256": label_digest,
                "target": target,
                "probabilities": probabilities,
            }
            try:
                snapshot = latest_pre_kickoff_snapshot(
                    filtered_ledger,
                    fixture_id=fixture_id,
                    market=market,
                    bookmaker=benchmark_bookmaker,
                    kickoff_at=kickoff_at,
                )
            except BookmakerOddsEvidenceError as exc:
                raise WalkForwardCertificationAdapterError(
                    f"odds_snapshot_invalid:{fixture_id}:{market}:{exc}"
                ) from None
            if snapshot is not None:
                row.update({
                    "bookmaker_odds_at": snapshot["captured_at"],
                    "bookmaker_odds_decimal": snapshot["decimal_odds"],
                    "odds_source_evidence_sha256": snapshot["source_payload_sha256"],
                })
            walk_rows.append(row)
        prospective = prospective_selections[market]
        if not isinstance(prospective, list):
            raise WalkForwardCertificationAdapterError(
                f"prospective_rows_invalid:{market}"
            )
        output[market] = {
            "walk_forward": walk_rows,
            "prospective": prospective,
        }
    return {
        "evidence": output,
        "walk_forward_report_sha256": _digest(walk_forward_report),
        "odds_ledger_observation_count": len(observations),
        "benchmark_bookmaker": benchmark_bookmaker,
        "side_effects": {
            "provider_requests": 0, "database_writes": 0,
            "prediction_publications": 0, "telegram_deliveries": 0,
        },
    }
