"""Fail-closed admission of shadow forecasts into the prospective paper ledger.

The admission layer joins a forecast to its exact scheduled-fixture snapshot,
the point-in-time training observations, and use-time source-rights approvals.
It creates ledger records only; persistence is an explicit separate operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re
from typing import Iterable, Mapping

from veltrix_v2.data.contracts import DataUsePurpose, SourceApproval
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.ledger.paper_predictions import PaperPrediction
from veltrix_v2.models.engine import BatchForecastReport, ForecastRecord, PredictionTarget
from veltrix_v2.models.poisson import MatchObservation, observation_eligible_as_of


_HASH = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PaperAdmissionRejection:
    fixture_id: str
    reason_code: str


@dataclass(frozen=True)
class PaperAdmissionReport:
    admitted: tuple[PaperPrediction, ...]
    rejected: tuple[PaperAdmissionRejection, ...]
    evaluated_forecast_count: int


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _provider_competition_id(competition_id: str, source_id: str) -> str | None:
    prefix = source_id + ":"
    return competition_id[len(prefix):] if competition_id.startswith(prefix) else None


def _approval_for(
    approval_id: str,
    approvals: Mapping[str, SourceApproval],
    *,
    provider: str,
    source_id: str,
    competition_id: str,
    at: datetime,
    purposes: tuple[DataUsePurpose, ...],
) -> SourceApproval:
    approval = approvals.get(approval_id)
    if not isinstance(approval, SourceApproval):
        raise ValueError("SOURCE_APPROVAL_MISSING")
    if approval.approval_id != approval_id or approval.provider != provider or approval.source_id != source_id:
        raise ValueError("SOURCE_APPROVAL_IDENTITY_MISMATCH")
    if approval.data_type not in {"fixture_result", "fixtures_and_results"}:
        raise ValueError("SOURCE_APPROVAL_DATA_TYPE_MISMATCH")
    provider_competition = _provider_competition_id(competition_id, source_id)
    scope = {item.strip() for item in approval.competition_scope.split(",") if item.strip()}
    if not provider_competition or provider_competition not in scope or "*" in scope:
        raise ValueError("SOURCE_APPROVAL_COMPETITION_SCOPE_MISMATCH")
    for purpose in purposes:
        decision = evaluate_source_use(approval, purpose, at_utc=at, commercial=True)
        if not decision.allowed:
            raise ValueError(decision.reason_code)
    return approval


def _training_evidence(
    observations: list[MatchObservation],
    *,
    forecast: ForecastRecord,
    approvals: Mapping[str, SourceApproval],
    rights_evaluated_at: datetime,
    evidence_class: str = "PIT_CERTIFIED",
) -> tuple[list[dict], int]:
    counts: dict[str, int] = {}
    for row in observations:
        if isinstance(row, MatchObservation) and isinstance(row.fixture_id, str):
            counts[row.fixture_id] = counts.get(row.fixture_id, 0) + 1
    duplicate_ids = {key for key, count in counts.items() if count > 1}
    used: list[dict] = []

    for row in observations:
        if not isinstance(row, MatchObservation) or row.fixture_id in duplicate_ids:
            continue
        if row.competition_id != forecast.competition_id:
            continue
        if evidence_class == "PIT_CERTIFIED":
            if row.point_in_time_certifiable is not True:
                continue
        elif evidence_class == "PROSPECTIVE_OBSERVED_ONLY":
            if (
                row.point_in_time_certifiable is not False
                or row.availability_basis != "collector_first_observed_v1"
            ):
                continue
            if not _valid_hash(row.evidence_manifest_sha256):
                raise ValueError("OBSERVED_EVIDENCE_MANIFEST_HASH_MISSING")
            if not _valid_hash(row.capture_evidence_sha256):
                raise ValueError("OBSERVED_CAPTURE_EVIDENCE_HASH_MISSING")
        else:
            raise ValueError("PAPER_EVIDENCE_CLASS_INVALID")
        if not observation_eligible_as_of(
            row, cutoff_at=forecast.cutoff_at, competition_id=forecast.competition_id
        ):
            continue
        if not _valid_hash(row.payload_sha256):
            raise ValueError("TRAINING_OBSERVATION_PAYLOAD_HASH_MISSING")
        if row.availability_basis == "provider_evidence_manifest_v1":
            if not _valid_hash(row.evidence_manifest_sha256):
                raise ValueError("TRAINING_EVIDENCE_MANIFEST_HASH_MISSING")
            if not _valid_hash(row.capture_evidence_sha256):
                raise ValueError("TRAINING_CAPTURE_EVIDENCE_HASH_MISSING")
        if not row.rights_approval_id:
            raise ValueError("TRAINING_OBSERVATION_RIGHTS_APPROVAL_MISSING")
        approval = _approval_for(
            row.rights_approval_id, approvals,
            provider=row.provider, source_id=row.source_id,
            competition_id=row.competition_id, at=rights_evaluated_at,
            purposes=(DataUsePurpose.STORAGE, DataUsePurpose.MODEL_TRAINING),
        )
        used.append({
            "fixture_id": row.fixture_id,
            "competition_id": row.competition_id,
            "home_team_id": row.home_team_id,
            "away_team_id": row.away_team_id,
            "kickoff_at": row.kickoff_at.isoformat() if row.kickoff_at else None,
            "kickoff_date": row.kickoff_date.isoformat() if row.kickoff_date else None,
            "available_at": row.available_at.isoformat(),
            "recorded_at": row.recorded_at.isoformat(),
            "payload_sha256": row.payload_sha256,
            "evidence_manifest_sha256": row.evidence_manifest_sha256,
            "capture_evidence_sha256": row.capture_evidence_sha256,
            "availability_basis": row.availability_basis,
            "evidence_class": evidence_class,
            "rights_approval_id": approval.approval_id,
            "rights_evidence_sha256": approval.evidence_sha256,
        })
    used.sort(key=lambda item: item["fixture_id"])
    return used, len(used)


def admit_shadow_forecasts(
    report: BatchForecastReport,
    targets: Iterable[PredictionTarget],
    observations: Iterable[MatchObservation],
    *,
    source_approvals: Mapping[str, SourceApproval],
    forecasted_at: datetime,
    recorded_at: datetime,
    model_artifact_sha256: str,
    feature_set_sha256: str,
    _evidence_class: str = "PIT_CERTIFIED",
) -> PaperAdmissionReport:
    """Create prospective shadow-ledger records only after all evidence checks.

    This deliberately does not require model.publishable: the ledger records
    non-public shadow forecasts for prospective evaluation. It never enables
    website/Telegram publication. A model remains unpublishable until separate
    certification.
    """
    if _evidence_class not in {"PIT_CERTIFIED", "PROSPECTIVE_OBSERVED_ONLY"}:
        raise ValueError("PAPER_EVIDENCE_CLASS_INVALID")
    if not isinstance(report, BatchForecastReport):
        raise ValueError("BATCH_FORECAST_REPORT_REQUIRED")
    if report.forecast_count != len(report.forecasts):
        raise ValueError("BATCH_FORECAST_COUNT_MISMATCH")
    if not _aware(report.cutoff_at) or not _aware(forecasted_at) or not _aware(recorded_at):
        raise ValueError("PAPER_ADMISSION_TIMESTAMPS_MUST_BE_AWARE")
    if not (report.cutoff_at <= forecasted_at <= recorded_at):
        raise ValueError("PAPER_ADMISSION_TIMESTAMP_ORDER_INVALID")
    if not _valid_hash(model_artifact_sha256) or not _valid_hash(feature_set_sha256):
        raise ValueError("MODEL_OR_FEATURE_ARTIFACT_HASH_INVALID")

    target_rows = list(targets)
    history = list(observations)
    target_counts: dict[str, int] = {}
    for target in target_rows:
        if isinstance(target, PredictionTarget):
            target_counts[target.fixture_id] = target_counts.get(target.fixture_id, 0) + 1
    target_by_id = {target.fixture_id: target for target in target_rows
                    if isinstance(target, PredictionTarget) and target_counts[target.fixture_id] == 1}

    admitted: list[PaperPrediction] = []
    rejected: list[PaperAdmissionRejection] = []
    for forecast in report.forecasts:
        try:
            if not isinstance(forecast, ForecastRecord):
                raise ValueError("FORECAST_RECORD_INVALID")
            target = target_by_id.get(forecast.fixture_id)
            if target is None:
                raise ValueError("UNIQUE_SOURCE_TARGET_NOT_FOUND")
            if (forecast.competition_id != target.competition_id
                    or forecast.kickoff_at != target.kickoff_at
                    or forecast.cutoff_at != report.cutoff_at
                    or forecast.provider != target.provider
                    or forecast.source_id != target.source_id):
                raise ValueError("FORECAST_TARGET_IDENTITY_OR_CUTOFF_MISMATCH")
            if target.retrieved_at > report.cutoff_at or target.kickoff_at <= recorded_at:
                raise ValueError("TARGET_NOT_KNOWN_AND_FUTURE_AT_RECORDING")
            if not _valid_hash(target.payload_sha256):
                raise ValueError("TARGET_PAYLOAD_HASH_INVALID")

            target_approval = _approval_for(
                target.rights_approval_id, source_approvals,
                provider=target.provider, source_id=target.source_id,
                competition_id=target.competition_id, at=recorded_at,
                purposes=(DataUsePurpose.COLLECTION, DataUsePurpose.CACHE),
            )
            if _evidence_class == "PROSPECTIVE_OBSERVED_ONLY" and forecast.model.publishable is not False:
                raise ValueError("OBSERVED_ONLY_FORECAST_MUST_REMAIN_NON_PUBLISHABLE")
            evidence_rows, evidence_count = _training_evidence(
                history, forecast=forecast, approvals=source_approvals,
                rights_evaluated_at=recorded_at, evidence_class=_evidence_class,
            )
            if evidence_count != forecast.model.evidence_match_count:
                raise ValueError("MODEL_EVIDENCE_COUNT_MISMATCH")
            if forecast.model.cutoff_at != report.cutoff_at:
                raise ValueError("MODEL_CUTOFF_MISMATCH")
            if not all(_valid_hash(x) for x in (
                model_artifact_sha256, feature_set_sha256,
                target.payload_sha256, target_approval.evidence_sha256,
            )):
                raise ValueError("PAPER_EVIDENCE_HASH_INVALID")

            evidence = {
                "fixture_id": target.fixture_id,
                "competition_id": target.competition_id,
                "home_team_id": target.home_team_id,
                "away_team_id": target.away_team_id,
                "kickoff_at": target.kickoff_at.isoformat(),
                "cutoff_at": report.cutoff_at.isoformat(),
                "target_provider": target.provider,
                "target_source_id": target.source_id,
                "target_payload_sha256": target.payload_sha256,
                "target_rights_approval_id": target_approval.approval_id,
                "target_rights_evidence_sha256": target_approval.evidence_sha256,
                "training_observations": evidence_rows,
                "model_artifact_sha256": model_artifact_sha256,
                "feature_set_sha256": feature_set_sha256,
                "model_version": forecast.model.model_version,
            }
            evidence_hash = _digest(evidence)
            prediction = PaperPrediction(
                fixture_id=target.fixture_id,
                competition_id=target.competition_id,
                home_team_id=target.home_team_id,
                away_team_id=target.away_team_id,
                kickoff_at=target.kickoff_at,
                prediction_cutoff_at=report.cutoff_at,
                forecasted_at=forecasted_at,
                recorded_at=recorded_at,
                model_version=forecast.model.model_version,
                home_probability=forecast.model.home_win,
                draw_probability=forecast.model.draw,
                away_probability=forecast.model.away_win,
                evidence_sha256=evidence_hash,
                point_in_time_certifiable=(_evidence_class == "PIT_CERTIFIED"),
                evidence_class=_evidence_class,
            )
            admitted.append(prediction)
        except (TypeError, ValueError, AttributeError) as exc:
            reason = str(exc) or "PAPER_ADMISSION_INVALID"
            rejected.append(PaperAdmissionRejection(
                fixture_id=getattr(forecast, "fixture_id", "unknown"),
                reason_code=reason,
            ))

    return PaperAdmissionReport(
        admitted=tuple(admitted), rejected=tuple(rejected),
        evaluated_forecast_count=len(report.forecasts),
    )


def admit_prospective_observed_shadow_forecasts(
    report: BatchForecastReport,
    targets: Iterable[PredictionTarget],
    observations: Iterable[MatchObservation],
    *,
    source_approvals: Mapping[str, SourceApproval],
    forecasted_at: datetime,
    recorded_at: datetime,
    model_artifact_sha256: str,
    feature_set_sha256: str,
) -> PaperAdmissionReport:
    """Admit forecasts using only first-observed snapshots into a non-PIT shadow class.

    This path never promotes evidence to PIT-certified and rejects any model
    forecast marked publishable. It is for prospective paper tracking only.
    """
    return admit_shadow_forecasts(
        report, targets, observations,
        source_approvals=source_approvals,
        forecasted_at=forecasted_at,
        recorded_at=recorded_at,
        model_artifact_sha256=model_artifact_sha256,
        feature_set_sha256=feature_set_sha256,
        _evidence_class="PROSPECTIVE_OBSERVED_ONLY",
    )
