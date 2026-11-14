"""Staging-only append-only persistence for provider evidence capture reports.

No connection creation, environment lookup, network access, or automatic writes
occur in this module. Callers must explicitly supply a DB-API connection and
the verified staging target identity.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, SourceApproval
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.data.provider_evidence_capture import (
    ProviderEvidenceCaptureReport,
    ProviderResultCapture,
    _digest,
)

_ALLOWED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
_ALLOWED_DATABASE = "veltrix_football_staging"
_ALLOWED_ROLE = "neondb_owner"


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _fetch_id(cursor: Any, insert_sql: str, insert_params: tuple,
              select_sql: str, select_params: tuple) -> int:
    cursor.execute(insert_sql, insert_params)
    row = cursor.fetchone()
    if row:
        return int(row[0])
    cursor.execute(select_sql, select_params)
    row = cursor.fetchone()
    if not row:
        raise RuntimeError("APPEND_ONLY_PERSISTENCE_ID_LOOKUP_FAILED")
    return int(row[0])


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def build_fixture_snapshot_manifest(
    *,
    provider: str,
    source_id: str,
    endpoint: str,
    request_id: str,
    request_params: Mapping[str, object],
    requested_at: datetime,
    retrieved_at: datetime,
    recorded_at: datetime,
    raw_response: bytes,
    competition_id: str,
    fixture_count: int,
    rights_approval_id: str,
) -> dict[str, str]:
    """Build deterministic hashes for a raw upcoming-fixture page snapshot."""
    if (provider, source_id) != ("5DollarFootballAPI", "5dollarfootballapi"):
        raise ValueError("FIXTURE_SNAPSHOT_PROVIDER_NOT_ALLOWED")
    if not all(isinstance(value, str) and value.strip() for value in (
        endpoint, request_id, competition_id, rights_approval_id
    )):
        raise ValueError("FIXTURE_SNAPSHOT_IDENTITY_INVALID")
    if not isinstance(request_params, Mapping):
        raise ValueError("FIXTURE_SNAPSHOT_REQUEST_PARAMS_INVALID")
    if not all(_aware(value) for value in (requested_at, retrieved_at, recorded_at)):
        raise ValueError("FIXTURE_SNAPSHOT_TIMESTAMP_NOT_AWARE")
    if not requested_at <= retrieved_at <= recorded_at:
        raise ValueError("FIXTURE_SNAPSHOT_TIMESTAMP_ORDER_INVALID")
    if not isinstance(raw_response, bytes) or not raw_response:
        raise ValueError("FIXTURE_SNAPSHOT_RAW_RESPONSE_INVALID")
    if type(fixture_count) is not int or fixture_count < 0:
        raise ValueError("FIXTURE_SNAPSHOT_FIXTURE_COUNT_INVALID")

    response_hash = sha256(raw_response).hexdigest()
    body = {
        "schema_version": "fixture_snapshot_page_v1",
        "provider": provider,
        "source_id": source_id,
        "endpoint": endpoint,
        "request_id": request_id,
        "request_params": dict(request_params),
        "requested_at": requested_at.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "recorded_at": recorded_at.isoformat(),
        "response_sha256": response_hash,
        "competition_id": competition_id,
        "status_filter": "scheduled",
        "fixture_count": fixture_count,
        "rights_approval_id": rights_approval_id,
        "rights_evaluated_at": recorded_at.isoformat(),
    }
    manifest_hash = sha256(_json(body).encode("utf-8")).hexdigest()
    return {
        "response_sha256": response_hash,
        "manifest_sha256": manifest_hash,
    }


def persist_fixture_snapshot_response(
    connection: Any,
    *,
    provider: str,
    source_id: str,
    endpoint: str,
    request_id: str,
    request_params: Mapping[str, object],
    requested_at: datetime,
    retrieved_at: datetime,
    recorded_at: datetime,
    raw_response: bytes,
    response_headers: Mapping[str, str],
    competition_id: str,
    fixture_count: int,
    rights_approval: SourceApproval,
    write_enabled: bool = False,
    environment: str = "unknown",
    database_name: str = "",
    host: str = "",
    role: str = "",
) -> dict[str, str | int]:
    """Persist one scheduled-fixture raw page and its manifest in staging only."""
    if write_enabled is not True:
        raise PermissionError("FIXTURE_SNAPSHOT_PERSISTENCE_WRITE_GUARD_DISABLED")
    if (environment, database_name, host, role) != (
        "staging", _ALLOWED_DATABASE, _ALLOWED_HOST, _ALLOWED_ROLE
    ):
        raise PermissionError("FIXTURE_SNAPSHOT_PERSISTENCE_TARGET_NOT_ALLOWLISTED")
    if not isinstance(rights_approval, SourceApproval):
        raise TypeError("FIXTURE_SNAPSHOT_SOURCE_APPROVAL_REQUIRED")
    if (
        rights_approval.status is not ApprovalStatus.APPROVED
        or rights_approval.provider != provider
        or rights_approval.source_id != source_id
        or competition_id not in {
            value.strip() for value in rights_approval.competition_scope.split(",")
        }
    ):
        raise PermissionError("FIXTURE_SNAPSHOT_SOURCE_RIGHTS_SCOPE_INVALID")

    hashes = build_fixture_snapshot_manifest(
        provider=provider,
        source_id=source_id,
        endpoint=endpoint,
        request_id=request_id,
        request_params=request_params,
        requested_at=requested_at,
        retrieved_at=retrieved_at,
        recorded_at=recorded_at,
        raw_response=raw_response,
        competition_id=competition_id,
        fixture_count=fixture_count,
        rights_approval_id=rights_approval.approval_id,
    )
    for purpose in (DataUsePurpose.STORAGE, DataUsePurpose.CACHE):
        decision = evaluate_source_use(
            rights_approval, purpose, at_utc=recorded_at, commercial=True
        )
        if not decision.allowed:
            raise PermissionError(decision.reason_code)

    response_hash = hashes["response_sha256"]
    manifest_hash = hashes["manifest_sha256"]
    manifest_key = f"{provider}:{source_id}:{request_id}:{manifest_hash}"
    request_fingerprint = sha256(_json({
        "endpoint": endpoint,
        "request_params": dict(request_params),
        "requested_at": requested_at.isoformat(),
    }).encode("utf-8")).hexdigest()
    scope = {
        "provider": provider,
        "source_id": source_id,
        "endpoint": endpoint,
        "request_id": request_id,
        "data_domain": "FIXTURES",
        "status_filter": "scheduled",
        "competition_id": competition_id,
        "fixture_count": fixture_count,
        "response_sha256": response_hash,
    }
    headers = {
        str(key).lower(): str(value)
        for key, value in response_headers.items()
        if str(key).lower() in {
            "content-type", "date", "x-ratelimit-limit",
            "x-ratelimit-remaining", "x-ratelimit-used",
        }
    }

    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT evidence_sha256 FROM source_approvals
                   WHERE approval_id = %s AND provider = %s AND source_id = %s""",
                (rights_approval.approval_id, provider, source_id),
            )
            approval_row = cursor.fetchone()
            if not approval_row:
                raise ValueError("STAGING_SOURCE_APPROVAL_NOT_FOUND")
            if approval_row[0] != rights_approval.evidence_sha256:
                raise ValueError("STAGING_SOURCE_APPROVAL_EVIDENCE_MISMATCH")

            manifest_id = _fetch_id(
                cursor,
                """INSERT INTO capture_manifests
                   (manifest_key, manifest_sha256, capture_scope, requests_planned)
                   VALUES (%s, %s, %s::jsonb, 1)
                   ON CONFLICT (manifest_key) DO NOTHING
                   RETURNING capture_manifest_id""",
                (manifest_key, manifest_hash, _json(scope)),
                "SELECT capture_manifest_id FROM capture_manifests WHERE manifest_key = %s",
                (manifest_key,),
            )
            cursor.execute(
                """SELECT 1 FROM capture_manifest_events
                   WHERE capture_manifest_id = %s AND reason_code = %s
                     AND evidence_sha256 = %s""",
                (manifest_id, "FIXTURE_SNAPSHOT_PAGE_PERSISTED", manifest_hash),
            )
            if not cursor.fetchone():
                cursor.execute(
                    """INSERT INTO capture_manifest_events
                       (capture_manifest_id, status, event_at, reason_code,
                        evidence_sha256, coverage_summary)
                       VALUES (%s, 'COMPLETED', %s, %s, %s, %s::jsonb)""",
                    (manifest_id, recorded_at, "FIXTURE_SNAPSHOT_PAGE_PERSISTED",
                     manifest_hash, _json({
                         "competition_id": competition_id,
                         "fixture_count": fixture_count,
                         "response_sha256": response_hash,
                     })),
                )

            response_id = _fetch_id(
                cursor,
                """INSERT INTO provider_responses
                   (provider, source_id, endpoint, request_id, request_params,
                    http_status, response_sha256, raw_body, response_headers, fetched_at)
                   VALUES (%s, %s, %s, %s, %s::jsonb, 200, %s, %s, %s::jsonb, %s)
                   ON CONFLICT (provider, source_id, request_id, response_sha256) DO NOTHING
                   RETURNING id""",
                (provider, source_id, endpoint, request_id, _json(dict(request_params)),
                 response_hash, raw_response, _json(headers), retrieved_at),
                """SELECT id FROM provider_responses
                   WHERE provider = %s AND source_id = %s AND request_id = %s
                     AND response_sha256 = %s""",
                (provider, source_id, request_id, response_hash),
            )
            cursor.execute(
                """INSERT INTO provider_capture_requests
                   (capture_manifest_id, provider, source_id, endpoint, request_key,
                    request_fingerprint, attempt_number, requested_at, response_id, outcome)
                   VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, 'RESPONSE')
                   ON CONFLICT (capture_manifest_id, request_key, attempt_number) DO NOTHING""",
                (manifest_id, provider, source_id, endpoint, request_id,
                 request_fingerprint, requested_at, response_id),
            )
    return {
        "capture_manifest_id": manifest_id,
        "provider_response_id": response_id,
        "manifest_sha256": manifest_hash,
        "response_sha256": response_hash,
    }


