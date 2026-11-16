"""Rights-verified settlement ingestion for prospective paper predictions."""
from __future__ import annotations

from datetime import datetime
from typing import Mapping

from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, FixtureStatus, HistoricalFixture, SourceApproval,
)
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.ledger.paper_predictions import (
    V2_PIT_MODEL_VERSION, PaperLedgerEvent, ProspectivePaperLedger,
)


def settle_from_verified_fixture(
    ledger: ProspectivePaperLedger,
    fixture: HistoricalFixture,
    approval: SourceApproval,
    *,
    recorded_at: datetime,
    model_version: str | None = None,
    prediction_feature_link: Mapping[str, object] | None = None,
) -> PaperLedgerEvent:
    """Settle one paper prediction from an exact, rights-approved final result."""
    if not isinstance(ledger, ProspectivePaperLedger):
        raise ValueError("PAPER_LEDGER_REQUIRED")
    if not isinstance(fixture, HistoricalFixture) or fixture.status is not FixtureStatus.FINISHED:
        raise ValueError("SETTLEMENT_REQUIRES_FINISHED_SOURCE_FIXTURE")
    if not isinstance(approval, SourceApproval):
        raise ValueError("SETTLEMENT_SOURCE_APPROVAL_REQUIRED")
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ValueError("SETTLEMENT_RECORDING_TIMESTAMP_MUST_BE_AWARE")
    fixture_id = f"{fixture.source_id}:{fixture.provider_fixture_id}"
    predictions = tuple(
        event for event in ledger.events
        if event.event_type in {"PREDICTION", "SHADOW_PREDICTION"}
        and event.fixture_id == fixture_id
        and (model_version is None or event.model_version == model_version)
    )
    if not predictions:
        raise ValueError("PAPER_SETTLEMENT_WITHOUT_MATCHING_PREDICTION")
    if len(predictions) != 1:
        raise ValueError("PAPER_SETTLEMENT_PREDICTION_NOT_UNIQUE")
    prediction = predictions[0]
    is_v2_pit_prediction = (
        prediction.event_type == "PREDICTION"
        and prediction.model_version == V2_PIT_MODEL_VERSION
    )
    feature_link_fields = {}
    if is_v2_pit_prediction:
        if prediction_feature_link is None:
            raise ValueError("SETTLEMENT_V2_FEATURE_EVIDENCE_LINK_REQUIRED")
        required_link_fields = (
            "link_sha256","prediction_event_sha256","feature_snapshot_id",
            "eligibility_event_id","feature_set_sha256","eligibility_evidence_sha256",
            "forecast_evidence_sha256","model_artifact_sha256",
            "forecast_cutoff_at","feature_snapshot_cutoff_at","recorded_at",
        )
        if any(field not in prediction_feature_link for field in required_link_fields):
            raise ValueError("SETTLEMENT_V2_FEATURE_EVIDENCE_LINK_INCOMPLETE")
        if (
            prediction_feature_link["prediction_event_sha256"] != prediction.event_sha256
            or prediction_feature_link["forecast_evidence_sha256"] != prediction.payload.get("evidence_sha256")
            or prediction.payload.get("evidence_class") != "PIT_CERTIFIED"
        ):
            raise ValueError("SETTLEMENT_V2_FEATURE_EVIDENCE_LINK_IDENTITY_MISMATCH")
        for field in (
            "link_sha256","feature_set_sha256","eligibility_evidence_sha256",
            "forecast_evidence_sha256","model_artifact_sha256",
        ):
            value=prediction_feature_link[field]
            if not isinstance(value,str) or len(value)!=64 or any(ch not in "0123456789abcdef" for ch in value):
                raise ValueError("SETTLEMENT_V2_FEATURE_EVIDENCE_HASH_INVALID")
        for field in ("feature_snapshot_id","eligibility_event_id"):
            value=prediction_feature_link[field]
            if not isinstance(value,int) or isinstance(value,bool) or value<=0:
                raise ValueError("SETTLEMENT_V2_FEATURE_EVIDENCE_ID_INVALID")
        feature_cutoff=prediction_feature_link["feature_snapshot_cutoff_at"]
        forecast_cutoff=prediction_feature_link["forecast_cutoff_at"]
        link_recorded=prediction_feature_link["recorded_at"]
        if isinstance(feature_cutoff,str):
            feature_cutoff=datetime.fromisoformat(feature_cutoff)
        if isinstance(forecast_cutoff,str):
            forecast_cutoff=datetime.fromisoformat(forecast_cutoff)
        if isinstance(link_recorded,str):
            link_recorded=datetime.fromisoformat(link_recorded)
        prediction_recorded=datetime.fromisoformat(prediction.recorded_at)
        if (
            feature_cutoff.tzinfo is None or forecast_cutoff.tzinfo is None
            or link_recorded.tzinfo is None
            or feature_cutoff > forecast_cutoff
            or forecast_cutoff > prediction_recorded
            or link_recorded < prediction_recorded
            or link_recorded > recorded_at
        ):
            raise ValueError("SETTLEMENT_V2_FEATURE_EVIDENCE_CLOCK_INVALID")
        feature_link_fields={
            "prediction_feature_link_sha256":prediction_feature_link["link_sha256"],
            "feature_snapshot_id":prediction_feature_link["feature_snapshot_id"],
            "eligibility_event_id":prediction_feature_link["eligibility_event_id"],
            "feature_set_sha256":prediction_feature_link["feature_set_sha256"],
            "eligibility_evidence_sha256":prediction_feature_link["eligibility_evidence_sha256"],
            "forecast_evidence_sha256":prediction_feature_link["forecast_evidence_sha256"],
            "model_artifact_sha256":prediction_feature_link["model_artifact_sha256"],
        }
    elif prediction_feature_link is not None:
        raise ValueError("SETTLEMENT_FEATURE_EVIDENCE_LINK_ONLY_FOR_V2_PREDICTION")

    observed_only = prediction.payload.get("evidence_class") == "PROSPECTIVE_OBSERVED_ONLY"
    if observed_only:
        if fixture.available_at_utc is None:
            raise ValueError("SETTLEMENT_CONSERVATIVE_DELAY_BASIS_MISSING")
        if not (
            fixture.kickoff_at_utc <= fixture.available_at_utc
            <= fixture.retrieved_at_utc <= recorded_at
        ):
            raise ValueError("SETTLEMENT_FIRST_OBSERVED_TEMPORAL_ORDER_INVALID")
    else:
        if fixture.available_at_utc is None:
            raise ValueError("SETTLEMENT_RESULT_AVAILABILITY_TIMESTAMP_MISSING")
        if not (fixture.kickoff_at_utc <= fixture.available_at_utc
                <= fixture.retrieved_at_utc <= recorded_at):
            raise ValueError("SETTLEMENT_SOURCE_TEMPORAL_ORDER_INVALID")
    if (approval.approval_id != fixture.rights_approval_id
            or approval.provider != fixture.provider
            or approval.source_id != fixture.source_id):
        raise ValueError("SETTLEMENT_SOURCE_APPROVAL_IDENTITY_MISMATCH")
    if approval.data_type not in {"fixture_result", "fixtures_and_results"}:
        raise ValueError("SETTLEMENT_SOURCE_APPROVAL_DATA_TYPE_MISMATCH")
    scope = {item.strip() for item in approval.competition_scope.split(",") if item.strip()}
    if fixture.provider_competition_id not in scope or "*" in scope:
        raise ValueError("SETTLEMENT_COMPETITION_OUTSIDE_APPROVAL_SCOPE")
    for purpose in (
        DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE, DataUsePurpose.BENCHMARKING,
    ):
        decision = evaluate_source_use(
            approval, purpose, at_utc=recorded_at, commercial=False
        )
        if not decision.allowed:
            raise ValueError(decision.reason_code)

    payload = prediction.payload
    if (
        payload.get("competition_id") != f"{fixture.source_id}:{fixture.provider_competition_id}"
        or payload.get("home_team_id") != f"{fixture.source_id}:{fixture.provider_home_team_id}"
        or payload.get("away_team_id") != f"{fixture.source_id}:{fixture.provider_away_team_id}"
        or payload.get("kickoff_at") != fixture.kickoff_at_utc.isoformat()
    ):
        raise ValueError("SETTLEMENT_FIXTURE_IDENTITY_MISMATCH")

    result_first_observed = fixture.availability_basis == "collector_first_observed_v1"
    if result_first_observed:
        if fixture.available_at_utc != fixture.retrieved_at_utc:
            raise ValueError("SETTLEMENT_FIRST_OBSERVED_CLOCK_MISMATCH")
        result_available_at = fixture.retrieved_at_utc
        result_retrieved_at = fixture.retrieved_at_utc
        result_basis = "collector_first_observed_v1"
    else:
        result_available_at = fixture.available_at_utc
        result_retrieved_at = fixture.retrieved_at_utc
        result_basis = "provider_timestamp"

    return ledger.append_settlement(
        fixture_id=fixture_id,
        model_version=prediction.model_version,
        home_goals=fixture.home_score,
        away_goals=fixture.away_score,
        result_available_at=result_available_at,
        result_retrieved_at=result_retrieved_at,
        recorded_at=recorded_at,
        source_provider=fixture.provider,
        source_id=fixture.source_id,
        source_fixture_id=fixture.provider_fixture_id,
        result_payload_sha256=fixture.payload_sha256,
        rights_approval_id=approval.approval_id,
        rights_evidence_sha256=approval.evidence_sha256,
        result_availability_basis=result_basis,
        settlement_delay_basis=fixture.availability_basis if result_first_observed else None,
        **feature_link_fields,
        result_response_sha256=fixture.response_sha256,
        result_capture_manifest_sha256=fixture.capture_manifest_sha256,
    )



