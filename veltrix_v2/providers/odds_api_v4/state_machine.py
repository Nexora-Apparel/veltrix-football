"""Pure append-only capture state transition validator; no persistence or I/O."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json


STATES = frozenset({
    "PLANNED", "BLOCKED", "PREFLIGHT_APPROVED", "CREDIT_RESERVED",
    "REQUEST_STARTED", "RESPONSE_RECEIVED", "OUTCOME_UNCERTAIN",
    "PROVIDER_REJECTED", "PARSED", "PARSE_REJECTED",
    "QUOTA_RECONCILED", "COMMITTED",
})

_ALLOWED = {
    "PLANNED": {"BLOCKED", "PREFLIGHT_APPROVED"},
    "PREFLIGHT_APPROVED": {"BLOCKED", "CREDIT_RESERVED"},
    "CREDIT_RESERVED": {"BLOCKED", "REQUEST_STARTED"},
    "REQUEST_STARTED": {"RESPONSE_RECEIVED", "OUTCOME_UNCERTAIN", "PROVIDER_REJECTED"},
    "OUTCOME_UNCERTAIN": {"QUOTA_RECONCILED"},
    "RESPONSE_RECEIVED": {"PARSED", "PARSE_REJECTED", "PROVIDER_REJECTED"},
    "PROVIDER_REJECTED": {"QUOTA_RECONCILED"},
    "PARSED": {"QUOTA_RECONCILED"},
    "PARSE_REJECTED": {"QUOTA_RECONCILED"},
    "QUOTA_RECONCILED": {"COMMITTED"},
    "BLOCKED": set(),
    "COMMITTED": set(),
}


@dataclass(frozen=True)
class CaptureStateEvent:
    request_id: str
    sequence: int
    from_state: str
    to_state: str
    occurred_at: str
    actor: str
    reason_code: str
    evidence_sha256: str
    previous_event_sha256: str | None
    event_sha256: str


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    reason_code: str
    event: CaptureStateEvent | None


def _aware_iso(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("EVENT_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_sha256(value: str | None) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _hash(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def advance_state(
    *,
    request_id: str,
    current_state: str,
    target_state: str,
    sequence: int,
    occurred_at: datetime,
    actor: str,
    reason_code: str,
    evidence_sha256: str,
    previous_event: CaptureStateEvent | None = None,
) -> TransitionDecision:
    """Validate one state transition and return a hash-chained immutable event."""
    if not isinstance(request_id, str) or not request_id.strip():
        return TransitionDecision(False, "REQUEST_ID_INVALID", None)
    if current_state not in STATES or target_state not in STATES:
        return TransitionDecision(False, "STATE_UNKNOWN", None)
    if target_state not in _ALLOWED[current_state]:
        return TransitionDecision(False, "TRANSITION_NOT_ALLOWED", None)
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        return TransitionDecision(False, "SEQUENCE_INVALID", None)
    if not isinstance(actor, str) or not actor.strip() or not isinstance(reason_code, str) or not reason_code.strip():
        return TransitionDecision(False, "EVENT_METADATA_INVALID", None)
    if not _is_sha256(evidence_sha256):
        return TransitionDecision(False, "EVIDENCE_HASH_INVALID", None)
    try:
        timestamp = _aware_iso(occurred_at)
    except ValueError:
        return TransitionDecision(False, "EVENT_TIMESTAMP_INVALID", None)

    previous_hash = None
    if previous_event is None:
        if sequence != 1 or current_state != "PLANNED":
            return TransitionDecision(False, "INITIAL_EVENT_CHAIN_INVALID", None)
    else:
        if not isinstance(previous_event, CaptureStateEvent):
            return TransitionDecision(False, "PREVIOUS_EVENT_INVALID", None)
        if (previous_event.request_id != request_id
                or previous_event.to_state != current_state
                or previous_event.sequence + 1 != sequence
                or not _is_sha256(previous_event.event_sha256)):
            return TransitionDecision(False, "PREVIOUS_EVENT_CHAIN_MISMATCH", None)
        previous_hash = previous_event.event_sha256

    payload = {
        "request_id": request_id, "sequence": sequence,
        "from_state": current_state, "to_state": target_state,
        "occurred_at": timestamp, "actor": actor.strip(),
        "reason_code": reason_code.strip(), "evidence_sha256": evidence_sha256,
        "previous_event_sha256": previous_hash,
    }
    event = CaptureStateEvent(
        request_id=request_id, sequence=sequence, from_state=current_state,
        to_state=target_state, occurred_at=timestamp, actor=actor.strip(),
        reason_code=reason_code.strip(), evidence_sha256=evidence_sha256,
        previous_event_sha256=previous_hash, event_sha256=_hash(payload),
    )
    return TransitionDecision(True, "TRANSITION_ACCEPTED", event)