def persist_provider_evidence_report(
    connection: Any,
    report: ProviderEvidenceCaptureReport,
    captures: Iterable[ProviderResultCapture],
    *,
    write_enabled: bool = False,
    environment: str = "unknown",
    database_name: str = "",
    host: str = "",
    role: str = "",
) -> dict[str, int]:
    """Persist a complete report atomically to the explicitly allowlisted staging DB.

    The function is disabled by default. It verifies report/capture linkage before
    opening a transaction, then appends manifest, raw response, request and
    observation rows. Replays are idempotent. It never writes to production.
    """
    if write_enabled is not True:
        raise PermissionError("EVIDENCE_PERSISTENCE_WRITE_GUARD_DISABLED")
    if (environment, database_name, host, role) != (
        "staging", _ALLOWED_DATABASE, _ALLOWED_HOST, _ALLOWED_ROLE
    ):
        raise PermissionError("EVIDENCE_PERSISTENCE_TARGET_NOT_ALLOWLISTED")
    if not isinstance(report, ProviderEvidenceCaptureReport):
        raise TypeError("PROVIDER_EVIDENCE_REPORT_REQUIRED")
    rows = tuple(captures)
    if len(rows) != report.manifest.item_count or len(rows) != len(report.observations):
        raise ValueError("CAPTURE_EVIDENCE_ROW_COUNT_MISMATCH")
    item_hashes = tuple(_digest(item.as_dict()) for item in report.observations)
    if item_hashes != report.manifest.item_evidence_sha256:
        raise ValueError("CAPTURE_EVIDENCE_ITEM_HASH_MISMATCH")
    manifest_body = report.manifest.as_dict()
    manifest_hash = manifest_body.pop("manifest_sha256", None)
    if not isinstance(manifest_hash, str) or sha256(_json(manifest_body).encode()).hexdigest() != manifest_hash:
        raise ValueError("CAPTURE_EVIDENCE_MANIFEST_HASH_MISMATCH")

    first = rows[0] if rows else None
    if first is None:
        raise ValueError("EMPTY_EVIDENCE_CAPTURE_BATCH")
    for row, evidence in zip(rows, report.observations):
        if (
            not isinstance(row.raw_response, bytes)
            or sha256(row.raw_response).hexdigest() != evidence.raw_response_sha256
            or row.provider != report.manifest.provider
            or row.source_id != report.manifest.source_id
            or row.endpoint != report.manifest.endpoint
            or row.request_id != report.manifest.request_id
            or row.provider_fixture_id != evidence.provider_fixture_id
        ):
            raise ValueError("CAPTURE_EVIDENCE_SOURCE_ROW_MISMATCH")
    if any(row.raw_response != first.raw_response for row in rows):
        raise ValueError("CAPTURE_BATCH_RAW_RESPONSE_MISMATCH")

    response_hash = sha256(first.raw_response).hexdigest()
    request_fingerprint = sha256(_json({
        "provider": first.provider, "source_id": first.source_id,
        "endpoint": first.endpoint, "request_id": first.request_id,
        "requested_at": report.manifest.requested_at,
    }).encode()).hexdigest()
    manifest_key = f"{first.provider}:{first.source_id}:{first.request_id}:{manifest_hash}"
    observation_ids: list[int] = []

    # psycopg connections and standard DB-API transactional connections both
    # commit on successful context exit and roll back on exceptions.
    with connection:
        with connection.cursor() as cursor:
            for approval_id in sorted({row.rights_approval.approval_id for row in rows}):
                approval = next(
                    row.rights_approval for row in rows
                    if row.rights_approval.approval_id == approval_id
                )
                cursor.execute(
                    """SELECT evidence_sha256 FROM source_approvals
                       WHERE approval_id = %s AND provider = %s AND source_id = %s""",
                    (approval_id, first.provider, first.source_id),
                )
                approval_row = cursor.fetchone()
                if not approval_row:
                    raise ValueError("STAGING_SOURCE_APPROVAL_NOT_FOUND")
                if approval_row[0] != approval.evidence_sha256:
                    raise ValueError("STAGING_SOURCE_APPROVAL_EVIDENCE_MISMATCH")

            manifest_id = _fetch_id(
                cursor,
                """INSERT INTO capture_manifests
                   (manifest_key, manifest_sha256, capture_scope, requests_planned)
                   VALUES (%s, %s, %s::jsonb, 1)
                   ON CONFLICT (manifest_key) DO NOTHING
                   RETURNING capture_manifest_id""",
                (manifest_key, manifest_hash, _json({
                    "provider": first.provider, "source_id": first.source_id,
                    "endpoint": first.endpoint, "request_id": first.request_id,
                    "item_count": report.manifest.item_count,
                    "certified_count": report.manifest.certified_count,
                    "rejected_count": report.manifest.rejected_count,
                })),
                "SELECT capture_manifest_id FROM capture_manifests WHERE manifest_key = %s",
                (manifest_key,),
            )
            cursor.execute(
                """SELECT 1 FROM capture_manifest_events
                   WHERE capture_manifest_id = %s AND reason_code = %s
                     AND evidence_sha256 = %s""",
                (manifest_id, "EVIDENCE_CAPTURE_PERSISTED", manifest_hash),
            )
            if not cursor.fetchone():
                cursor.execute(
                    """INSERT INTO capture_manifest_events
                       (capture_manifest_id, status, event_at, reason_code,
                        evidence_sha256, coverage_summary)
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
                    (manifest_id, "COMPLETED" if report.manifest.rejected_count == 0 else "PARTIAL",
                     report.manifest.recorded_at, "EVIDENCE_CAPTURE_PERSISTED", manifest_hash,
                     _json({"item_count": report.manifest.item_count,
                            "certified_count": report.manifest.certified_count,
                            "rejected_count": report.manifest.rejected_count})),
                )

            response_id = _fetch_id(
                cursor,
                """INSERT INTO provider_responses
                   (provider, source_id, endpoint, request_id, request_params,
                    http_status, response_sha256, raw_body, response_headers, fetched_at)
                   VALUES (%s, %s, %s, %s, %s::jsonb, 200, %s, %s, '{}'::jsonb, %s)
                   ON CONFLICT (provider, source_id, request_id, response_sha256) DO NOTHING
                   RETURNING id""",
                (first.provider, first.source_id, first.endpoint, first.request_id,
                 _json({"capture_manifest_sha256": manifest_hash}), response_hash,
                 first.raw_response, report.manifest.retrieved_at),
                """SELECT id FROM provider_responses
                   WHERE provider = %s AND source_id = %s AND request_id = %s
                     AND response_sha256 = %s""",
                (first.provider, first.source_id, first.request_id, response_hash),
            )
            cursor.execute(
                """INSERT INTO provider_capture_requests
                   (capture_manifest_id, provider, source_id, endpoint, request_key,
                    request_fingerprint, attempt_number, requested_at, response_id, outcome)
                   VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s, 'RESPONSE')
                   ON CONFLICT (capture_manifest_id, request_key, attempt_number) DO NOTHING""",
                (manifest_id, first.provider, first.source_id, first.endpoint,
                 first.request_id, request_fingerprint, report.manifest.requested_at, response_id),
            )

            for evidence, item_hash in zip(report.observations, item_hashes):
                payload = evidence.as_dict()
                payload["manifest_sha256"] = manifest_hash
                payload["item_evidence_sha256"] = item_hash
                observation_id = _fetch_id(
                    cursor,
                    """INSERT INTO source_observations
                       (provider, source_id, endpoint, entity_type, provider_entity_id,
                        data_type, payload_sha256, retrieved_at, payload, source_event_time,
                        available_at, availability_basis, rights_approval_id, provider_response_id,
                        point_in_time_certifiable, source_published_at, source_effective_at,
                        recorded_at, source_timestamp_raw, source_timestamp_basis)
                       VALUES (%s, %s, %s, 'FIXTURE_RESULT', %s, 'fixture_result',
                               %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (provider, endpoint, entity_type, provider_entity_id, payload_sha256)
                       DO NOTHING RETURNING id""",
                    (evidence.provider, evidence.source_id, report.manifest.endpoint,
                     evidence.provider_fixture_id, item_hash, report.manifest.retrieved_at,
                     _json(payload), evidence.kickoff_at, evidence.available_at,
                     evidence.availability_timestamp_basis, evidence.rights_approval_id,
                     response_id, evidence.point_in_time_certifiable,
                     evidence.source_published_at, evidence.source_effective_at,
                     evidence.recorded_at, evidence.source_published_at,
                     evidence.source_timestamp_basis),
                    """SELECT id FROM source_observations
                       WHERE provider = %s AND endpoint = %s AND entity_type = 'FIXTURE_RESULT'
                         AND provider_entity_id = %s AND payload_sha256 = %s""",
                    (evidence.provider, report.manifest.endpoint,
                     evidence.provider_fixture_id, item_hash),
                )
                observation_ids.append(observation_id)

    return {
        "manifest_id": manifest_id,
        "provider_response_id": response_id,
        "observation_count": len(observation_ids),
        "certified_observation_count": report.manifest.certified_count,
        "rejected_observation_count": report.manifest.rejected_count,
    }
