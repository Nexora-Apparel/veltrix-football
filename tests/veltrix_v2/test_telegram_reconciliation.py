from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import uuid

import pytest

from veltrix_v2.reporting.reconciliation import validate_reconciliation_event


CLAIM = {
    "idempotency_key": "a" * 64,
    "report_id": "report-r1",
    "report_sha256": "b" * 64,
    "destination_sha256": "c" * 64,
    "state": "OUTCOME_UNKNOWN",
}
EVIDENCE = b"telegram operator evidence export"
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)


def event(**overrides):
    value = {
        "reconciliation_id": str(uuid.uuid4()),
        "idempotency_key": CLAIM["idempotency_key"],
        "report_id": CLAIM["report_id"],
        "report_sha256": CLAIM["report_sha256"],
        "destination_sha256": CLAIM["destination_sha256"],
        "outcome": "CONFIRMED_SENT",
        "telegram_message_ids": ["12345"],
        "evidence_uri": "s3://veltrix-audit/telegram/evidence.json",
        "evidence_sha256": hashlib.sha256(EVIDENCE).hexdigest(),
        "evidence_kind": "telegram_export_json",
        "operator_id": "github:operator-1",
        "reviewer_id": None,
        "observed_at": NOW.isoformat(),
        "recorded_at": NOW.isoformat(),
        "reason_code": "OPERATOR_REVIEW_COMPLETED",
        "supersedes_reconciliation_id": None,
    }
    value.update(overrides)
    return value


def test_valid_confirmed_sent_event_is_normalized_and_bound_to_claim():
    result = validate_reconciliation_event(CLAIM, event(), EVIDENCE)
    assert result["outcome"] == "CONFIRMED_SENT"
    assert result["telegram_message_ids"] == ["12345"]
    assert result["idempotency_key"] == CLAIM["idempotency_key"]


def test_reconciliation_rejects_non_unknown_claim():
    claim = {**CLAIM, "state": "SENT"}
    with pytest.raises(ValueError, match="OUTCOME_UNKNOWN"):
        validate_reconciliation_event(claim, event(), EVIDENCE)


@pytest.mark.parametrize("field,value", [
    ("report_id", "different-report"),
    ("report_sha256", "d" * 64),
    ("destination_sha256", "e" * 64),
    ("idempotency_key", "f" * 64),
])
def test_reconciliation_rejects_claim_identity_drift(field, value):
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        validate_reconciliation_event(CLAIM, event(**{field: value}), EVIDENCE)


def test_reconciliation_rejects_evidence_hash_mismatch():
    with pytest.raises(ValueError, match="EVIDENCE_HASH_MISMATCH"):
        validate_reconciliation_event(CLAIM, event(), b"changed evidence")


def test_reconciliation_requires_durable_evidence_uri():
    with pytest.raises(ValueError, match="EVIDENCE_URI_NOT_DURABLE"):
        validate_reconciliation_event(CLAIM, event(evidence_uri="/tmp/local.json"), EVIDENCE)


def test_confirmed_sent_requires_message_ids():
    with pytest.raises(ValueError, match="REQUIRES_MESSAGE_IDS"):
        validate_reconciliation_event(CLAIM, event(telegram_message_ids=[]), EVIDENCE)


@pytest.mark.parametrize("outcome", ["CONFIRMED_NOT_SENT", "INCONCLUSIVE"])
def test_non_sent_outcomes_forbid_message_ids(outcome):
    with pytest.raises(ValueError, match="MUST_NOT_HAVE_MESSAGE_IDS"):
        validate_reconciliation_event(CLAIM, event(outcome=outcome), EVIDENCE)


def test_confirmed_not_sent_requires_independent_reviewer():
    with pytest.raises(ValueError, match="INDEPENDENT_REVIEWER"):
        validate_reconciliation_event(
            CLAIM, event(outcome="CONFIRMED_NOT_SENT", telegram_message_ids=[]), EVIDENCE
        )


