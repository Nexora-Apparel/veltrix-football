"""Append-only prospective paper prediction ledger primitives.

This module is intentionally storage-agnostic. Callers persist each immutable
event to an append-only store; no database/network/production write occurs here.
Historical backfills are rejected. Non-PIT observations can enter only the separately typed prospective-observed shadow class; they can never be represented as PIT-certified predictions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import math
from typing import Iterable


GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class PaperPrediction:
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    kickoff_at: datetime
    prediction_cutoff_at: datetime
    forecasted_at: datetime
    recorded_at: datetime
    model_version: str
    home_probability: float
    draw_probability: float
    away_probability: float
    evidence_sha256: str
    point_in_time_certifiable: bool
    evidence_class: str = "PIT_CERTIFIED"
    target_provider: str | None = None
    target_source_id: str | None = None
    target_source_fixture_id: str | None = None
    target_provider_competition_id: str | None = None
    target_payload_sha256: str | None = None
    target_response_sha256: str | None = None
    target_capture_manifest_sha256: str | None = None


@dataclass(frozen=True)
class PaperLedgerEvent:
    sequence: int
    event_type: str
    fixture_id: str
    model_version: str
    recorded_at: str
    payload: dict
    previous_event_sha256: str
    event_sha256: str


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _event_hash(body: dict) -> str:
    return hashlib.sha256(_canonical(body)).hexdigest()


class ProspectivePaperLedger:
    """In-memory append-only ledger builder with a verifiable hash chain."""

    def __init__(self, events: Iterable[PaperLedgerEvent] = ()) -> None:
        self._events = list(events)
        self.verify_chain()

    @property
    def events(self) -> tuple[PaperLedgerEvent, ...]:
        return tuple(self._events)

    def append_prediction(self, prediction: PaperPrediction) -> PaperLedgerEvent:
        if not isinstance(prediction, PaperPrediction):
            raise ValueError("PAPER_PREDICTION_TYPE_INVALID")
        times = (prediction.kickoff_at, prediction.prediction_cutoff_at,
                 prediction.forecasted_at, prediction.recorded_at)
        if not all(_aware(x) for x in times):
            raise ValueError("PAPER_PREDICTION_TIMESTAMPS_MUST_BE_AWARE")
        if not (prediction.prediction_cutoff_at <= prediction.forecasted_at
                <= prediction.recorded_at < prediction.kickoff_at):
            raise ValueError("PAPER_PREDICTION_NOT_PROSPECTIVE")
        if prediction.point_in_time_certifiable is True and prediction.evidence_class == "PIT_CERTIFIED":
            event_type = "PREDICTION"
        elif prediction.point_in_time_certifiable is False and prediction.evidence_class == "PROSPECTIVE_OBSERVED_ONLY":
            event_type = "SHADOW_PREDICTION"
        elif prediction.point_in_time_certifiable is False and prediction.evidence_class == "PIT_CERTIFIED":
            raise ValueError("PAPER_PREDICTION_EVIDENCE_NOT_CERTIFIABLE")
        else:
            raise ValueError("PAPER_PREDICTION_EVIDENCE_CLASS_INVALID")
        if not all(isinstance(x, str) and x.strip() for x in (
            prediction.fixture_id, prediction.competition_id, prediction.home_team_id,
            prediction.away_team_id, prediction.model_version
        )) or prediction.home_team_id == prediction.away_team_id:
            raise ValueError("PAPER_PREDICTION_IDENTITY_INVALID")
        if len(prediction.evidence_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in prediction.evidence_sha256.lower()
        ):
            raise ValueError("PAPER_PREDICTION_EVIDENCE_HASH_INVALID")
        probs = (prediction.home_probability, prediction.draw_probability,
                 prediction.away_probability)
        if any(not isinstance(x, (int, float)) or isinstance(x, bool)
               or not math.isfinite(x) or x < 0 or x > 1 for x in probs):
            raise ValueError("PAPER_PREDICTION_PROBABILITY_INVALID")
        if abs(sum(probs) - 1.0) > 1e-9:
            raise ValueError("PAPER_PREDICTION_PROBABILITIES_NOT_NORMALISED")
        if any(e.event_type in {"PREDICTION", "SHADOW_PREDICTION"}
               and e.fixture_id == prediction.fixture_id
               and e.model_version == prediction.model_version for e in self._events):
            raise ValueError("PAPER_PREDICTION_DUPLICATE")
        target_fields = (
            prediction.target_provider, prediction.target_source_id,
            prediction.target_source_fixture_id, prediction.target_provider_competition_id,
            prediction.target_payload_sha256, prediction.target_response_sha256,
            prediction.target_capture_manifest_sha256,
        )
        if any(value is not None for value in target_fields):
            if not all(isinstance(value, str) and value.strip() for value in (
                prediction.target_provider, prediction.target_source_id,
                prediction.target_source_fixture_id, prediction.target_payload_sha256,
            )):
                raise ValueError("PAPER_PREDICTION_TARGET_PROVENANCE_INCOMPLETE")
            for value in (
                prediction.target_payload_sha256,
                prediction.target_response_sha256,
                prediction.target_capture_manifest_sha256,
            ):
                if value is not None and (
                    len(value) != 64
                    or any(ch not in "0123456789abcdef" for ch in value.casefold())
                ):
                    raise ValueError("PAPER_PREDICTION_TARGET_HASH_INVALID")
            if prediction.target_provider == "5DollarFootballAPI" and not all(
                isinstance(value, str) and value.strip() for value in (
                    prediction.target_provider_competition_id,
                    prediction.target_response_sha256,
                    prediction.target_capture_manifest_sha256,
                )
            ):
                raise ValueError("PAPER_PREDICTION_TARGET_CAPTURE_EVIDENCE_MISSING")

        payload = {
            "fixture_id": prediction.fixture_id,
            "competition_id": prediction.competition_id,
            "home_team_id": prediction.home_team_id,
            "away_team_id": prediction.away_team_id,
            "kickoff_at": prediction.kickoff_at.isoformat(),
            "prediction_cutoff_at": prediction.prediction_cutoff_at.isoformat(),
            "forecasted_at": prediction.forecasted_at.isoformat(),
            "recorded_at": prediction.recorded_at.isoformat(),
            "model_version": prediction.model_version,
            "home_probability": float(prediction.home_probability),
            "draw_probability": float(prediction.draw_probability),
            "away_probability": float(prediction.away_probability),
            "evidence_sha256": prediction.evidence_sha256.lower(),
            "point_in_time_certifiable": prediction.point_in_time_certifiable,
            "evidence_class": prediction.evidence_class,
        }
        if prediction.target_provider is not None:
            payload.update({
                "target_provider": prediction.target_provider,
                "target_source_id": prediction.target_source_id,
                "target_source_fixture_id": prediction.target_source_fixture_id,
                "target_provider_competition_id": prediction.target_provider_competition_id,
                "target_payload_sha256": prediction.target_payload_sha256,
                "target_response_sha256": prediction.target_response_sha256,
                "target_capture_manifest_sha256": prediction.target_capture_manifest_sha256,
            })
        return self._append(event_type, prediction.fixture_id,
                            prediction.model_version, prediction.recorded_at, payload)

    def append_settlement(self, *, fixture_id: str, model_version: str,
                          home_goals: int, away_goals: int,
                          result_available_at: datetime,
                          result_retrieved_at: datetime,
                          recorded_at: datetime,
                          source_provider: str,
                          source_id: str,
                          source_fixture_id: str,
                          result_payload_sha256: str,
                          rights_approval_id: str,
                          rights_evidence_sha256: str,
                          result_availability_basis: str = "provider_timestamp",
                          settlement_delay_basis: str | None = None) -> PaperLedgerEvent:
        prediction = next((e for e in self._events
                           if e.event_type in {"PREDICTION", "SHADOW_PREDICTION"}
                           and e.fixture_id == fixture_id
                           and e.model_version == model_version), None)
        if prediction is None:
            raise ValueError("PAPER_SETTLEMENT_WITHOUT_PREDICTION")
        if not all(_aware(x) for x in (result_available_at, result_retrieved_at, recorded_at)):
            raise ValueError("PAPER_SETTLEMENT_TIMESTAMPS_MUST_BE_AWARE")
        kickoff = datetime.fromisoformat(prediction.payload["kickoff_at"])
        if not (kickoff <= result_available_at <= result_retrieved_at <= recorded_at):
            raise ValueError("PAPER_SETTLEMENT_TEMPORAL_ORDER_INVALID")
        if result_availability_basis not in {"provider_timestamp", "collector_first_observed_v1"}:
            raise ValueError("PAPER_SETTLEMENT_AVAILABILITY_BASIS_INVALID")
        if (result_availability_basis == "collector_first_observed_v1"
                and result_available_at != result_retrieved_at):
            raise ValueError("PAPER_SETTLEMENT_FIRST_OBSERVED_CLOCK_MISMATCH")
        if any(e.event_type == "SETTLEMENT" and e.fixture_id == fixture_id
               and e.model_version == model_version for e in self._events):
            raise ValueError("PAPER_SETTLEMENT_DUPLICATE")
        if any(not isinstance(x, int) or isinstance(x, bool) or x < 0
               for x in (home_goals, away_goals)):
            raise ValueError("PAPER_SETTLEMENT_SCORE_INVALID")
        if not all(isinstance(x, str) and x.strip() for x in (
            source_provider, source_id, source_fixture_id, rights_approval_id
        )):
            raise ValueError("PAPER_SETTLEMENT_SOURCE_IDENTITY_INVALID")
        for value in (result_payload_sha256, rights_evidence_sha256):
            if not isinstance(value, str) or len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value.lower()
            ):
                raise ValueError("PAPER_SETTLEMENT_EVIDENCE_HASH_INVALID")
        payload = {
            "home_goals": home_goals, "away_goals": away_goals,
            "result_available_at": result_available_at.isoformat(),
            "result_retrieved_at": result_retrieved_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "source_provider": source_provider, "source_id": source_id,
            "source_fixture_id": source_fixture_id,
            "result_payload_sha256": result_payload_sha256.lower(),
            "rights_approval_id": rights_approval_id,
            "rights_evidence_sha256": rights_evidence_sha256.lower(),
            "result_availability_basis": result_availability_basis,
            "settlement_delay_basis": settlement_delay_basis,
            "prediction_event_type": prediction.event_type,
            "prediction_evidence_class": prediction.payload.get("evidence_class", "PIT_CERTIFIED"),
            "prediction_event_sha256": prediction.event_sha256,
        }
        return self._append("SETTLEMENT", fixture_id, model_version, recorded_at, payload)

    def _append(self, event_type: str, fixture_id: str, model_version: str,
                recorded_at: datetime, payload: dict) -> PaperLedgerEvent:
        previous = self._events[-1].event_sha256 if self._events else GENESIS_HASH
        body = {
            "sequence": len(self._events) + 1, "event_type": event_type,
            "fixture_id": fixture_id, "model_version": model_version,
            "recorded_at": recorded_at.isoformat(), "payload": payload,
            "previous_event_sha256": previous,
        }
        event = PaperLedgerEvent(
            sequence=body["sequence"], event_type=event_type, fixture_id=fixture_id,
            model_version=model_version, recorded_at=body["recorded_at"],
            payload=payload, previous_event_sha256=previous,
            event_sha256=_event_hash(body),
        )
        self._events.append(event)
        return event

    def verify_chain(self) -> bool:
        previous = GENESIS_HASH
        for index, event in enumerate(self._events, start=1):
            body = {
                "sequence": event.sequence, "event_type": event.event_type,
                "fixture_id": event.fixture_id, "model_version": event.model_version,
                "recorded_at": event.recorded_at, "payload": event.payload,
                "previous_event_sha256": event.previous_event_sha256,
            }
            if event.sequence != index or event.previous_event_sha256 != previous:
                raise ValueError("PAPER_LEDGER_CHAIN_LINK_INVALID")
            if _event_hash(body) != event.event_sha256:
                raise ValueError("PAPER_LEDGER_EVENT_HASH_INVALID")
            if event.event_type in {"PREDICTION", "SHADOW_PREDICTION"}:
                payload = event.payload
                if (
                    payload.get("fixture_id") != event.fixture_id
                    or payload.get("model_version") != event.model_version
                    or payload.get("recorded_at") != event.recorded_at
                ):
                    raise ValueError("PAPER_LEDGER_EVENT_IDENTITY_INVALID")
                if payload.get("target_provider") == "5DollarFootballAPI":
                    required_target_fields = (
                        "target_source_id", "target_source_fixture_id",
                        "target_provider_competition_id", "target_payload_sha256",
                        "target_response_sha256", "target_capture_manifest_sha256",
                    )
                    if not all(
                        isinstance(payload.get(key), str) and payload[key].strip()
                        for key in required_target_fields
                    ):
                        raise ValueError("PAPER_LEDGER_TARGET_PROVENANCE_INCOMPLETE")
                    if not all(
                        len(payload[key]) == 64
                        and all(ch in "0123456789abcdef" for ch in payload[key].casefold())
                        for key in (
                            "target_payload_sha256", "target_response_sha256",
                            "target_capture_manifest_sha256",
                        )
                    ):
                        raise ValueError("PAPER_LEDGER_TARGET_HASH_INVALID")
            previous = event.event_sha256
        return True
