"""Guarded PostgreSQL persistence for the append-only provider credit ledger.

This adapter performs database writes only when explicitly enabled for a named,
non-production database. It never loads credentials or performs provider I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from typing import Callable

from veltrix_v2.providers.odds_api_v4.reservations import (
    ReservationBudget,
    ReservationRequest,
    validate_reservation,
)


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _canonical_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class BudgetSnapshotEvidence:
    budget: ReservationBudget
    evidence_uri: str
    terms_version: str
    terms_acceptance_evidence_uri: str
    terms_acceptance_evidence_sha256: str
    rights_approval_ids: tuple[str, ...]
    provider_used: int | None = None
    provider_last_cost: int | None = None


@dataclass(frozen=True)
class ReservationEvent:
    reservation_key: str
    event_type: str
    reserved_credits: int
    actual_credits: int | None
    reason_code: str
    evidence_sha256: str
    actor: str
    occurred_at: datetime


class PostgresCreditReservationStore:
    """Narrow persistence adapter for migrations 0005 and later."""

    def __init__(
        self,
        connection_factory: Callable[[], object],
        *,
        allow_writes: bool = False,
        expected_database: str | None = None,
    ):
        self._connect = connection_factory
        self._allow_writes = allow_writes
        self._expected_database = expected_database
        if allow_writes and not expected_database:
            raise ValueError("EXPECTED_CREDIT_LEDGER_DATABASE_REQUIRED")
        if allow_writes and expected_database in {
            "veltrix-football", "veltrix_football",
        }:
            raise RuntimeError("PRODUCTION_CREDIT_LEDGER_WRITES_DISABLED")

    def _connect_for_write(self):
        if not self._allow_writes:
            raise RuntimeError("CREDIT_LEDGER_WRITES_DISABLED")
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT current_database()")
            row = cur.fetchone()
            if not row or row[0] != self._expected_database:
                raise RuntimeError("CREDIT_LEDGER_DATABASE_TARGET_MISMATCH")
            return conn
        except Exception:
            conn.close()
            raise

    def persist_budget_snapshot(self, evidence: BudgetSnapshotEvidence) -> int:
        """Append one account/period budget snapshot; exact evidence replay is idempotent."""
        if not isinstance(evidence, BudgetSnapshotEvidence):
            raise ValueError("CREDIT_BUDGET_EVIDENCE_TYPE_INVALID")
        budget = evidence.budget
        if not isinstance(budget, ReservationBudget):
            raise ValueError("CREDIT_BUDGET_TYPE_INVALID")
        if not all(isinstance(value, str) and value.strip() for value in (
            budget.provider, budget.account_ref, evidence.evidence_uri,
            evidence.terms_version, evidence.terms_acceptance_evidence_uri,
        )):
            raise ValueError("CREDIT_BUDGET_IDENTITY_OR_EVIDENCE_MISSING")
        if (not _sha256(budget.evidence_sha256)
                or not _sha256(evidence.terms_acceptance_evidence_sha256)):
            raise ValueError("CREDIT_BUDGET_EVIDENCE_HASH_INVALID")
        if (not isinstance(budget.period_start, date)
                or isinstance(budget.period_start, datetime)
                or not isinstance(budget.period_end, date)
                or isinstance(budget.period_end, datetime)
                or budget.period_end <= budget.period_start):
            raise ValueError("CREDIT_BUDGET_PERIOD_INVALID")
        if (not _aware(budget.observed_at) or not _aware(budget.valid_until)
                or budget.valid_until <= budget.observed_at):
            raise ValueError("CREDIT_BUDGET_TIME_INVALID")
        limits = (
            budget.monthly_allowance, budget.provider_remaining,
            budget.monthly_hard_cap, budget.per_run_hard_cap,
            budget.request_count_cap,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
               for value in limits):
            raise ValueError("CREDIT_BUDGET_COUNTER_INVALID")
        if any(value == 0 for value in (
            budget.monthly_allowance, budget.monthly_hard_cap,
            budget.per_run_hard_cap, budget.request_count_cap,
        )):
            raise ValueError("CREDIT_BUDGET_CAP_MUST_BE_POSITIVE")
        for value in (evidence.provider_used, evidence.provider_last_cost):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError("CREDIT_BUDGET_OPTIONAL_COUNTER_INVALID")
        if (not isinstance(evidence.rights_approval_ids, tuple)
                or not evidence.rights_approval_ids
                or any(not isinstance(item, str) or not item.strip()
                       for item in evidence.rights_approval_ids)
                or len(set(evidence.rights_approval_ids)) != len(evidence.rights_approval_ids)):
            raise ValueError("CREDIT_BUDGET_RIGHTS_LINKS_INVALID")

        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            snapshot_lock_key = (
                f"{budget.provider}|{budget.account_ref}|{budget.period_start}|"
                f"{budget.period_end}|{budget.evidence_sha256}"
            )
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (snapshot_lock_key,),
            )
            cur.execute(
                """SELECT budget_snapshot_id,provider,provider_account_ref,
                          billing_period_start,billing_period_end,monthly_allowance,
                          provider_remaining,monthly_hard_cap,per_run_hard_cap,
                          request_count_cap,provider_used,provider_last_cost,observed_at,
                          valid_until,evidence_uri,evidence_sha256,terms_version,
                          terms_acceptance_evidence_uri,terms_acceptance_evidence_sha256,
                          rights_approval_ids
                   FROM provider_credit_budget_snapshots
                   WHERE provider=%s AND provider_account_ref=%s
                     AND billing_period_start=%s AND billing_period_end=%s
                     AND evidence_sha256=%s""",
                (budget.provider, budget.account_ref, budget.period_start,
                 budget.period_end, budget.evidence_sha256),
            )
            prior = cur.fetchone()
            expected = (
                budget.provider, budget.account_ref, budget.period_start,
                budget.period_end, budget.monthly_allowance, budget.provider_remaining,
                budget.monthly_hard_cap, budget.per_run_hard_cap,
                budget.request_count_cap, evidence.provider_used,
                evidence.provider_last_cost, budget.observed_at, budget.valid_until,
                evidence.evidence_uri, budget.evidence_sha256, evidence.terms_version,
                evidence.terms_acceptance_evidence_uri,
                evidence.terms_acceptance_evidence_sha256,
                list(evidence.rights_approval_ids),
            )
            if prior:
                stored = tuple(prior[1:19]) + (
                    list(prior[19] or []) if isinstance(prior[19], (list, tuple)) else prior[19],
                )
                if stored != expected:
                    raise ValueError("CREDIT_BUDGET_EVIDENCE_IDEMPOTENCY_CONFLICT")
                conn.commit()
                return int(prior[0])

            cur.execute(
                """INSERT INTO provider_credit_budget_snapshots (
                    provider,provider_account_ref,billing_period_start,billing_period_end,
                    monthly_allowance,provider_remaining,monthly_hard_cap,per_run_hard_cap,
                    request_count_cap,provider_used,provider_last_cost,observed_at,valid_until,
                    evidence_uri,evidence_sha256,terms_version,terms_acceptance_evidence_uri,
                    terms_acceptance_evidence_sha256,rights_approval_ids
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                RETURNING budget_snapshot_id""",
                (
                    budget.provider, budget.account_ref, budget.period_start,
                    budget.period_end, budget.monthly_allowance, budget.provider_remaining,
                    budget.monthly_hard_cap, budget.per_run_hard_cap,
                    budget.request_count_cap, evidence.provider_used,
                    evidence.provider_last_cost, budget.observed_at, budget.valid_until,
                    evidence.evidence_uri, budget.evidence_sha256, evidence.terms_version,
                    evidence.terms_acceptance_evidence_uri,
                    evidence.terms_acceptance_evidence_sha256,
                    json.dumps(list(evidence.rights_approval_ids)),
                ),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("CREDIT_BUDGET_SNAPSHOT_INSERT_FAILED")
            conn.commit()
            return int(row[0])
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def reserve(
        self,
        request: ReservationRequest,
        budget: ReservationBudget,
        *,
        budget_snapshot_id: int,
        actor: str,
        now: datetime,
    ) -> int:
        """Atomically reserve credits using the migration's account-period lock."""
        decision = validate_reservation(request, budget, now=now)
        if not decision.allowed:
            raise ValueError(decision.reason_code)
        if (not isinstance(budget_snapshot_id, int)
                or isinstance(budget_snapshot_id, bool) or budget_snapshot_id < 1):
            raise ValueError("CREDIT_BUDGET_SNAPSHOT_ID_INVALID")
        if not isinstance(actor, str) or not actor.strip():
            raise ValueError("CREDIT_RESERVATION_ACTOR_REQUIRED")
        evidence_hash = _canonical_hash({
            "budget_evidence_sha256": budget.evidence_sha256,
            "request_fingerprint": request.request_fingerprint,
            "reservation_key": request.reservation_key,
            "estimated_credits": request.estimated_credits,
        })
        event_hash = _canonical_hash({
            "reservation_key": request.reservation_key,
            "event_sequence": 1,
            "event_type": "RESERVED",
            "request_fingerprint": request.request_fingerprint,
            "budget_snapshot_id": budget_snapshot_id,
            "reserved_credits": request.estimated_credits,
            "evidence_sha256": evidence_hash,
            "actor": actor.strip(),
            "occurred_at": request.requested_at.isoformat(),
        })
        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT reserve_provider_credits(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )""",
                (
                    request.reservation_key, request.provider, request.account_ref,
                    request.period_start, request.period_end, request.run_key,
                    request.manifest_id, request.request_key, request.attempt_number,
                    request.request_fingerprint, request.estimated_credits,
                    budget_snapshot_id, actor.strip(), request.requested_at,
                    evidence_hash, event_hash,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("CREDIT_RESERVATION_INSERT_FAILED")
            conn.commit()
            return int(row[0])
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def append_event(self, event: ReservationEvent) -> int:
        """Append a reservation lifecycle event with serialized hash-chain construction."""
        if not isinstance(event, ReservationEvent):
            raise ValueError("CREDIT_RESERVATION_EVENT_TYPE_INVALID")
        if (not isinstance(event.reservation_key, str) or not event.reservation_key.strip()
                or not isinstance(event.event_type, str) or not event.event_type.strip()
                or not isinstance(event.reason_code, str) or not event.reason_code.strip()
                or not isinstance(event.actor, str) or not event.actor.strip()
                or not _sha256(event.evidence_sha256)
                or not _aware(event.occurred_at)):
            raise ValueError("CREDIT_RESERVATION_EVENT_INPUT_INVALID")
        if (not isinstance(event.reserved_credits, int)
                or isinstance(event.reserved_credits, bool) or event.reserved_credits < 0):
            raise ValueError("CREDIT_RESERVATION_AMOUNT_INVALID")
        if event.event_type in {"RECONCILED", "OVERRUN"}:
            if (not isinstance(event.actual_credits, int)
                    or isinstance(event.actual_credits, bool) or event.actual_credits < 0):
                raise ValueError("CREDIT_RESERVATION_ACTUAL_AMOUNT_REQUIRED")
        elif event.actual_credits is not None:
            raise ValueError("CREDIT_RESERVATION_ACTUAL_AMOUNT_FORBIDDEN")

        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT provider,provider_account_ref,billing_period_start,
                          billing_period_end
                   FROM provider_credit_reservation_events
                   WHERE reservation_key=%s AND event_sequence=1""",
                (event.reservation_key,),
            )
            initial = cur.fetchone()
            if not initial:
                raise ValueError("CREDIT_RESERVATION_NOT_FOUND")
            lock_key = (
                f"{initial[0]}|{initial[1]}|{initial[2]}|{initial[3]}"
            )
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (lock_key,),
            )
            cur.execute(
                """SELECT event_sequence,event_type,reserved_credits,event_sha256,
                          occurred_at
                   FROM provider_credit_reservation_events
                   WHERE reservation_key=%s
                   ORDER BY event_sequence DESC LIMIT 1""",
                (event.reservation_key,),
            )
            prior = cur.fetchone()
            if not prior:
                raise ValueError("CREDIT_RESERVATION_NOT_FOUND")
            if event.occurred_at < prior[4]:
                raise ValueError("CREDIT_RESERVATION_EVENT_TIME_NOT_MONOTONIC")
            if event.reserved_credits != prior[2]:
                raise ValueError("CREDIT_RESERVATION_AMOUNT_IMMUTABLE")
            sequence = int(prior[0]) + 1
            event_hash = _canonical_hash({
                "reservation_key": event.reservation_key,
                "event_sequence": sequence,
                "event_type": event.event_type,
                "reserved_credits": event.reserved_credits,
                "actual_credits": event.actual_credits,
                "reason_code": event.reason_code,
                "evidence_sha256": event.evidence_sha256,
                "previous_event_sha256": prior[3],
                "actor": event.actor.strip(),
                "occurred_at": event.occurred_at.isoformat(),
            })
            cur.execute(
                """SELECT append_provider_credit_reservation_event(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s
                )""",
                (
                    event.reservation_key, event.event_type,
                    event.reserved_credits, event.actual_credits,
                    event.reason_code, event.evidence_sha256, event_hash,
                    event.actor.strip(), event.occurred_at,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("CREDIT_RESERVATION_EVENT_INSERT_FAILED")
            conn.commit()
            return int(row[0])
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