def test_operator_and_reviewer_must_be_distinct():
    with pytest.raises(ValueError, match="REVIEWER_INVALID"):
        validate_reconciliation_event(
            CLAIM,
            event(
                outcome="CONFIRMED_NOT_SENT",
                telegram_message_ids=[],
                reviewer_id="github:operator-1",
            ),
            EVIDENCE,
        )


def test_reconciliation_rejects_naive_or_reversed_timestamps():
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        validate_reconciliation_event(
            CLAIM, event(observed_at="2026-11-14T12:00:00"), EVIDENCE
        )
    with pytest.raises(ValueError, match="RECORDED_BEFORE_OBSERVED"):
        validate_reconciliation_event(
            CLAIM,
            event(
                observed_at="2026-11-14T13:00:00+00:00",
                recorded_at="2026-11-14T12:00:00+00:00",
            ),
            EVIDENCE,
        )


def test_initial_reconciliation_is_unique_per_claim():
    existing = [{
        "reconciliation_id": str(uuid.uuid4()),
        "idempotency_key": CLAIM["idempotency_key"],
        "supersedes_reconciliation_id": None,
    }]
    with pytest.raises(ValueError, match="ALREADY_RECORDED"):
        validate_reconciliation_event(CLAIM, event(), EVIDENCE, existing)


def test_correction_must_supersede_existing_event_for_same_claim():
    parent_id = str(uuid.uuid4())
    existing = [{
        "reconciliation_id": parent_id,
        "idempotency_key": CLAIM["idempotency_key"],
        "supersedes_reconciliation_id": None,
    }]
    corrected = event(
        reconciliation_id=str(uuid.uuid4()),
        outcome="INCONCLUSIVE",
        telegram_message_ids=[],
        supersedes_reconciliation_id=parent_id,
        reason_code="CORRECTION_EVIDENCE_REVIEW",
    )
    result = validate_reconciliation_event(CLAIM, corrected, EVIDENCE, existing)
    assert result["supersedes_reconciliation_id"] == parent_id


def test_correction_rejects_wrong_parent_or_existing_successor():
    parent_id = str(uuid.uuid4())
    existing = [{
        "reconciliation_id": parent_id,
        "idempotency_key": "9" * 64,
        "supersedes_reconciliation_id": None,
    }]
    corrected = event(supersedes_reconciliation_id=parent_id)
    with pytest.raises(ValueError, match="SUPERSESSION_MISMATCH"):
        validate_reconciliation_event(CLAIM, corrected, EVIDENCE, existing)

    existing = [{
        "reconciliation_id": parent_id,
        "idempotency_key": CLAIM["idempotency_key"],
        "supersedes_reconciliation_id": None,
    }, {
        "reconciliation_id": str(uuid.uuid4()),
        "idempotency_key": CLAIM["idempotency_key"],
        "supersedes_reconciliation_id": parent_id,
    }]
    with pytest.raises(ValueError, match="PARENT_ALREADY_SUPERSEDED"):
        validate_reconciliation_event(
            CLAIM,
            event(supersedes_reconciliation_id=parent_id),
            EVIDENCE,
            existing,
        )


def test_reconciliation_rejects_duplicate_telegram_message_ids():
    with pytest.raises(ValueError, match="MESSAGE_IDS_DUPLICATED"):
        validate_reconciliation_event(
            CLAIM, event(telegram_message_ids=["12345", "12345"]), EVIDENCE
        )


def test_reconciliation_rejects_reviewer_equal_after_normalization():
    with pytest.raises(ValueError, match="REVIEWER_INVALID"):
        validate_reconciliation_event(
            CLAIM,
            event(
                outcome="CONFIRMED_NOT_SENT",
                telegram_message_ids=[],
                operator_id="github:operator-1",
                reviewer_id=" github:operator-1 ",
            ),
            EVIDENCE,
        )


def test_reconciliation_rejects_unrecognized_outcome_type():
    with pytest.raises(ValueError, match="OUTCOME_INVALID"):
        validate_reconciliation_event(CLAIM, event(outcome=[]), EVIDENCE)