def settle_verified_fixture_to_store(
    store,
    fixture: HistoricalFixture,
    approval: SourceApproval,
    *,
    recorded_at: datetime,
    model_version: str | None = None,
    prediction_feature_link: Mapping[str, object] | None = None,
) -> PaperLedgerEvent:
    """Verify settlement rights and source identity, then persist through a ledger store.

    The store must expose load() and append_settlement(). The first read verifies
    the existing chain and locates the exact prediction; the store's append method
    then rechecks the chain under its own transaction/lock before committing.
    """
    if not callable(getattr(store, "load", None)) or not callable(
        getattr(store, "append_settlement", None)
    ):
        raise ValueError("PAPER_LEDGER_STORE_INTERFACE_INVALID")

    ledger = store.load()
    verified = settle_from_verified_fixture(
        ledger,
        fixture,
        approval,
        recorded_at=recorded_at,
        model_version=model_version,
        prediction_feature_link=prediction_feature_link,
    )
    payload = verified.payload
    persisted = store.append_settlement(
        fixture_id=verified.fixture_id,
        model_version=verified.model_version,
        home_goals=payload["home_goals"],
        away_goals=payload["away_goals"],
        result_available_at=datetime.fromisoformat(payload["result_available_at"]),
        result_retrieved_at=datetime.fromisoformat(payload["result_retrieved_at"]),
        recorded_at=datetime.fromisoformat(payload["recorded_at"]),
        source_provider=payload["source_provider"],
        source_id=payload["source_id"],
        source_fixture_id=payload["source_fixture_id"],
        result_payload_sha256=payload["result_payload_sha256"],
        rights_approval_id=payload["rights_approval_id"],
        rights_evidence_sha256=payload["rights_evidence_sha256"],
        result_availability_basis=payload["result_availability_basis"],
        settlement_delay_basis=payload["settlement_delay_basis"],
        result_response_sha256=payload.get("result_response_sha256"),
        result_capture_manifest_sha256=payload.get("result_capture_manifest_sha256"),
        prediction_feature_link_sha256=payload.get("prediction_feature_link_sha256"),
        feature_snapshot_id=payload.get("feature_snapshot_id"),
        eligibility_event_id=payload.get("eligibility_event_id"),
        feature_set_sha256=payload.get("feature_set_sha256"),
        eligibility_evidence_sha256=payload.get("eligibility_evidence_sha256"),
        forecast_evidence_sha256=payload.get("forecast_evidence_sha256"),
        model_artifact_sha256=payload.get("model_artifact_sha256"),
    )
    if persisted.event_sha256 != verified.event_sha256:
        raise RuntimeError("PAPER_LEDGER_PERSISTED_SETTLEMENT_HASH_MISMATCH")
    return persisted
