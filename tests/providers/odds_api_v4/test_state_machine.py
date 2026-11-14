from dataclasses import replace
from datetime import datetime, timedelta, timezone

from veltrix_v2.providers.odds_api_v4.state_machine import advance_state


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
HASH = "a" * 64


def advance(current, target, sequence, previous=None, at=None, evidence=HASH):
    return advance_state(
        request_id="req-1", current_state=current, target_state=target,
        sequence=sequence, occurred_at=at or NOW + timedelta(seconds=sequence),
        actor="offline-test", reason_code="TEST_TRANSITION",
        evidence_sha256=evidence, previous_event=previous,
    )


def test_full_capture_lifecycle_is_hash_chained_and_append_only():
    first = advance("PLANNED", "PREFLIGHT_APPROVED", 1)
    assert first.allowed
    second = advance("PREFLIGHT_APPROVED", "CREDIT_RESERVED", 2, first.event)
    third = advance("CREDIT_RESERVED", "REQUEST_STARTED", 3, second.event)
    fourth = advance("REQUEST_STARTED", "RESPONSE_RECEIVED", 4, third.event)
    fifth = advance("RESPONSE_RECEIVED", "PARSED", 5, fourth.event)
    sixth = advance("PARSED", "QUOTA_RECONCILED", 6, fifth.event)
    seventh = advance("QUOTA_RECONCILED", "COMMITTED", 7, sixth.event)
    assert all(x.allowed for x in (second, third, fourth, fifth, sixth, seventh))
    assert seventh.event.previous_event_sha256 == sixth.event.event_sha256
    assert len({x.event.event_sha256 for x in (first, second, third, fourth, fifth, sixth, seventh)}) == 7


def test_timeout_and_parse_rejection_must_reconcile_before_commit():
    started = advance("PLANNED", "PREFLIGHT_APPROVED", 1)
    reserved = advance("PREFLIGHT_APPROVED", "CREDIT_RESERVED", 2, started.event)
    dispatched = advance("CREDIT_RESERVED", "REQUEST_STARTED", 3, reserved.event)
    uncertain = advance("REQUEST_STARTED", "OUTCOME_UNCERTAIN", 4, dispatched.event)
    assert uncertain.allowed
    blocked_commit = advance("OUTCOME_UNCERTAIN", "COMMITTED", 5, uncertain.event)
    assert not blocked_commit.allowed
    reconciled = advance("OUTCOME_UNCERTAIN", "QUOTA_RECONCILED", 5, uncertain.event)
    committed = advance("QUOTA_RECONCILED", "COMMITTED", 6, reconciled.event)
    assert reconciled.allowed and committed.allowed

    received = advance("REQUEST_STARTED", "RESPONSE_RECEIVED", 4, dispatched.event)
    rejected = advance("RESPONSE_RECEIVED", "PARSE_REJECTED", 5, received.event)
    reconciled_parse = advance("PARSE_REJECTED", "QUOTA_RECONCILED", 6, rejected.event)
    assert received.allowed and rejected.allowed and reconciled_parse.allowed


def test_invalid_transitions_and_terminal_states_are_rejected():
    assert advance("PLANNED", "REQUEST_STARTED", 1).reason_code == "TRANSITION_NOT_ALLOWED"
    blocked = advance("PLANNED", "BLOCKED", 1)
    assert blocked.allowed
    assert advance("BLOCKED", "PREFLIGHT_APPROVED", 2, blocked.event).reason_code == "TRANSITION_NOT_ALLOWED"


def test_event_requires_aware_time_and_sha256_evidence():
    naive = advance("PLANNED", "BLOCKED", 1, at=datetime(2026, 11, 13, 12))
    bad_hash = advance("PLANNED", "BLOCKED", 1, evidence="not-a-hash")
    assert naive.reason_code == "EVENT_TIMESTAMP_INVALID"
    assert bad_hash.reason_code == "EVIDENCE_HASH_INVALID"


def test_event_chain_rejects_wrong_request_sequence_and_tampered_hash():
    first = advance("PLANNED", "PREFLIGHT_APPROVED", 1)
    wrong_sequence = advance("PREFLIGHT_APPROVED", "CREDIT_RESERVED", 3, first.event)
    wrong_request = replace(first.event, request_id="other")
    wrong_id = advance("PREFLIGHT_APPROVED", "CREDIT_RESERVED", 2, wrong_request)
    tampered = replace(first.event, reason_code="changed")
    tampered_hash = advance("PREFLIGHT_APPROVED", "CREDIT_RESERVED", 2, tampered)
    assert wrong_sequence.reason_code == "PREVIOUS_EVENT_CHAIN_MISMATCH"
    assert wrong_id.reason_code == "PREVIOUS_EVENT_CHAIN_MISMATCH"
    assert tampered_hash.reason_code == "PREVIOUS_EVENT_CHAIN_MISMATCH"


def test_event_time_must_be_monotonic():
    first = advance("PLANNED", "PREFLIGHT_APPROVED", 1)
    backwards = advance("PREFLIGHT_APPROVED", "CREDIT_RESERVED", 2, first.event, at=NOW)
    assert backwards.reason_code == "EVENT_TIME_NOT_MONOTONIC"
