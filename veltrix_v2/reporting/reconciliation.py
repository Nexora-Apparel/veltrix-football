"""Evidence-backed operator reconciliation for uncertain Telegram deliveries.

This module records evidence only. It has no Telegram transport and cannot retry
or resend a delivery. Authentication of operator_id/reviewer_id belongs to the
trusted caller and is an explicit release prerequisite.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit
import uuid


_HASH = re.compile(r"^[0-9a-f]{64}$")
_OUTCOMES = frozenset({"CONFIRMED_SENT", "CONFIRMED_NOT_SENT", "INCONCLUSIVE"})
_EVIDENCE_SCHEMES = frozenset({"https", "s3", "gs"})


def _aware_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field.upper()}_INVALID") from exc
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field.upper()}_MUST_BE_TIMEZONE_AWARE")
    return value


def validate_reconciliation_event(
    claim: Mapping[str, Any],
    event: Mapping[str, Any],
    evidence_bytes: bytes,
    existing_events: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate event identity, exact evidence bytes, claim binding and event chain."""
    if not isinstance(claim, Mapping) or not isinstance(event, Mapping):
        raise ValueError("RECONCILIATION_INPUTS_MUST_BE_OBJECTS")
    if claim.get("state") != "OUTCOME_UNKNOWN":
        raise ValueError("RECONCILIATION_REQUIRES_OUTCOME_UNKNOWN_CLAIM")

    required = (
        "reconciliation_id", "idempotency_key", "report_id", "report_sha256",
        "destination_sha256", "outcome", "telegram_message_ids", "evidence_uri",
        "evidence_sha256", "evidence_kind", "operator_id", "observed_at",
        "recorded_at", "reason_code",
    )
    if any(key not in event for key in required):
        raise ValueError("RECONCILIATION_REQUIRED_FIELD_MISSING")

    try:
        reconciliation_id = str(uuid.UUID(str(event["reconciliation_id"])))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("RECONCILIATION_ID_INVALID") from exc

    for field in ("idempotency_key", "report_sha256", "destination_sha256", "evidence_sha256"):
        if not isinstance(event[field], str) or not _HASH.fullmatch(event[field]):
            raise ValueError(f"{field.upper()}_INVALID")

    for field in ("idempotency_key", "report_id", "report_sha256", "destination_sha256"):
        if event[field] != claim.get(field):
            raise ValueError("RECONCILIATION_CLAIM_BINDING_MISMATCH")

    outcome = event["outcome"]
    if not isinstance(outcome, str) or outcome not in _OUTCOMES:
        raise ValueError("RECONCILIATION_OUTCOME_INVALID")

    message_ids = event["telegram_message_ids"]
    if not isinstance(message_ids, (list, tuple)) or any(
        not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip()
        for value in message_ids
    ):
        raise ValueError("RECONCILIATION_MESSAGE_IDS_INVALID")
    message_ids = [str(value) for value in message_ids]
    if len(message_ids) != len(set(message_ids)):
        raise ValueError("RECONCILIATION_MESSAGE_IDS_DUPLICATED")
    if outcome == "CONFIRMED_SENT" and not message_ids:
        raise ValueError("CONFIRMED_SENT_REQUIRES_MESSAGE_IDS")
    if outcome != "CONFIRMED_SENT" and message_ids:
        raise ValueError("NON_SENT_OUTCOME_MUST_NOT_HAVE_MESSAGE_IDS")

    evidence_uri = event["evidence_uri"]
    if not isinstance(evidence_uri, str) or not evidence_uri.strip():
        raise ValueError("RECONCILIATION_EVIDENCE_URI_REQUIRED")
    parsed_uri = urlsplit(evidence_uri)
    if (
        parsed_uri.scheme not in _EVIDENCE_SCHEMES
        or not parsed_uri.netloc
        or parsed_uri.username
        or parsed_uri.password
        or parsed_uri.query
        or parsed_uri.fragment
    ):
        raise ValueError("RECONCILIATION_EVIDENCE_URI_NOT_DURABLE")
    if not isinstance(evidence_bytes, bytes):
        raise ValueError("RECONCILIATION_EVIDENCE_BYTES_REQUIRED")
    if len(evidence_bytes) > 8_000_000:
        raise ValueError("RECONCILIATION_EVIDENCE_TOO_LARGE")
    if hashlib.sha256(evidence_bytes).hexdigest() != event["evidence_sha256"]:
        raise ValueError("RECONCILIATION_EVIDENCE_HASH_MISMATCH")

    for field in ("evidence_kind", "operator_id", "reason_code"):
        if not isinstance(event[field], str) or not event[field].strip():
            raise ValueError(f"{field.upper()}_REQUIRED")

    observed_at = _aware_datetime(event["observed_at"], "observed_at")
    recorded_at = _aware_datetime(event["recorded_at"], "recorded_at")
    if recorded_at < observed_at:
        raise ValueError("RECONCILIATION_RECORDED_BEFORE_OBSERVED")

    operator_id = event["operator_id"].strip()
    reviewer_id = event.get("reviewer_id")
    if reviewer_id is not None:
        if not isinstance(reviewer_id, str) or not reviewer_id.strip():
            raise ValueError("RECONCILIATION_REVIEWER_INVALID")
        reviewer_id = reviewer_id.strip()
        if reviewer_id == operator_id:
            raise ValueError("RECONCILIATION_REVIEWER_INVALID")
    if outcome == "CONFIRMED_NOT_SENT" and reviewer_id is None:
        raise ValueError("CONFIRMED_NOT_SENT_REQUIRES_INDEPENDENT_REVIEWER")

    existing = list(existing_events or [])
    supersedes = event.get("supersedes_reconciliation_id")
    if supersedes is None:
        if existing:
            raise ValueError("RECONCILIATION_ALREADY_RECORDED")
    else:
        try:
            supersedes = str(uuid.UUID(str(supersedes)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("RECONCILIATION_SUPERSESSION_ID_INVALID") from exc
        parent = next((row for row in existing if str(row.get("reconciliation_id")) == supersedes), None)
        if parent is None or parent.get("idempotency_key") != event["idempotency_key"]:
            raise ValueError("RECONCILIATION_SUPERSESSION_MISMATCH")
        if any(row.get("supersedes_reconciliation_id") == supersedes for row in existing):
            raise ValueError("RECONCILIATION_PARENT_ALREADY_SUPERSEDED")

    return {
        "reconciliation_id": reconciliation_id,
        "idempotency_key": event["idempotency_key"],
        "report_id": event["report_id"],
        "report_sha256": event["report_sha256"],
        "destination_sha256": event["destination_sha256"],
        "outcome": outcome,
        "telegram_message_ids": message_ids,
        "evidence_uri": evidence_uri,
        "evidence_sha256": event["evidence_sha256"],
        "evidence_kind": event["evidence_kind"].strip(),
        "operator_id": operator_id,
        "reviewer_id": reviewer_id,
        "observed_at": observed_at,
        "recorded_at": recorded_at,
        "reason_code": event["reason_code"].strip(),
        "supersedes_reconciliation_id": supersedes,
    }


class PostgresTelegramReconciliationStore:
    """Append-only reconciliation writer with evidence-byte verification."""

    def __init__(self, connect: Callable, read_evidence: Callable[[str], bytes]):
        if not callable(connect) or not callable(read_evidence):
            raise ValueError("RECONCILIATION_DEPENDENCIES_REQUIRED")
        self._connect = connect
        self._read_evidence = read_evidence

    def record(self, event: Mapping[str, Any]) -> str:
        evidence_uri = event.get("evidence_uri")
        if not isinstance(evidence_uri, str) or not evidence_uri.strip():
            raise ValueError("RECONCILIATION_EVIDENCE_URI_REQUIRED")
        parsed_uri = urlsplit(evidence_uri)
        if (
            parsed_uri.scheme not in _EVIDENCE_SCHEMES
            or not parsed_uri.netloc
            or parsed_uri.username
            or parsed_uri.password
            or parsed_uri.query
            or parsed_uri.fragment
        ):
            raise ValueError("RECONCILIATION_EVIDENCE_URI_NOT_DURABLE")
        evidence_bytes = self._read_evidence(evidence_uri)
        if not isinstance(evidence_bytes, bytes):
            raise ValueError("RECONCILIATION_EVIDENCE_READER_INVALID")
        if len(evidence_bytes) > 8_000_000:
            raise ValueError("RECONCILIATION_EVIDENCE_TOO_LARGE")

        with self._connect() as connection:
            claim = connection.execute(
                """
                SELECT idempotency_key, report_id, report_sha256,
                       destination_sha256, state
                FROM telegram_delivery_claims
                WHERE idempotency_key=%s
                FOR KEY SHARE
                """,
                (event.get("idempotency_key"),),
            ).fetchone()
            if claim is None:
                raise ValueError("RECONCILIATION_DELIVERY_CLAIM_NOT_FOUND")
            claim_data = dict(zip(
                ("idempotency_key", "report_id", "report_sha256", "destination_sha256", "state"),
                claim,
            ))
            existing_rows = connection.execute(
                """
                SELECT reconciliation_id::text, idempotency_key,
                       supersedes_reconciliation_id::text
                FROM telegram_delivery_reconciliations
                WHERE idempotency_key=%s
                """,
                (event.get("idempotency_key"),),
            ).fetchall()
            existing = [
                dict(zip(("reconciliation_id", "idempotency_key", "supersedes_reconciliation_id"), row))
                for row in existing_rows
            ]
            validated = validate_reconciliation_event(
                claim_data, event, evidence_bytes, existing
            )
            connection.execute(
                """
                INSERT INTO telegram_delivery_reconciliations (
                    reconciliation_id, idempotency_key, report_id, report_sha256,
                    destination_sha256, outcome, telegram_message_ids, evidence_uri,
                    evidence_sha256, evidence_kind, operator_id, reviewer_id,
                    observed_at, recorded_at, reason_code, supersedes_reconciliation_id
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    validated["reconciliation_id"], validated["idempotency_key"],
                    validated["report_id"], validated["report_sha256"],
                    validated["destination_sha256"], validated["outcome"],
                    json.dumps(validated["telegram_message_ids"]),
                    validated["evidence_uri"], validated["evidence_sha256"],
                    validated["evidence_kind"], validated["operator_id"],
                    validated["reviewer_id"], validated["observed_at"],
                    validated["recorded_at"], validated["reason_code"],
                    validated["supersedes_reconciliation_id"],
                ),
            )
        return validated["reconciliation_id"]
