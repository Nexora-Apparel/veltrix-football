"""Durable fixture-source decisions; ambiguous identities are quarantined."""
from __future__ import annotations
import json
from hashlib import sha256
from datetime import datetime, timezone
from typing import Callable
from veltrix_v2.domain.identity import ReconciliationDecision, ReconciliationStatus
from veltrix_v2.identity.registry import MappingResolutionStatus, ProviderFixtureSourceIdentity, ResolvedProviderFixture


class PostgresFixtureDecisionRepository:
    def __init__(self, connection_factory: Callable[[], object]):
        self._connect=connection_factory

    def persist_decision(self, source: ProviderFixtureSourceIdentity, source_record_id: str,
                         mapping: ResolvedProviderFixture, *, decided_at_utc: datetime,
                         reconciliation: ReconciliationDecision | None = None,
                         new_canonical_fixture_id: str | None = None) -> str:
        if not source_record_id.strip():
            raise ValueError("source_record_id is required")
        if decided_at_utc.tzinfo is None or decided_at_utc.utcoffset() is None:
            raise ValueError("decided_at_utc must be timezone-aware")
        if mapping.source_identity != source:
            raise ValueError("SOURCE_IDENTITY_MISMATCH")
        canonical_id=None
        status=mapping.status.value
        reason=mapping.reason_code
        candidates=()
        mapped=mapping.canonical_identity
        if mapping.status is MappingResolutionStatus.VERIFIED:
            if mapped is None:
                raise ValueError("VERIFIED_MAPPING_WITHOUT_CANONICAL_IDENTITY")
            if reconciliation is not None:
                if reconciliation.provider_record != mapped:
                    raise ValueError("RECONCILIATION_SOURCE_IDENTITY_MISMATCH")
                status=reconciliation.status.value
                candidates=reconciliation.candidate_fixture_ids
                if reconciliation.status is ReconciliationStatus.MATCHED_EXISTING:
                    canonical_id=reconciliation.canonical_fixture_id
                elif reconciliation.status is ReconciliationStatus.NEW_CANONICAL_FIXTURE:
                    canonical_id=new_canonical_fixture_id
                    if not canonical_id:
                        raise ValueError("NEW_CANONICAL_FIXTURE_ID_REQUIRED")
                elif reconciliation.status in {ReconciliationStatus.AMBIGUOUS,
                                                 ReconciliationStatus.UNRESOLVED_IDENTITY}:
                    canonical_id=None
                reason=f"RECONCILIATION_{reconciliation.status.value}"
            elif new_canonical_fixture_id is not None:
                raise ValueError("CANONICAL_FIXTURE_ID_WITHOUT_RECONCILIATION")
            else:
                status="MAPPED_PENDING_CANONICAL_RECONCILIATION"
        elif reconciliation is not None or new_canonical_fixture_id is not None:
            raise ValueError("UNVERIFIED_PROVIDER_IDENTITY_CANNOT_BE_RECONCILED")

        if reconciliation and reconciliation.status is ReconciliationStatus.MATCHED_EXISTING and not canonical_id:
            raise ValueError("MATCHED_FIXTURE_ID_MISSING")
        if reconciliation and reconciliation.status in {ReconciliationStatus.AMBIGUOUS,
                                                          ReconciliationStatus.UNRESOLVED_IDENTITY} and new_canonical_fixture_id:
            raise ValueError("AMBIGUOUS_FIXTURE_CANNOT_RECEIVE_CANONICAL_ID")

        evidence=tuple(dict.fromkeys(mapping.evidence_refs))
        conn=self._connect()
        try:
            cur=conn.cursor()
            # Confirm the source record belongs to this exact provider fixture.
            cur.execute("""SELECT provider,source_id,provider_fixture_id
                FROM v2_source_records WHERE source_record_id=%s""",(source_record_id,))
            stored_source=cur.fetchone()
            expected_source=(source.provider,source.source_id,source.provider_fixture_id)
            if not stored_source or tuple(stored_source)!=expected_source:
                raise ValueError("SOURCE_RECORD_PROVIDER_FIXTURE_MISMATCH")

            if status in {ReconciliationStatus.NEW_CANONICAL_FIXTURE.value,
                          ReconciliationStatus.MATCHED_EXISTING.value}:
                if status==ReconciliationStatus.NEW_CANONICAL_FIXTURE.value:
                    cur.execute("""INSERT INTO v2_canonical_fixtures
                        (canonical_fixture_id,canonical_competition_id,squad_category,
                         canonical_home_team_id,canonical_away_team_id,kickoff_at_utc)
                        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(canonical_fixture_id) DO NOTHING""",
                        (canonical_id,mapped.canonical_competition_id,mapped.squad_category.value,
                         mapped.canonical_home_team_id,mapped.canonical_away_team_id,mapped.kickoff_at_utc))
                cur.execute("""SELECT canonical_competition_id,squad_category,canonical_home_team_id,
                    canonical_away_team_id,kickoff_at_utc FROM v2_canonical_fixtures
                    WHERE canonical_fixture_id=%s""",(canonical_id,))
                expected=(mapped.canonical_competition_id,mapped.squad_category.value,
                          mapped.canonical_home_team_id,mapped.canonical_away_team_id,mapped.kickoff_at_utc)
                stored_fixture=cur.fetchone()
                if stored_fixture is None or tuple(stored_fixture)!=expected:
                    raise ValueError("CANONICAL_FIXTURE_IDENTITY_CONFLICT")
            cur.execute("""INSERT INTO v2_fixture_sources
                (provider,source_id,provider_fixture_id,provider_competition_id,
                 provider_home_team_id,provider_away_team_id,canonical_fixture_id,
                 source_record_id,identity_status,reason_code,evidence_refs)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT DO NOTHING""",
                (source.provider,source.source_id,source.provider_fixture_id,
                 source.provider_competition_id,source.provider_home_team_id,source.provider_away_team_id,
                 canonical_id,source_record_id,status,reason,json.dumps(evidence)))
            cur.execute("""SELECT canonical_fixture_id,identity_status,reason_code
                FROM v2_fixture_sources WHERE provider=%s AND source_id=%s
                AND provider_fixture_id=%s AND source_record_id=%s""",
                (source.provider,source.source_id,source.provider_fixture_id,source_record_id))
            stored=cur.fetchone()
            if not stored or tuple(stored)!=(canonical_id,status,reason):
                raise ValueError("FIXTURE_SOURCE_IDEMPOTENCY_CONFLICT")
            quarantine=status in {ReconciliationStatus.AMBIGUOUS.value,
                ReconciliationStatus.UNRESOLVED_IDENTITY.value,MappingResolutionStatus.AMBIGUOUS.value,
                MappingResolutionStatus.UNRESOLVED.value,MappingResolutionStatus.UNVERIFIED.value,
                MappingResolutionStatus.INVALID_MAPPING.value,MappingResolutionStatus.SQUAD_CATEGORY_MISMATCH.value}
            if quarantine:
                quarantine_id=sha256("|".join((source.provider,source.source_id,
                    source.provider_fixture_id,source_record_id,status)).encode()).hexdigest()
                cur.execute("""INSERT INTO v2_identity_quarantine
                    (quarantine_id,provider,source_id,provider_fixture_id,source_record_id,
                     status,reason_code,candidate_ids,created_at_utc)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                    ON CONFLICT(quarantine_id) DO NOTHING""",
                    (quarantine_id,source.provider,source.source_id,source.provider_fixture_id,
                     source_record_id,status,reason,json.dumps(candidates),decided_at_utc.astimezone(timezone.utc)))
            conn.commit()
            return status
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
