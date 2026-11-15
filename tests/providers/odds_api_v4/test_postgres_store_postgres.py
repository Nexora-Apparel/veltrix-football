"""Real PostgreSQL integration tests for the immutable odds quote writer.

Each test gets a disposable database or isolated schema populated by the
complete migration chain. Neon schema mode never writes to the public schema.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg import sql
import pytest

from scripts.db_migrate import migrate
from veltrix_v2.providers.odds_api_v4.parser import parse_bulk_odds
from veltrix_v2.providers.odds_api_v4.postgres_store import (
    PostgresOddsQuoteStore,
    QuoteWriteContext,
)


UTC = timezone.utc
BASE_DSN = os.environ["DATABASE_URL"]
NOW = datetime.now(UTC).replace(microsecond=0)
RETRIEVED = NOW - timedelta(minutes=2)
PUBLISHED = NOW - timedelta(minutes=3)
CUTOFF = NOW + timedelta(hours=1)
KICKOFF = NOW + timedelta(hours=2)
RAW = json.dumps([{
    "id": "odds-event-1",
    "bookmakers": [{
        "key": "book-a",
        "title": "Book A",
        "markets": [{
            "key": "h2h",
            "last_update": PUBLISHED.isoformat(),
            "outcomes": [
                {"name": "Home", "price": 2.1},
                {"name": "Away", "price": 3.4},
            ],
        }],
    }],
}], separators=(",", ":")).encode()


def _database_urls():
    parsed = urlsplit(BASE_DSN)
    name = f"veltrix_odds_writer_{uuid.uuid4().hex[:12]}"
    if os.environ.get("VELTRIX_TEST_SCHEMA_MODE") == "1":
        # Neon branch roles cannot CREATE DATABASE; isolate each test in a schema.
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query = [(key, value) for key, value in query if key != "options"]
        query.append(("options", f"-c search_path={name}"))
        target = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
        return "schema", name, target
    admin = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", "", ""))
    target = urlunsplit((parsed.scheme, parsed.netloc, f"/{name}", "", ""))
    return admin, name, target


@pytest.fixture
def postgres_db(monkeypatch):
    admin_dsn, database_name, target_dsn = _database_urls()
    if admin_dsn == "schema":
        with psycopg.connect(BASE_DSN) as admin:
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(database_name)))
        try:
            actual_database = urlsplit(BASE_DSN).path.lstrip("/")
            monkeypatch.setenv("VELTRIX_EXPECTED_DATABASE", actual_database)
            migrated = migrate(target_dsn, dry_run=False)
            assert migrated["applied_now"] == migrated["manifest_count"]
            repeated = migrate(target_dsn, dry_run=False)
            assert repeated["applied_now"] == 0
            assert repeated["manifest_count"] == migrated["manifest_count"]
            yield target_dsn
        finally:
            with psycopg.connect(BASE_DSN) as admin:
                admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(database_name)))
        return
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{database_name}"')
    try:
        monkeypatch.setenv("VELTRIX_EXPECTED_DATABASE", database_name)
        migrated = migrate(target_dsn, dry_run=False)
        assert migrated["applied_now"] == migrated["manifest_count"]
        repeated = migrate(target_dsn, dry_run=False)
        assert repeated["applied_now"] == 0
        yield target_dsn
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s", (database_name,))
            admin.execute(f'DROP DATABASE IF EXISTS "{database_name}"')


def seed_evidence(dsn: str, *, competition_scope="soccer_epl",
                  mapping_fixture_id: int | None = None,
                  status="APPROVED", persisted_response_hash: str | None = None):
    """Create a fully linked fixture, response, capture request, crosswalk and rights row."""
    digest = hashlib.sha256(RAW).hexdigest()
    with psycopg.connect(dsn) as conn:
        country_id = "GB"
        conn.execute(
            """INSERT INTO countries(country_code,country_name,source_provider,observed_at)
               VALUES (%s,'United Kingdom','fixture-test',%s)""",
            (country_id, RETRIEVED),
        )
        competition_id = conn.execute(
            """INSERT INTO competitions(provider,provider_competition_id,country_code,name,observed_at)
               VALUES ('fixture-test','epl','GB','Premier League',%s) RETURNING id""",
            (RETRIEVED,),
        ).fetchone()[0]
        home_id = conn.execute(
            """INSERT INTO teams(provider,provider_team_id,name,observed_at)
               VALUES ('fixture-test','home','Home FC',%s) RETURNING id""",
            (RETRIEVED,),
        ).fetchone()[0]
        away_id = conn.execute(
            """INSERT INTO teams(provider,provider_team_id,name,observed_at)
               VALUES ('fixture-test','away','Away FC',%s) RETURNING id""",
            (RETRIEVED,),
        ).fetchone()[0]
        fixture_id = conn.execute(
            """INSERT INTO fixtures(
                   provider,provider_fixture_id,competition_id,home_team_id,away_team_id,
                   kickoff_at,status,source_payload_sha256,retrieved_at
               ) VALUES ('fixture-test','fixture-1',%s,%s,%s,%s,'SCHEDULED',%s,%s)
               RETURNING id""",
            (competition_id, home_id, away_id, KICKOFF, "b" * 64, RETRIEVED),
        ).fetchone()[0]
        mapped_id = mapping_fixture_id if mapping_fixture_id is not None else fixture_id
        if mapped_id != fixture_id:
            other_fixture_id = conn.execute(
                """INSERT INTO fixtures(
                       provider,provider_fixture_id,competition_id,home_team_id,away_team_id,
                       kickoff_at,status,source_payload_sha256,retrieved_at
                   ) VALUES ('fixture-test','fixture-2',%s,%s,%s,%s,'SCHEDULED',%s,%s)
                   RETURNING id""",
                (competition_id, home_id, away_id, KICKOFF + timedelta(days=1),
                 "c" * 64, RETRIEVED),
            ).fetchone()[0]
            mapped_id = other_fixture_id

        conn.execute(
            """INSERT INTO source_approvals(
                   approval_id,provider,source_id,competition_scope,data_type,status,
                   rights_basis,terms_url,terms_version,evidence_uri,evidence_sha256,
                   reviewed_at,reviewer_id,valid_from,valid_until,permitted_uses,
                   commercial_use_allowed
               ) VALUES (
                   'odds-rights-1','the_odds_api','odds_api_v4',%s,'odds_quote','APPROVED',
                   'TERMS','https://example.invalid/terms','terms-v1',
                   'https://example.invalid/evidence',%s,%s,'test-reviewer',
                   %s,%s,'["COLLECTION","STORAGE"]'::jsonb,TRUE
               )""",
            (competition_scope, "d" * 64, RETRIEVED - timedelta(days=1),
             RETRIEVED - timedelta(days=2), RETRIEVED + timedelta(days=2)),
        )
        evidence_observation_id = conn.execute(
            """INSERT INTO source_observations(
                   provider,source_id,data_type,endpoint,entity_type,provider_entity_id,
                   payload_sha256,retrieved_at,payload
               ) VALUES (
                   'the_odds_api','odds_api_v4','odds_quote','/v4/sports',
                   'FIXTURE','odds-event-1',%s,%s,'{}'::jsonb
               ) RETURNING id""",
            ("e" * 64, RETRIEVED),
        ).fetchone()[0]
        crosswalk_id = conn.execute(
            """INSERT INTO entity_crosswalk_versions(
                   entity_type,provider,source_id,provider_entity_id,canonical_entity_key,
                   mapping_version,mapping_status,mapping_method,valid_from,
                   evidence_observation_id,decision_reason
               ) VALUES (
                   'FIXTURE','the_odds_api','odds_api_v4','odds-event-1',%s,
                   1,'RESOLVED','EXACT_PROVIDER_ID',%s,%s,'exact provider event mapping'
               ) RETURNING crosswalk_version_id""",
            (str(mapped_id), RETRIEVED - timedelta(days=1), evidence_observation_id),
        ).fetchone()[0]
        manifest_id = conn.execute(
            """INSERT INTO capture_manifests(
                   manifest_key,manifest_sha256,capture_scope,requests_planned
               ) VALUES ('odds-writer-test',%s,'{}'::jsonb,1)
               RETURNING capture_manifest_id""",
            ("f" * 64,),
        ).fetchone()[0]
        response_id = conn.execute(
            """INSERT INTO provider_responses(
                   provider,source_id,endpoint,request_id,request_params,http_status,
                   response_sha256,raw_body,response_headers,fetched_at
               ) VALUES (
                   'the_odds_api','odds_api_v4','/v4/sports/soccer_epl/odds',
                   'odds-request-1','{}'::jsonb,200,%s,%s,'{}'::jsonb,%s
               ) RETURNING id""",
            (persisted_response_hash or digest, RAW, RETRIEVED),
        ).fetchone()[0]
        request_id = conn.execute(
            """INSERT INTO provider_capture_requests(
                   capture_manifest_id,provider,source_id,endpoint,request_key,
                   request_fingerprint,attempt_number,requested_at,response_id,outcome
               ) VALUES (
                   %s,'the_odds_api','odds_api_v4','/v4/sports/soccer_epl/odds',
                   'odds-request-1',%s,1,%s,%s,'RESPONSE'
               ) RETURNING capture_request_id""",
            (manifest_id, "a" * 64, RETRIEVED, response_id),
        ).fetchone()[0]
        if status == "REVOKED":
            conn.execute(
                """INSERT INTO source_approval_status_events(
                       approval_id,status,evidence_uri,evidence_sha256,effective_at,reason_code
                   ) VALUES (
                       'odds-rights-1','REVOKED','https://example.invalid/revocation',
                       %s,%s,'RIGHTS_REVOKED'
                   )""",
                ("9" * 64, RETRIEVED - timedelta(seconds=1)),
            )
    return {
        "fixture_id": fixture_id,
        "crosswalk_version_id": crosswalk_id,
        "response_id": response_id,
        "capture_request_id": request_id,
    }


def parsed(raw=RAW):
    return parse_bulk_odds(raw, sport_key="soccer_epl", retrieved_at=RETRIEVED)


def write_context(seed, raw=RAW):
    return QuoteWriteContext(
        fixture_id=seed["fixture_id"],
        crosswalk_version_id=seed["crosswalk_version_id"],
        response_id=seed["response_id"],
        capture_request_id=seed["capture_request_id"],
        rights_approval_id="odds-rights-1",
        raw_response=raw,
        prediction_cutoff_at=CUTOFF,
        kickoff_at=KICKOFF,
    )


def store(dsn):
    return PostgresOddsQuoteStore(lambda: psycopg.connect(dsn))


def test_real_postgres_inserts_immutable_quote_rows(postgres_db):
    seed = seed_evidence(postgres_db)
    result = store(postgres_db).write_capture(parsed(), write_context(seed))
    assert (result.inserted, result.duplicates, result.rejected) == (2, 0, 0)
    with psycopg.connect(postgres_db) as conn:
        rows = conn.execute(
            """SELECT selection_key,decimal_price,response_sha256,rights_approval_id
               FROM odds_quote_observations ORDER BY selection_key"""
        ).fetchall()
        assert rows == [
            ("away", Decimal("3.400000"), hashlib.sha256(RAW).hexdigest(), "odds-rights-1"),
            ("home", Decimal("2.100000"), hashlib.sha256(RAW).hexdigest(), "odds-rights-1"),
        ]
        with pytest.raises(psycopg.Error, match="IMMUTABLE_HISTORY"):
            conn.execute("UPDATE odds_quote_observations SET decimal_price=2.2")
        conn.rollback()
        with pytest.raises(psycopg.Error, match="IMMUTABLE_HISTORY"):
            conn.execute("DELETE FROM odds_quote_observations")
        conn.rollback()


def test_real_postgres_duplicate_is_idempotent_and_never_overwrites(postgres_db):
    seed = seed_evidence(postgres_db)
    writer = store(postgres_db)
    first = writer.write_capture(parsed(), write_context(seed))
    second = writer.write_capture(parsed(), write_context(seed))
    assert (first.inserted, first.duplicates, first.rejected) == (2, 0, 0)
    assert (second.inserted, second.duplicates, second.rejected) == (0, 2, 0)
    with psycopg.connect(postgres_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM odds_quote_observations").fetchone()[0] == 2


def test_real_postgres_rejects_revoked_rights(postgres_db):
    seed = seed_evidence(postgres_db, status="REVOKED")
    result = store(postgres_db).write_capture(parsed(), write_context(seed))
    assert (result.inserted, result.duplicates, result.rejected) == (0, 0, 2)
    with psycopg.connect(postgres_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM odds_quote_observations").fetchone()[0] == 0


def test_real_postgres_rejects_competition_outside_rights_scope(postgres_db):
    seed = seed_evidence(postgres_db, competition_scope="soccer_spain_la_liga")
    result = store(postgres_db).write_capture(parsed(), write_context(seed))
    assert (result.inserted, result.duplicates, result.rejected) == (0, 0, 2)
    with psycopg.connect(postgres_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM odds_quote_observations").fetchone()[0] == 0


def test_real_postgres_rejects_invalid_fixture_crosswalk(postgres_db):
    seed = seed_evidence(postgres_db, mapping_fixture_id=999999)
    with pytest.raises(ValueError, match="FIXTURE_CROSSWALK_FIXTURE_ID_MISMATCH"):
        store(postgres_db).write_capture(parsed(), write_context(seed))
    with psycopg.connect(postgres_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM odds_quote_observations").fetchone()[0] == 0


def test_real_postgres_rejects_persisted_response_hash_mismatch(postgres_db):
    seed = seed_evidence(postgres_db, persisted_response_hash="0" * 64)
    with pytest.raises(ValueError, match="PERSISTED_RAW_RESPONSE_HASH_OR_BYTES_MISMATCH"):
        store(postgres_db).write_capture(parsed(), write_context(seed))
    with psycopg.connect(postgres_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM odds_quote_observations").fetchone()[0] == 0


def test_real_postgres_rejects_capture_atomically_when_one_quote_fails_admission(postgres_db):
    seed = seed_evidence(postgres_db)
    capture = parsed()
    invalid_second = replace(capture.observations[1], provider_event_id="unmapped-event")
    mixed_capture = replace(
        capture,
        observations=(capture.observations[0], invalid_second),
    )
    result = store(postgres_db).write_capture(mixed_capture, write_context(seed))
    assert (result.inserted, result.duplicates, result.rejected) == (0, 0, 1)
    with psycopg.connect(postgres_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM odds_quote_observations").fetchone()[0] == 0


def test_real_postgres_rolls_back_entire_capture_if_later_insert_fails(postgres_db):
    seed = seed_evidence(postgres_db)
    capture = parsed()
    invalid_second = replace(capture.observations[1], source_timestamp_raw="")
    broken_capture = replace(
        capture,
        observations=(capture.observations[0], invalid_second),
    )
    with pytest.raises(psycopg.Error):
        store(postgres_db).write_capture(broken_capture, write_context(seed))
    with psycopg.connect(postgres_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM odds_quote_observations").fetchone()[0] == 0
