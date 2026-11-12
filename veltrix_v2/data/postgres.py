"""PostgreSQL adapter for the existing public VELTRIX history schema.

This adapter writes only when explicitly called with a connection to a non-production
staging target. Source observations and provider responses are append-only; current
fixture rows are updated only after provider identity consistency is verified.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, Iterable

from veltrix_v2.data.contracts import (
    ApprovalStatus, HistoricalFixture, ProviderResponse, SourceApproval,
)
from veltrix_v2.data.rights import evaluate_fixture_import


def _contains_sensitive_key(value) -> bool:
    sensitive_tokens = ("authorization", "api-key", "api_key", "apikey", "access_key", "token", "secret", "password", "cookie")
    if isinstance(value, dict):
        for key, nested in value.items():
            if any(token in str(key).casefold() for token in sensitive_tokens):
                return True
            if _contains_sensitive_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_sensitive_key(item) for item in value)
    return False


class PostgresHistoryStore:
    def __init__(self, connection_factory: Callable[[], object], *, allow_writes: bool = False, expected_database: str | None = None):
        self._connect = connection_factory
        self._allow_writes = allow_writes
        self._expected_database = expected_database
        if allow_writes and not expected_database:
            raise ValueError("EXPECTED_HISTORY_WRITE_DATABASE_REQUIRED")
        if allow_writes and expected_database in {"veltrix-football", "veltrix_football"}:
            raise RuntimeError("PRODUCTION_DATABASE_WRITES_DISABLED")

    def _connect_for_write(self):
        if not self._allow_writes:
            raise RuntimeError("HISTORY_DATABASE_WRITES_DISABLED")
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT current_database()")
            row = cur.fetchone()
            actual_database = row[0] if row else None
            if actual_database != self._expected_database:
                raise RuntimeError("HISTORY_WRITE_DATABASE_TARGET_MISMATCH")
            return conn
        except Exception:
            conn.close()
            raise

    def persist_source_approval(self, approval: SourceApproval) -> str:
        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO source_approvals (
                    approval_id, provider, source_id, competition_scope, data_type,
                    status, rights_basis, terms_url, terms_version, evidence_uri,
                    evidence_sha256, reviewed_at, reviewer_id, valid_from, valid_until,
                    permitted_uses, commercial_use_allowed, attribution_required,
                    attribution_text, attribution_url, raw_redistribution_allowed
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s::jsonb,%s,%s,%s,%s,%s
                ) ON CONFLICT (approval_id) DO NOTHING""",
                (
                    approval.approval_id, approval.provider, approval.source_id,
                    approval.competition_scope, approval.data_type, approval.status.value,
                    approval.rights_basis, approval.terms_url, approval.terms_version,
                    approval.evidence_uri, approval.evidence_sha256, approval.reviewed_at_utc,
                    approval.reviewer_id, approval.valid_from_utc, approval.valid_until_utc,
                    json.dumps(sorted(item.value for item in approval.permitted_uses)),
                    approval.commercial_use_allowed, approval.attribution_required,
                    approval.attribution_text, approval.attribution_url,
                    approval.raw_redistribution_allowed,
                ),
            )
            cur.execute(
                """SELECT provider,source_id,competition_scope,data_type,status,
                    rights_basis,terms_url,terms_version,evidence_uri,evidence_sha256,
                    reviewed_at,reviewer_id,valid_from,valid_until,permitted_uses,
                    commercial_use_allowed,attribution_required,attribution_text,
                    attribution_url,raw_redistribution_allowed
                   FROM source_approvals WHERE approval_id=%s""",
                (approval.approval_id,),
            )
            row = cur.fetchone()
            expected = (
                approval.provider, approval.source_id, approval.competition_scope,
                approval.data_type, approval.status.value, approval.rights_basis,
                approval.terms_url, approval.terms_version, approval.evidence_uri,
                approval.evidence_sha256, approval.reviewed_at_utc, approval.reviewer_id,
                approval.valid_from_utc, approval.valid_until_utc,
                sorted(item.value for item in approval.permitted_uses),
                approval.commercial_use_allowed, approval.attribution_required,
                approval.attribution_text, approval.attribution_url,
                approval.raw_redistribution_allowed,
            )
            stored = (
                tuple(row[:14]) + (sorted(row[14] or []),) + tuple(row[15:])
                if row else None
            )
            if stored != expected:
                raise ValueError("SOURCE_APPROVAL_IDEMPOTENCY_CONFLICT")
            conn.commit()
            return approval.approval_id
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def start_import_run(
        self, *, provider: str, import_type: str, boundary_start: datetime,
        boundary_end: datetime, request_budget: int, importer_version: str,
        rights_approval_id: str, started_at_utc: datetime,
    ) -> int:
        if any(value.tzinfo is None or value.utcoffset() is None
               for value in (boundary_start, boundary_end, started_at_utc)):
            raise ValueError("IMPORT_RUN_TIMESTAMPS_MUST_BE_TIMEZONE_AWARE")
        if boundary_end <= boundary_start or request_budget < 1:
            raise ValueError("IMPORT_RUN_BOUNDARY_OR_BUDGET_INVALID")
        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO import_runs(
                    provider,import_type,boundary_start,boundary_end,status,started_at,
                    importer_version,request_budget,rights_approval_id
                ) VALUES (%s,%s,%s,%s,'RUNNING',%s,%s,%s,%s) RETURNING id""",
                (provider, import_type, boundary_start, boundary_end, started_at_utc,
                 importer_version, request_budget, rights_approval_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("IMPORT_RUN_INSERT_FAILED")
            conn.commit()
            return int(row[0])
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def upsert_checkpoint(
        self, *, import_run_id: int, window_start: datetime, window_end: datetime,
        cursor_value: str | None, status: str, records_seen: int,
        records_inserted: int, records_rejected: int, records_quarantined: int,
        requests_used: int, response_sha256: str | None, last_error_code: str | None = None,
    ) -> None:
        if status not in {"PENDING", "RUNNING", "COMPLETED", "FAILED"}:
            raise ValueError("IMPORT_CHECKPOINT_STATUS_INVALID")
        if min(records_seen, records_inserted, records_rejected, records_quarantined, requests_used) < 0:
            raise ValueError("IMPORT_CHECKPOINT_COUNTS_INVALID")
        if window_start.tzinfo is None or window_start.utcoffset() is None or window_end.tzinfo is None or window_end.utcoffset() is None or window_end <= window_start:
            raise ValueError("IMPORT_CHECKPOINT_WINDOW_INVALID")
        if status == "COMPLETED" and records_seen != records_inserted + records_rejected + records_quarantined:
            raise ValueError("COMPLETED_CHECKPOINT_HAS_UNACCOUNTED_RECORDS")
        if response_sha256 is not None and (
            len(response_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in response_sha256.casefold())
        ):
            raise ValueError("IMPORT_CHECKPOINT_RESPONSE_HASH_INVALID")
        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            cur.execute("SELECT request_budget FROM import_runs WHERE id=%s", (import_run_id,))
            run_row = cur.fetchone()
            if not run_row or requests_used > int(run_row[0]):
                raise ValueError("IMPORT_CHECKPOINT_REQUEST_BUDGET_EXCEEDED")
            cur.execute(
                """INSERT INTO import_checkpoints(
                    import_run_id,window_start,window_end,cursor_value,status,records_seen,
                    records_inserted,updated_at,records_rejected,records_quarantined,
                    requests_used,response_sha256,last_error_code
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s,%s,%s)
                ON CONFLICT(import_run_id,window_start,window_end) DO UPDATE SET
                    cursor_value=EXCLUDED.cursor_value,status=EXCLUDED.status,
                    records_seen=EXCLUDED.records_seen,records_inserted=EXCLUDED.records_inserted,
                    updated_at=NOW(),records_rejected=EXCLUDED.records_rejected,
                    records_quarantined=EXCLUDED.records_quarantined,
                    requests_used=EXCLUDED.requests_used,response_sha256=EXCLUDED.response_sha256,
                    last_error_code=EXCLUDED.last_error_code
                WHERE import_checkpoints.status NOT IN ('COMPLETED','FAILED')
                  AND (import_checkpoints.status <> 'RUNNING' OR EXCLUDED.status <> 'PENDING')
                  AND EXCLUDED.records_seen >= import_checkpoints.records_seen
                  AND EXCLUDED.records_inserted >= import_checkpoints.records_inserted
                  AND EXCLUDED.records_rejected >= import_checkpoints.records_rejected
                  AND EXCLUDED.records_quarantined >= import_checkpoints.records_quarantined
                  AND EXCLUDED.requests_used >= import_checkpoints.requests_used""",
                (import_run_id, window_start, window_end, cursor_value, status,
                 records_seen, records_inserted, records_rejected, records_quarantined,
                 requests_used, response_sha256, last_error_code),
            )
            if cur.rowcount != 1:
                raise ValueError("IMPORT_CHECKPOINT_TERMINAL_OR_REGRESSION")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def finish_import_run(
        self, *, import_run_id: int, status: str, finished_at_utc: datetime,
        requests_used: int, records_seen: int, records_inserted: int,
        records_rejected: int, records_quarantined: int,
        manifest_sha256: str | None, reason_code: str | None = None,
    ) -> None:
        if status not in {"COMPLETED", "FAILED", "PAUSED"}:
            raise ValueError("IMPORT_RUN_TERMINAL_STATUS_INVALID")
        if finished_at_utc.tzinfo is None or finished_at_utc.utcoffset() is None:
            raise ValueError("IMPORT_RUN_FINISH_TIME_MUST_BE_TIMEZONE_AWARE")
        if min(requests_used, records_seen, records_inserted, records_rejected, records_quarantined) < 0:
            raise ValueError("IMPORT_RUN_COUNTS_INVALID")
        terminal_count = records_inserted + records_rejected + records_quarantined
        if status == "COMPLETED" and terminal_count != records_seen:
            raise ValueError("COMPLETED_IMPORT_RUN_HAS_UNACCOUNTED_RECORDS")
        if manifest_sha256 is not None and (
            len(manifest_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in manifest_sha256.casefold())
        ):
            raise ValueError("IMPORT_RUN_MANIFEST_HASH_INVALID")
        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            cur.execute(
                """UPDATE import_runs SET status=%s,finished_at=%s,requests_used=%s,
                    records_seen=%s,records_inserted=%s,records_rejected=%s,
                    records_quarantined=%s,manifest_sha256=%s,reason_code=%s
                   WHERE id=%s AND status='RUNNING' AND request_budget >= %s""",
                (status, finished_at_utc, requests_used, records_seen, records_inserted,
                 records_rejected, records_quarantined, manifest_sha256, reason_code,
                 import_run_id, requests_used),
            )
            if cur.rowcount != 1:
                raise ValueError("IMPORT_RUN_NOT_RUNNING_OR_NOT_FOUND")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def advance_sync_watermark(
        self, *, provider: str, data_class: str, scope: str,
        cursor_value: str | None, expected_version: int, updated_at_utc: datetime,
    ) -> int:
        if expected_version < 0:
            raise ValueError("SYNC_WATERMARK_EXPECTED_VERSION_INVALID")
        if updated_at_utc.tzinfo is None or updated_at_utc.utcoffset() is None:
            raise ValueError("SYNC_WATERMARK_TIME_MUST_BE_TIMEZONE_AWARE")
        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO sync_watermarks(provider,data_class,scope,cursor_value,version,updated_at)
                   VALUES (%s,%s,%s,NULL,0,%s)
                   ON CONFLICT(provider,data_class,scope) DO NOTHING""",
                (provider, data_class, scope, updated_at_utc),
            )
            cur.execute(
                """SELECT version FROM sync_watermarks
                   WHERE provider=%s AND data_class=%s AND scope=%s FOR UPDATE""",
                (provider, data_class, scope),
            )
            row = cur.fetchone()
            if not row or int(row[0]) != expected_version:
                raise ValueError("SYNC_WATERMARK_VERSION_CONFLICT")
            cur.execute(
                """UPDATE sync_watermarks SET cursor_value=%s,version=version+1,updated_at=%s
                   WHERE provider=%s AND data_class=%s AND scope=%s
                   RETURNING version""",
                (cursor_value, updated_at_utc, provider, data_class, scope),
            )
            updated = cur.fetchone()
            if not updated:
                raise ValueError("SYNC_WATERMARK_ADVANCE_FAILED")
            conn.commit()
            return int(updated[0])
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_sync_watermark(self, *, provider: str, data_class: str, scope: str):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT cursor_value,version,updated_at FROM sync_watermarks
                   WHERE provider=%s AND data_class=%s AND scope=%s""",
                (provider, data_class, scope),
            )
            return cur.fetchone()
        finally:
            conn.close()

    def record_entitlement_observation(
        self, *, provider: str, source_id: str, plan_code: str,
        entitlement_status: str, country_pack_code: str | None,
        competition_ids: list[str], rate_limit_hour: int | None,
        rate_limit_minute: int | None, quota_remaining: int | None,
        provider_response_id: int | None, evidence_sha256: str,
        checked_at_utc: datetime,
    ) -> int:
        if checked_at_utc.tzinfo is None or checked_at_utc.utcoffset() is None:
            raise ValueError("ENTITLEMENT_CHECK_TIME_MUST_BE_TIMEZONE_AWARE")
        if len(evidence_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in evidence_sha256.casefold()):
            raise ValueError("ENTITLEMENT_EVIDENCE_HASH_INVALID")
        if not provider.strip() or not source_id.strip() or not plan_code.strip() or not entitlement_status.strip():
            raise ValueError("ENTITLEMENT_IDENTITY_REQUIRED")
        if len(set(competition_ids)) != len(competition_ids):
            raise ValueError("ENTITLEMENT_COMPETITION_IDS_DUPLICATED")
        conn = self._connect_for_write()
        try:
            cur = conn.cursor()
            if provider_response_id is None:
                raise ValueError("ENTITLEMENT_PROVIDER_RESPONSE_REQUIRED")
            cur.execute(
                """SELECT provider,source_id,http_status,fetched_at
                   FROM provider_responses WHERE id=%s""",
                (provider_response_id,),
            )
            response_row = cur.fetchone()
            if (
                not response_row
                or tuple(response_row[:3]) != (provider, source_id, 200)
                or response_row[3] > checked_at_utc
            ):
                raise ValueError("ENTITLEMENT_RESPONSE_PROVENANCE_MISMATCH")
            if any(not isinstance(item, str) or not item.strip() for item in competition_ids):
                raise ValueError("ENTITLEMENT_COMPETITION_IDS_INVALID")
            cur.execute(
                """INSERT INTO provider_entitlement_observations(
                    provider,source_id,plan_code,entitlement_status,country_pack_code,
                    competition_ids,rate_limit_hour,rate_limit_minute,quota_remaining,
                    provider_response_id,evidence_sha256,checked_at
                ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(provider,source_id,checked_at,evidence_sha256) DO NOTHING
                RETURNING id""",
                (provider, source_id, plan_code, entitlement_status, country_pack_code,
                 json.dumps(sorted(competition_ids)), rate_limit_hour, rate_limit_minute,
                 quota_remaining, provider_response_id, evidence_sha256, checked_at_utc),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """SELECT id FROM provider_entitlement_observations
                       WHERE provider=%s AND source_id=%s AND checked_at=%s AND evidence_sha256=%s""",
                    (provider, source_id, checked_at_utc, evidence_sha256),
                )
                row = cur.fetchone()
            if not row:
                raise ValueError("ENTITLEMENT_OBSERVATION_INSERT_FAILED")
            conn.commit()
            return int(row[0])
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _persist_provider_response(self, cur, response: ProviderResponse) -> int:
        sensitive = {"authorization", "x-api-key", "api-key", "cookie", "set-cookie"}
        if any(str(key).casefold() in sensitive for key in response.response_headers):
            raise ValueError("PROVIDER_RESPONSE_SECRET_HEADER_MUST_NOT_BE_STORED")
        params = dict(response.request_params)
        if any(any(token in str(key).casefold() for token in ("key", "token", "secret", "password")) for key in params):
            raise ValueError("PROVIDER_REQUEST_SECRET_PARAMETER_MUST_NOT_BE_STORED")
        cur.execute(
            """INSERT INTO provider_responses (
                provider,source_id,endpoint,request_id,request_params,http_status,
                response_sha256,raw_body,response_headers,quota_limit,quota_remaining,
                quota_reset_at,fetched_at
            ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)
            ON CONFLICT (provider,source_id,request_id,response_sha256) DO NOTHING""",
            (
                response.provider, response.source_id, response.endpoint, response.request_id,
                json.dumps(params, sort_keys=True), response.http_status,
                response.response_sha256, response.raw_body,
                json.dumps(dict(response.response_headers), sort_keys=True),
                _header_int(response.response_headers, "X-RateLimit-Limit"),
                _header_int(response.response_headers, "X-RateLimit-Remaining"),
                _header_datetime(response.response_headers, "X-RateLimit-Reset"),
                response.fetched_at_utc.astimezone(timezone.utc),
            ),
        )
        cur.execute(
            """SELECT id,raw_body,http_status FROM provider_responses
               WHERE provider=%s AND source_id=%s AND request_id=%s AND response_sha256=%s""",
            (response.provider, response.source_id, response.request_id, response.response_sha256),
        )
        stored = cur.fetchone()
        if not stored or bytes(stored[1]) != response.raw_body or stored[2] != response.http_status:
            raise ValueError("PROVIDER_RESPONSE_IDEMPOTENCY_CONFLICT")
        return int(stored[0])

    def persist_page(
        self,
        response: ProviderResponse,
        fixtures: Iterable[HistoricalFixture],
        approval: SourceApproval,
        *,
        import_run_id: int | None = None,
    ) -> dict:
        """Persist one page atomically; caller must use an isolated staging database."""
        rows = tuple(fixtures)
        if approval.provider != response.provider or approval.source_id != response.source_id:
            raise ValueError("SOURCE_APPROVAL_PROVIDER_MISMATCH")
        if _contains_sensitive_key(dict(response.response_headers)):
            raise ValueError("PROVIDER_RESPONSE_SECRET_HEADER_MUST_NOT_BE_STORED")
        if _contains_sensitive_key(dict(response.request_params)):
            raise ValueError("PROVIDER_REQUEST_SECRET_PARAMETER_MUST_NOT_BE_STORED")
        # Rights evidence is immutable and must exist before any source record can reference it.
        self.persist_source_approval(approval)
        conn = self._connect_for_write()
        inserted_observations = inserted_fixtures = refreshed_fixtures = inserted_results = inserted_versions = conflicts = 0
        try:
            cur = conn.cursor()
            response_id = self._persist_provider_response(cur, response)
            cur.execute(
                """SELECT e.entitlement_status,e.competition_ids
                   FROM provider_entitlement_observations e
                   JOIN provider_responses r ON r.id=e.provider_response_id
                   WHERE e.provider=%s AND e.source_id=%s AND e.checked_at<=%s
                     AND r.provider=e.provider AND r.source_id=e.source_id
                     AND r.http_status=200 AND r.fetched_at<=e.checked_at
                   ORDER BY e.checked_at DESC,e.id DESC LIMIT 1""",
                (response.provider, response.source_id, response.fetched_at_utc),
            )
            entitlement = cur.fetchone()
            entitlement_active = bool(entitlement and str(entitlement[0]).upper() == "ACTIVE")
            entitled_competitions = set(map(str, entitlement[1] or [])) if entitlement_active else set()
            for fixture in rows:
                if fixture.provider != response.provider or fixture.source_id != response.source_id:
                    raise ValueError("FIXTURE_PROVIDER_RESPONSE_MISMATCH")
                if not entitlement_active:
                    self._quarantine(
                        cur, fixture, import_run_id, "PROVIDER_ENTITLEMENT_NOT_VERIFIED",
                        {"provider": response.provider, "source_id": response.source_id},
                    )
                    conflicts += 1
                    continue
                if fixture.provider_competition_id not in entitled_competitions:
                    self._quarantine(
                        cur, fixture, import_run_id, "PROVIDER_COMPETITION_NOT_ENTITLED",
                        {"competition_id": fixture.provider_competition_id,
                         "entitled_competitions": sorted(entitled_competitions)},
                    )
                    conflicts += 1
                    continue
                decision = evaluate_fixture_import(
                    fixture, approval, evaluated_at_utc=response.fetched_at_utc
                )
                if decision.status.value != "IMPORTABLE":
                    self._quarantine(
                        cur, fixture, import_run_id,
                        decision.reason_code, {"decision": decision.status.value},
                    )
                    conflicts += 1
                    continue
                cur.execute(
                    """INSERT INTO source_observations (
                        provider,endpoint,entity_type,provider_entity_id,payload_sha256,
                        retrieved_at,payload,source_id,data_type,season_key,source_event_time,
                        available_at,availability_basis,rights_approval_id,schema_version,
                        provider_response_id,point_in_time_certifiable
                    ) VALUES (%s,%s,'fixture',%s,%s,%s,%s::jsonb,%s,'fixture_result',%s,%s,
                              %s,%s,%s,'1',%s,FALSE)
                    ON CONFLICT (provider,endpoint,entity_type,provider_entity_id,payload_sha256)
                    DO NOTHING""",
                    (
                        fixture.provider, response.endpoint, fixture.provider_fixture_id,
                        fixture.payload_sha256, fixture.retrieved_at_utc,
                        json.dumps(dict(fixture.payload), sort_keys=True),
                        fixture.source_id, fixture.season_key, fixture.source_event_time_utc,
                        fixture.available_at_utc, fixture.availability_basis,
                        fixture.rights_approval_id, response_id,
                    ),
                )
                observation_inserted = cur.rowcount == 1
                cur.execute(
                    """SELECT id,payload_sha256,rights_approval_id,provider_response_id
                       FROM source_observations
                       WHERE provider=%s AND endpoint=%s AND entity_type='fixture'
                         AND provider_entity_id=%s AND payload_sha256=%s""",
                    (
                        fixture.provider, response.endpoint, fixture.provider_fixture_id,
                        fixture.payload_sha256,
                    ),
                )
                observation = cur.fetchone()
                if not observation or observation[1].strip() != fixture.payload_sha256:
                    raise ValueError("SOURCE_OBSERVATION_IDEMPOTENCY_CONFLICT")
                if observation[2] != fixture.rights_approval_id:
                    raise ValueError("SOURCE_OBSERVATION_RIGHTS_APPROVAL_CONFLICT")
                observation_id = int(observation[0])
                if observation_inserted:
                    inserted_observations += 1

                cur.execute(
                    """INSERT INTO competitions(provider,provider_competition_id,name,season,observed_at)
                       VALUES (%s,%s,%s,NULL,%s)
                       ON CONFLICT(provider,provider_competition_id) DO NOTHING""",
                    (fixture.provider, fixture.provider_competition_id,
                     fixture.competition_name, fixture.retrieved_at_utc),
                )
                cur.execute(
                    "SELECT id FROM competitions WHERE provider=%s AND provider_competition_id=%s",
                    (fixture.provider, fixture.provider_competition_id),
                )
                competition = cur.fetchone()
                if not competition:
                    raise ValueError("COMPETITION_PERSISTENCE_FAILED")
                competition_id = int(competition[0])

                team_ids = []
                for provider_team_id, team_name in (
                    (fixture.provider_home_team_id, fixture.home_team_name),
                    (fixture.provider_away_team_id, fixture.away_team_name),
                ):
                    cur.execute(
                        """INSERT INTO teams(provider,provider_team_id,name,observed_at)
                           VALUES (%s,%s,%s,%s)
                           ON CONFLICT(provider,provider_team_id) DO NOTHING""",
                        (fixture.provider, provider_team_id, team_name, fixture.retrieved_at_utc),
                    )
                    cur.execute(
                        "SELECT id FROM teams WHERE provider=%s AND provider_team_id=%s",
                        (fixture.provider, provider_team_id),
                    )
                    team = cur.fetchone()
                    if not team:
                        raise ValueError("TEAM_PERSISTENCE_FAILED")
                    team_ids.append(int(team[0]))

                status = fixture.status.value
                cur.execute(
                    """INSERT INTO fixtures(
                        provider,provider_fixture_id,competition_id,home_team_id,away_team_id,
                        kickoff_at,status,source_payload_sha256,retrieved_at,season_key,source_observation_id
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(provider,provider_fixture_id) DO NOTHING""",
                    (
                        fixture.provider, fixture.provider_fixture_id, competition_id,
                        team_ids[0], team_ids[1], fixture.kickoff_at_utc, status,
                        fixture.payload_sha256, fixture.retrieved_at_utc,
                        fixture.season_key, observation_id,
                    ),
                )
                fixture_inserted = cur.rowcount == 1
                cur.execute(
                    """SELECT id,competition_id,home_team_id,away_team_id,kickoff_at
                       FROM fixtures WHERE provider=%s AND provider_fixture_id=%s""",
                    (fixture.provider, fixture.provider_fixture_id),
                )
                stored_fixture = cur.fetchone()
                expected_identity = (
                    competition_id, team_ids[0], team_ids[1], fixture.kickoff_at_utc
                )
                if not stored_fixture or tuple(stored_fixture[1:]) != expected_identity:
                    self._quarantine(
                        cur, fixture, import_run_id, "FIXTURE_PROVIDER_IDENTITY_CONFLICT",
                        {"stored_identity": list(stored_fixture[1:]) if stored_fixture else None,
                         "expected_identity": list(expected_identity)},
                    )
                    conflicts += 1
                    continue
                fixture_db_id = int(stored_fixture[0])
                cur.execute(
                    """UPDATE fixtures SET status=%s,source_payload_sha256=%s,retrieved_at=%s,
                       season_key=COALESCE(%s,season_key),source_observation_id=%s
                       WHERE id=%s AND retrieved_at<=%s""",
                    (
                        status, fixture.payload_sha256, fixture.retrieved_at_utc,
                        fixture.season_key, observation_id, fixture_db_id,
                        fixture.retrieved_at_utc,
                    ),
                )
                if fixture_inserted:
                    inserted_fixtures += 1
                elif cur.rowcount:
                    refreshed_fixtures += 1

                cur.execute(
                    """INSERT INTO fixture_result_versions(
                        fixture_id,source_observation_id,home_score,away_score,available_at,
                        availability_basis,rights_approval_id
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(source_observation_id) DO NOTHING""",
                    (
                        fixture_db_id, observation_id, fixture.home_score, fixture.away_score,
                        fixture.available_at_utc, fixture.availability_basis,
                        fixture.rights_approval_id,
                    ),
                )
                if cur.rowcount:
                    inserted_versions += 1
                cur.execute(
                    "SELECT home_score,away_score,fixture_id FROM fixture_result_versions WHERE source_observation_id=%s",
                    (observation_id,),
                )
                version = cur.fetchone()
                if not version or tuple(version) != (
                    fixture.home_score, fixture.away_score, fixture_db_id
                ):
                    raise ValueError("FIXTURE_RESULT_VERSION_IDEMPOTENCY_CONFLICT")

                cur.execute(
                    "SELECT home_score,away_score FROM fixture_results WHERE fixture_id=%s",
                    (fixture_db_id,),
                )
                current_result = cur.fetchone()
                if current_result is None:
                    cur.execute(
                        """INSERT INTO fixture_results(
                            fixture_id,home_score,away_score,result_source,observed_at,
                            source_observation_id,available_at,availability_basis,rights_approval_id
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            fixture_db_id, fixture.home_score, fixture.away_score,
                            fixture.provider, fixture.retrieved_at_utc, observation_id,
                            fixture.available_at_utc, fixture.availability_basis,
                            fixture.rights_approval_id,
                        ),
                    )
                    inserted_results += 1
                elif tuple(current_result) != (fixture.home_score, fixture.away_score):
                    self._quarantine(
                        cur, fixture, import_run_id, "SETTLED_RESULT_CONFLICT",
                        {"stored_score": list(current_result),
                         "observed_score": [fixture.home_score, fixture.away_score]},
                        source_observation_id=observation_id,
                    )
                    conflicts += 1
            conn.commit()
            return {
                "provider_response_id": response_id,
                "source_observations": inserted_observations,
                "fixtures_inserted": inserted_fixtures,
                "fixtures_refreshed": refreshed_fixtures,
                "result_versions_inserted": inserted_versions,
                "results_inserted": inserted_results,
                "quarantined_or_conflicting": conflicts,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _quarantine(cur, fixture, import_run_id, reason_code, details, source_observation_id=None):
        cur.execute(
            """INSERT INTO ingestion_quarantine(
                provider,source_id,provider_entity_id,source_observation_id,
                import_run_id,reason_code,details
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT DO NOTHING""",
            (
                fixture.provider, fixture.source_id, fixture.provider_fixture_id,
                source_observation_id, import_run_id, reason_code,
                json.dumps(details, sort_keys=True),
            ),
        )


def _header_int(headers, name):
    value = next((v for k, v in headers.items() if str(k).casefold() == name.casefold()), None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _header_datetime(headers, name):
    value = next((v for k, v in headers.items() if str(k).casefold() == name.casefold()), None)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
