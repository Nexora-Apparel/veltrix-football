"""Prospective-only scoring of immutable V2 paper-ledger settlements.

This module scores only linked prediction/settlement events. It does not infer
stakes, selections, odds, ROI or CLV. Those remain unavailable until separately
verified pre-kickoff price and selection evidence is stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from typing import Mapping

from veltrix_v2.ledger.paper_predictions import (
    V2_PIT_MODEL_VERSION, ProspectivePaperLedger,
)


@dataclass(frozen=True, slots=True)
class ProspectiveMarketScore:
    market: str
    sample_count: int
    distinct_dates: int
    brier_score: float | None
    log_loss: float | None
    odds_covered_selections: int
    roi: float | None
    roi_status: str
    clv: float | None
    clv_status: str


@dataclass(frozen=True, slots=True)
class ProspectiveSettlementScorecard:
    ledger_event_count: int
    prediction_count: int
    settled_prediction_count: int
    unsettled_prediction_count: int
    markets: tuple[ProspectiveMarketScore, ...]
    certification_status: str


def _safe_probability(value: object) -> float:
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0):
        raise ValueError("PROSPECTIVE_SCORE_PROBABILITY_INVALID")
    return float(value)


def _market_score(market: str, samples: list[tuple[dict, str, datetime]]) -> ProspectiveMarketScore:
    if not samples:
        return ProspectiveMarketScore(
            market=market, sample_count=0, distinct_dates=0,
            brier_score=None, log_loss=None, odds_covered_selections=0,
            roi=None, roi_status="NOT_COMPUTABLE_NO_SETTLED_SAMPLES",
            clv=None, clv_status="NOT_COMPUTABLE_NO_TIMESTAMPED_ODDS",
        )
    brier_values: list[float] = []
    losses: list[float] = []
    dates: set[str] = set()
    for probabilities, outcome, kickoff in samples:
        dates.add(kickoff.astimezone(timezone.utc).date().isoformat())
        if market == "1X2":
            keys = ("home", "draw", "away")
            if outcome not in {"HOME", "DRAW", "AWAY"}:
                raise ValueError("PROSPECTIVE_SCORE_1X2_OUTCOME_INVALID")
            vector = [_safe_probability(probabilities[key]) for key in keys]
            if abs(sum(vector) - 1.0) > 1e-9:
                raise ValueError("PROSPECTIVE_SCORE_1X2_NOT_NORMALISED")
            index = {"HOME": 0, "DRAW": 1, "AWAY": 2}[outcome]
            brier_values.append(sum((value - (1.0 if i == index else 0.0)) ** 2
                                    for i, value in enumerate(vector)))
            losses.append(-math.log(max(vector[index], 1e-15)))
        else:
            if market == "BTTS":
                positive = "YES"
            elif market == "TOTALS_2_5":
                positive = "OVER"
            else:
                raise ValueError("PROSPECTIVE_SCORE_MARKET_UNSUPPORTED")
            if outcome not in {positive, "NO" if market == "BTTS" else "UNDER"}:
                raise ValueError("PROSPECTIVE_SCORE_BINARY_OUTCOME_INVALID")
            key = "yes" if market == "BTTS" else "over"
            p = _safe_probability(probabilities[key])
            y = 1.0 if outcome == positive else 0.0
            brier_values.append((p - y) ** 2)
            losses.append(-math.log(max(p if y else 1.0 - p, 1e-15)))
    return ProspectiveMarketScore(
        market=market, sample_count=len(samples), distinct_dates=len(dates),
        brier_score=sum(brier_values) / len(brier_values),
        log_loss=sum(losses) / len(losses),
        odds_covered_selections=0, roi=None,
        roi_status="LOCKED_NO_VERIFIED_SELECTION_AND_PREKICKOFF_ODDS",
        clv=None, clv_status="NOT_COMPUTABLE_NO_TIMESTAMPED_ODDS",
    )


def evaluate_prospective_settlements(
    ledger: ProspectivePaperLedger,
    *,
    model_version: str | None = None,
    prediction_feature_links: Mapping[str, Mapping[str, object]] | None = None,
) -> ProspectiveSettlementScorecard:
    """Score only append-only settlements linked to their exact prediction event."""
    if not isinstance(ledger, ProspectivePaperLedger):
        raise ValueError("PAPER_LEDGER_REQUIRED")
    ledger.verify_chain()
    predictions = {}
    feature_links = prediction_feature_links or {}
    for event in ledger.events:
        if model_version is not None and event.model_version != model_version:
            continue
        eligible_legacy = (
            event.event_type in {"PREDICTION", "SHADOW_PREDICTION"}
            and event.payload.get("evidence_class") == "PROSPECTIVE_OBSERVED_ONLY"
        )
        eligible_v2 = (
            event.event_type == "PREDICTION"
            and event.model_version == V2_PIT_MODEL_VERSION
            and event.payload.get("evidence_class") == "PIT_CERTIFIED"
            and event.payload.get("point_in_time_certifiable") is True
        )
        if not (eligible_legacy or eligible_v2):
            continue
        if eligible_v2:
            link=feature_links.get(event.event_sha256)
            if (
                link is None
                or link.get("prediction_event_sha256") != event.event_sha256
                or link.get("forecast_evidence_sha256") != event.payload.get("evidence_sha256")
            ):
                raise ValueError("PROSPECTIVE_SCORE_V2_FEATURE_EVIDENCE_LINK_MISSING")
        key = (event.fixture_id, event.model_version)
        if key in predictions:
            raise ValueError("PROSPECTIVE_SCORE_DUPLICATE_PREDICTION_KEY")
        predictions[key] = event

    settlements = {}
    for event in ledger.events:
        if event.event_type != "SETTLEMENT":
            continue
        if model_version is not None and event.model_version != model_version:
            continue
        key = (event.fixture_id, event.model_version)
        if key in settlements:
            raise ValueError("PROSPECTIVE_SCORE_DUPLICATE_SETTLEMENT_KEY")
        prediction = predictions.get(key)
        if prediction is None:
            raise ValueError("PROSPECTIVE_SCORE_SETTLEMENT_NOT_PROSPECTIVE")
        if event.payload.get("prediction_event_sha256") != prediction.event_sha256:
            raise ValueError("PROSPECTIVE_SCORE_SETTLEMENT_LINK_INVALID")
        if prediction.model_version == V2_PIT_MODEL_VERSION:
            link=feature_links.get(prediction.event_sha256)
            if (
                link is None
                or event.payload.get("prediction_feature_link_sha256") != link.get("link_sha256")
                or event.payload.get("feature_snapshot_id") != link.get("feature_snapshot_id")
                or event.payload.get("forecast_evidence_sha256") != link.get("forecast_evidence_sha256")
            ):
                raise ValueError("PROSPECTIVE_SCORE_V2_SETTLEMENT_FEATURE_LINK_INVALID")
        settlements[key] = event
    samples: dict[str, list[tuple[dict, str, datetime]]] = {
        "1X2": [], "BTTS": [], "TOTALS_2_5": [],
    }
    for key, settlement in settlements.items():
        prediction = predictions.get(key)
        if prediction is None or settlement.payload.get("prediction_event_sha256") != prediction.event_sha256:
            raise ValueError("PROSPECTIVE_SCORE_SETTLEMENT_LINK_INVALID")
        kickoff = datetime.fromisoformat(prediction.payload["kickoff_at"])
        if kickoff.tzinfo is None or kickoff.utcoffset() is None:
            raise ValueError("PROSPECTIVE_SCORE_KICKOFF_NOT_AWARE")
        markets = prediction.payload.get("market_probabilities") or {
            "1X2": {
                "home": prediction.payload["home_probability"],
                "draw": prediction.payload["draw_probability"],
                "away": prediction.payload["away_probability"],
            }
        }
        outcomes = settlement.payload.get("market_outcomes") or {}
        for market in ("1X2", "BTTS", "TOTALS_2_5"):
            if market not in markets or market not in outcomes:
                continue
            samples[market].append((markets[market], outcomes[market], kickoff))

    metrics = tuple(_market_score(name, samples[name])
                    for name in ("1X2", "BTTS", "TOTALS_2_5"))
    settled = len(settlements)
    return ProspectiveSettlementScorecard(
        ledger_event_count=len(ledger.events),
        prediction_count=len(predictions),
        settled_prediction_count=settled,
        unsettled_prediction_count=len(predictions) - settled,
        markets=metrics,
        certification_status="NOT_CERTIFIED",
    )
