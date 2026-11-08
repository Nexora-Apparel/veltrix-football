"""Durable raw-source repository with immutable idempotency semantics."""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Callable

from veltrix_v2.ingestion.ports import StoredSourceRecord


class PostgresProviderRecordRepository:
    def __init__(self, connection_factory: Callable[[], object]):
        self._connect = connection_factory

    def persist_accepted_record(self, accepted, *, raw_payload: bytes,
                                ingestion_run_id: str, idempotency_key: str) -> StoredSourceRecord:
        record = accepted.record
        digest = sha256(raw_payload).hexdigest()
        if digest != record.raw_payload_sha256:
            raise ValueError("RAW_PROVIDER_PAYLOAD_DIGEST_MISMATCH")
        if not ingestion_run_id.strip() or not idempotency_key.strip():
            raise ValueError("INGESTION_RUN_AND_IDEMPOTENCY_KEYS_REQUIRED")
        source_record_id = sha256(idempotency_key.encode("utf-8")).hexdigest()
        rights = json.dumps([
            {"allowed": item.allowed, "reason_code": item.reason_code}
            for item in accepted.rights_decisions
        ], sort_keys=True, separators=(",", ":"))
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO v2_source_records
                (source_record_id,provider,source_id,provider_record_id,provider_fixture_id,
                 provider_competition_id,provider_home_team_id,provider_away_team_id,data_class,
                 raw_payload,raw_payload_sha256,payload_reference,fetched_at_utc,ingested_at_utc,
                 source_updated_at_utc,ingestion_run_id,idempotency_key,rights_evidence)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (idempotency_key) DO NOTHING""",
                (source_record_id, record.provider, record.source_id, record.provider_record_id,
                 record.provider_fixture_id, record.provider_competition_id,
                 record.provider_home_team_id, record.provider_away_team_id, record.data_class,
                 raw_payload, digest, record.payload_reference, record.fetched_at_utc,
                 record.ingested_at_utc, record.source_updated_at_utc, ingestion_run_id,
                 idempotency_key, rights),
            )
            cur.execute(
                """SELECT source_record_id,raw_payload_sha256,payload_reference
                FROM v2_source_records WHERE idempotency_key=%s""", (idempotency_key,)
            )
            stored = cur.fetchone()
            if not stored or stored[1] != digest:
                raise ValueError("SOURCE_RECORD_IDEMPOTENCY_CONFLICT")
            if stored[0] != source_record_id:
                raise ValueError("SOURCE_RECORD_IDEMPOTENCY_KEY_COLLISION")
            conn.commit()
            return StoredSourceRecord(stored[0], stored[2], stored[1], False)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
