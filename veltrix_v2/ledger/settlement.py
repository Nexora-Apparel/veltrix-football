"""Rights-verified settlement ingestion for prospective paper predictions."""
from __future__ import annotations

from datetime import datetime

from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, FixtureStatus, HistoricalFixture, SourceApproval,
)
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.ledger.paper_predictions import PaperLedgerEvent, ProspectivePaperLedger


def settle_from_verified_fixture(
    ledger: ProspectivePaperLedger,
    fixture: HistoricalFixture,
    approval: SourceApproval,
    *,
    recorded_at: datetime,
    model_version: str | None = None,
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
            approval, purpose, at_utc=recorded_at, commercial=True
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

    observed_only = prediction.payload.get("evidence_class") == "PROSPECTIVE_OBSERVED_ONLY"
    if observed_only:
        # The provider publication clock is unknown. Use the exact time this
        # collector first observed the finished result, never the old proxy.
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
        settlement_delay_basis=fixture.availability_basis if observed_only else None,
    )
