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


class PostgresHistoryStore:
    def __init__(self, connection_factory: Callable[[], object]):
        self._connect = connection_factory

    def persist_source_approval(self, approval: SourceApproval) -> str:
        conn = self._connect()
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
                    evidence_sha256,terms_version,permitted_uses
                   FROM source_approvals WHERE approval_id=%s""",
                (approval.approval_id,),
            )
            row = cur.fetchone()
            expected = (
                approval.provider, approval.source_id, approval.competition_scope,
                approval.data_type, approval.status.value, approval.evidence_sha256,
                approval.terms_version,
                json.dumps(sorted(item.value for item in approval.permitted_uses)),
            )
            if not row or row[0:7] != expected[0:7] or json.dumps(row[7], sort_keys=True) != expected[7]:
                raise ValueError("SOURCE_APPROVAL_IDEMPOTENCY_CONFLICT")
            conn.commit()
            return approval.approval_id
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
        # Rights evidence is immutable and must exist before any source record can reference it.
        self.persist_source_approval(approval)
        conn = self._connect()
        inserted_observations = inserted_fixtures = refreshed_fixtures = inserted_results = inserted_versions = conflicts = 0
        try:
            cur = conn.cursor()
            response_id = self._persist_provider_response(cur, response)
            for fixture in rows:
                if fixture.provider != response.provider or fixture.source_id != response.source_id:
                    raise ValueError("FIXTURE_PROVIDER_RESPONSE_MISMATCH")
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
                if cur.rowcount:
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
