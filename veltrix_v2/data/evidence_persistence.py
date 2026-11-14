"""Staging-only append-only persistence for provider evidence capture reports.

No connection creation, environment lookup, network access, or automatic writes
occur in this module. Callers must explicitly supply a DB-API connection and
the verified staging target identity.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable

from veltrix_v2.data.provider_evidence_capture import (
    ProviderEvidenceCaptureReport,
    ProviderResultCapture,
    _digest,
)

_ALLOWED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
_ALLOWED_DATABASE = "veltrix_football_staging"
_ALLOWED_ROLE = "neondb_owner"
_SAFE_RESPONSE_HEADERS = {
    "content-type", "date", "etag", "last-modified", "retry-after",
    "x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining",
    "x-ratelimit-reset", "x-requests-used", "x-requests-remaining",
    "x-requests-last",
}


def _safe_response_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if headers is None:
        return {}
    if not isinstance(headers, dict):
        raise ValueError("PROVIDER_RESPONSE_HEADERS_INVALID")
    safe = {}
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("PROVIDER_RESPONSE_HEADERS_INVALID")
        normalized = key.strip().lower()
        if normalized in _SAFE_RESPONSE_HEADERS:
            if not value or len(value) > 1024:
                raise ValueError("PROVIDER_RESPONSE_HEADER_VALUE_INVALID")
            safe[normalized] = value
    return safe


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
    http_status: int = 200,
    request_params: dict[str, object] | None = None,
    response_headers: dict[str, str] | None = None,
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

    if type(http_status) is not int or not 200 <= http_status < 300:
        raise ValueError("PROVIDER_RESPONSE_HTTP_STATUS_INVALID")
    if request_params is None:
        request_params = {}
    if not isinstance(request_params, dict):
        raise ValueError("PROVIDER_REQUEST_PARAMS_INVALID")
    _json(request_params)
    safe_headers = _safe_response_headers(response_headers)
    response_hash = sha256(first.raw_response).hexdigest()
    request_fingerprint = sha256(_json({
        "provider": first.provider, "source_id": first.source_id,
        "endpoint": first.endpoint, "request_id": first.request_id,
        "requested_at": report.manifest.requested_at,
        "request_params": request_params,
    }).encode()).hexdigest()
    manifest_key = f"{first.provider}:{first.source_id}:{first.request_id}:{manifest_hash}"
    observation_ids: list[int] = []

    # psycopg connections and standard DB-API transactional connections both
    # commit on successful context exit and roll back on exceptions.
    with connection:
        with connection.cursor() as cursor:
            for approval_id in sorted({row.rights_approval.approval_id for row in rows}):
                cursor.execute(
                    """SELECT 1 FROM source_approvals
                       WHERE approval_id = %s AND provider = %s AND source_id = %s""",
                    (approval_id, first.provider, first.source_id),
                )
                if not cursor.fetchone():
                    raise ValueError("STAGING_SOURCE_APPROVAL_NOT_FOUND")

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
                    "request_params": request_params,
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
                   VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s)
                   ON CONFLICT (provider, source_id, request_id, response_sha256) DO NOTHING
                   RETURNING id""",
                (first.provider, first.source_id, first.endpoint, first.request_id,
                 _json({"capture_manifest_sha256": manifest_hash, "request_params": request_params}),
                 http_status, response_hash, first.raw_response, _json(safe_headers),
                 report.manifest.retrieved_at),
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
