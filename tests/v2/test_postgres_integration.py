from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlparse
import os
import pytest

psycopg=pytest.importorskip("psycopg")
DB_URL=os.getenv("V2_TEST_DATABASE_URL")
pytestmark=pytest.mark.skipif(not DB_URL,reason="V2_TEST_DATABASE_URL not configured")


def _validate_disposable_test_database(dsn: str) -> None:
    """Only allow destructive schema reset against the dedicated local CI database."""
    parsed = urlparse(dsn)
    host = (parsed.hostname or "").lower()
    database = unquote(parsed.path.lstrip("/").split("/", 1)[0])
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("V2_TEST_DATABASE_SCHEME_INVALID")
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("V2_TEST_DATABASE_HOST_MUST_BE_LOCAL")
    if database != "veltrix_v2_test":
        raise RuntimeError("V2_TEST_DATABASE_NAME_MUST_BE_DISPOSABLE")
    if parsed.port != 5432:
        raise RuntimeError("V2_TEST_DATABASE_PORT_MUST_BE_5432")


def test_destructive_test_database_guard_rejects_non_local_targets():
    valid = "postgresql://user:password@localhost:5432/veltrix_v2_test"
    _validate_disposable_test_database(valid)
    for unsafe in (
        "postgresql://user:password@db.neon.tech:5432/veltrix_v2_test",
        "postgresql://user:password@localhost:5432/veltrix_football_v2",
        "postgresql://user:password@localhost:5433/veltrix_v2_test",
        "https://localhost/veltrix_v2_test",
    ):
        with pytest.raises(RuntimeError):
            _validate_disposable_test_database(unsafe)

from veltrix_v2.domain.contracts import DataUsePurpose, RightsDecision, RightsStatus, SourceRights
from veltrix_v2.domain.identity import ReconciliationDecision, ReconciliationStatus, SquadCategory, reconcile_provider_fixture
from veltrix_v2.history.contracts import TeamHistoryQuery, SyncWatermark
from veltrix_v2.history.importer import build_training_history_match
from veltrix_v2.history.postgres import PostgresHistoryStore
from veltrix_v2.identity.postgres_fixtures import PostgresFixtureDecisionRepository
from veltrix_v2.identity.postgres_registry import PostgresIdentityMappingRepository
from veltrix_v2.identity.registry import (
    MappingResolutionStatus, MappingVerificationState, ProviderCompetitionMapping,
    ProviderFixtureSourceIdentity, ProviderTeamMapping, resolve_provider_fixture,
)
from veltrix_v2.ingestion.acceptance import AcceptedSourceRecord, ProviderSourceRecord
from veltrix_v2.ingestion.postgres_records import PostgresProviderRecordRepository
from veltrix_v2.ingestion.providers.five_dollar_fixture import FiveDollarFixtureRecord, FiveDollarFixtureStatus

NOW=datetime(2026,11,8,9,tzinfo=timezone.utc)
KICKOFF=NOW-timedelta(days=2)


@pytest.fixture
def connect():
    _validate_disposable_test_database(DB_URL)
    with psycopg.connect(DB_URL) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute((Path(__file__).resolve().parents[2]/"migrations/v2/001_historical_store.sql").read_text())
    return lambda: psycopg.connect(DB_URL)


def save_source(connect,fixture_id="provider-fx-1",payload=b'{"fixture":"v1"}',key=None):
    digest=sha256(payload).hexdigest()
    record=ProviderSourceRecord(
        provider="5DollarFootballAPI",source_id="five-dollar",provider_record_id=fixture_id,
        provider_fixture_id=fixture_id,provider_competition_id="provider-comp-1",
        data_class="fixtures",raw_payload_sha256=digest,
        payload_reference=f"provider-response://{fixture_id}/{digest}",
        fetched_at_utc=NOW,ingested_at_utc=NOW,
        provider_home_team_id="provider-home",provider_away_team_id="provider-away")
    accepted=AcceptedSourceRecord(record,(RightsDecision(
        "five-dollar",DataUsePurpose.CACHE,True,"RIGHTS_VERIFIED"),))
    return PostgresProviderRecordRepository(connect).persist_accepted_record(
        accepted,raw_payload=payload,ingestion_run_id="run-1",
        idempotency_key=key or f"{fixture_id}:{digest}")


def rights():
    return SourceRights("five-dollar",RightsStatus.VERIFIED,True,
        frozenset({DataUsePurpose.HISTORICAL_IMPORT,DataUsePurpose.CACHE,DataUsePurpose.MODEL_TRAINING}),
        "https://provider.example/terms","2026-11",NOW,"b"*64)


def mappings(connect):
    repo=PostgresIdentityMappingRepository(connect)
    start=KICKOFF-timedelta(days=30)
    repo.add_competition_mapping(ProviderCompetitionMapping(
        "5DollarFootballAPI","five-dollar","provider-comp-1","canonical-comp-1",
        SquadCategory.SENIOR_MEN,MappingVerificationState.VERIFIED,"v1","evidence:comp",
        start,verified_at_utc=NOW-timedelta(days=1)))
    for pid,cid in (("provider-home","canonical-home"),("provider-away","canonical-away")):
        repo.add_team_mapping(ProviderTeamMapping(
            "5DollarFootballAPI","five-dollar",pid,cid,SquadCategory.SENIOR_MEN,
            MappingVerificationState.VERIFIED,"v1",f"evidence:{pid}",start,
            verified_at_utc=NOW-timedelta(days=1)))
    return repo


def fixture_source(fixture_id="provider-fx-1",kickoff=KICKOFF):
    return ProviderFixtureSourceIdentity("5DollarFootballAPI","five-dollar",fixture_id,
        "provider-comp-1","provider-home","provider-away",None,kickoff)


def test_postgres_schema_raw_versions_and_mapping_immutability(connect):
    first=save_source(connect)
    replay=save_source(connect,key="same-content-new-key")
    revised=save_source(connect,payload=b'{"fixture":"v2"}',key="fixture-v2")
    assert replay.source_record_id==first.source_record_id and replay.duplicate
    assert revised.source_record_id!=first.source_record_id
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM v2_source_records").fetchone()[0]==2
    repo=mappings(connect)
    assert len(repo.get_competition_mappings(provider="5DollarFootballAPI",
        source_id="five-dollar",provider_competition_id="provider-comp-1"))==1
    conflict=ProviderCompetitionMapping("5DollarFootballAPI","five-dollar","provider-comp-1",
        "wrong-comp",SquadCategory.SENIOR_MEN,MappingVerificationState.VERIFIED,
        "v1","evidence:wrong",KICKOFF-timedelta(days=30),verified_at_utc=NOW-timedelta(days=1))
    with pytest.raises(ValueError,match="IDENTITY_MAPPING_VERSION_CONFLICT"):
        repo.add_competition_mapping(conflict)


def test_postgres_reconciliation_quarantine_history_and_watermark(connect):
    raw=save_source(connect)
    repo=mappings(connect)
    source=fixture_source()
    resolved=resolve_provider_fixture(source,repo,evaluated_at_utc=NOW)
    assert resolved.status is MappingResolutionStatus.VERIFIED
    reconciliation=reconcile_provider_fixture(resolved.canonical_identity,())
    assert reconciliation.status is ReconciliationStatus.NEW_CANONICAL_FIXTURE
    decisions=PostgresFixtureDecisionRepository(connect)
    decisions.persist_decision(source,raw.source_record_id,resolved,decided_at_utc=NOW,
        reconciliation=reconciliation,new_canonical_fixture_id="canonical-fixture-1")

    parsed=FiveDollarFixtureRecord(
        source_identity=source,status=FiveDollarFixtureStatus.FINISHED,raw_status="finished",
        home_team_name="Home",away_team_name="Away",competition_name="League",
        completed_home_goals=2,completed_away_goals=1,status_reason=None,status_code="full",
        raw_payload_sha256=sha256(b'{"fixture":"v1"}').hexdigest())
    imported=build_training_history_match(parsed,resolved,raw.source_record_id,rights(),
        "canonical-fixture-1",evaluated_at_utc=NOW)
    assert imported.allowed
    store=PostgresHistoryStore(connect)
    store.persist_historical_match(imported.historical_match,imported_at_utc=NOW)
    history=store.get_team_history(TeamHistoryQuery(
        "canonical-home",SquadCategory.SENIOR_MEN.value,NOW,date(2026,1,1),
        ("canonical-comp-1",),10,1))
    assert history.total_match_count==1
    assert history.matches[0].provider_fixture_refs==(
        ("5DollarFootballAPI","five-dollar","provider-fx-1"),)

    raw2=save_source(connect,"provider-fx-2",b'{"fixture":"ambiguous"}')
    source2=fixture_source("provider-fx-2",KICKOFF+timedelta(days=1))
    resolved2=resolve_provider_fixture(source2,repo,evaluated_at_utc=NOW)
    ambiguous=ReconciliationDecision(ReconciliationStatus.AMBIGUOUS,None,
        ("candidate-a","candidate-b"),resolved2.canonical_identity)
    decisions.persist_decision(source2,raw2.source_record_id,resolved2,
        decided_at_utc=NOW,reconciliation=ambiguous)
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM v2_identity_quarantine").fetchone()[0]==1
        ids=conn.execute("SELECT provider_fixture_id,provider_competition_id FROM v2_fixture_sources WHERE provider_fixture_id='provider-fx-2'").fetchone()
        assert ids==("provider-fx-2","provider-comp-1")

    watermark=SyncWatermark("5DollarFootballAPI","fixtures","league-1","cursor-1",NOW,1)
    assert store.advance(watermark,expected_version=0)
    assert store.read(provider="5DollarFootballAPI",data_class="fixtures",scope="league-1")==watermark
    assert not store.advance(SyncWatermark("5DollarFootballAPI","fixtures","league-1","stale",NOW,1),
                             expected_version=0)


def test_watermark_version_and_timestamp_cannot_regress(connect):
    store=PostgresHistoryStore(connect)
    initial=SyncWatermark("5DollarFootballAPI","fixtures","scope","c1",NOW,1)
    assert store.advance(initial,expected_version=0)
    with pytest.raises(ValueError,match="WATERMARK_VERSION_MUST_ADVANCE_EXACTLY_ONCE"):
        store.advance(SyncWatermark("5DollarFootballAPI","fixtures","scope","c2",NOW,3),
                      expected_version=1)
    assert not store.advance(SyncWatermark("5DollarFootballAPI","fixtures","scope","c2",
        NOW-timedelta(seconds=1),2),expected_version=1)
    assert store.read(provider="5DollarFootballAPI",data_class="fixtures",scope="scope")==initial


def test_migration_runner_is_idempotent_and_detects_checksum_drift(connect):
    from scripts.v2_apply_migrations import apply_sql_migration
    sql=(Path(__file__).resolve().parents[2]/"migrations/v2/001_historical_store.sql").read_text()
    digest=sha256(sql.encode("utf-8")).hexdigest()
    with connect() as conn:
        assert apply_sql_migration(conn,migration_version="001_historical_store",
                                   sql=sql,checksum_sha256=digest)
        assert not apply_sql_migration(conn,migration_version="001_historical_store",
                                      sql=sql,checksum_sha256=digest)
        changed_sql=sql+"\\n-- checksum drift regression"
        changed_digest=sha256(changed_sql.encode("utf-8")).hexdigest()
        with pytest.raises(ValueError,match="APPLIED_MIGRATION_CHECKSUM_MISMATCH"):
            apply_sql_migration(conn,migration_version="001_historical_store",
                                sql=changed_sql,checksum_sha256=changed_digest)



def test_postgres_reconciliation_audit_reports_clean_empty_schema(connect):
    from veltrix_v2.audit.reconciliation import audit_postgres_reconciliation
    report = audit_postgres_reconciliation(connect)
    assert report.is_clean
    assert report.total_issues == 0
    assert {item.category for item in report.findings} == {
        "orphaned_source_records", "unresolved_competition_mappings",
        "unresolved_home_team_mappings", "unresolved_away_team_mappings",
        "provenance_gaps", "duplicate_canonical_fixtures",
    }


def test_postgres_reconciliation_audit_detects_integrity_gaps_without_mutation(connect):
    from veltrix_v2.audit.reconciliation import audit_postgres_reconciliation
    orphan = save_source(connect, "orphan-fixture")
    linked = save_source(connect, "linked-but-unverified")
    mismatched = save_source(connect, "mismatched-provider-provenance")

    with connect() as conn:
        conn.execute("""INSERT INTO v2_fixture_sources
            (provider,source_id,provider_fixture_id,provider_competition_id,
             provider_home_team_id,provider_away_team_id,canonical_fixture_id,
             source_record_id,identity_status,reason_code,evidence_refs)
            VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,'[]'::jsonb)""",
            ("wrong-provider", "wrong-source", "wrong-fixture", "wrong-comp",
             "wrong-home", "wrong-away", mismatched.source_record_id,
             "UNRESOLVED", "TEST_IDENTITY_MISMATCH"))
        conn.execute("""INSERT INTO v2_fixture_sources
            (provider,source_id,provider_fixture_id,provider_competition_id,
             provider_home_team_id,provider_away_team_id,canonical_fixture_id,
             source_record_id,identity_status,reason_code,evidence_refs)
            VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,'[]'::jsonb)""",
            ("5DollarFootballAPI", "five-dollar", "linked-but-unverified",
             "provider-comp-1", "provider-home", "provider-away",
             linked.source_record_id, "UNRESOLVED", "TEST_MAPPING_PENDING"))
        conn.execute("""INSERT INTO v2_canonical_fixtures
            (canonical_fixture_id,canonical_competition_id,squad_category,
             canonical_home_team_id,canonical_away_team_id,kickoff_at_utc)
            VALUES ('audit-canonical-a','audit-comp','SENIOR_MEN',
                    'audit-home','audit-away',%s)""", (KICKOFF,))
        conn.execute("""INSERT INTO v2_historical_matches
            (historical_match_id,canonical_fixture_id,home_goals,away_goals,imported_at_utc)
            VALUES ('audit-history-a','audit-canonical-a',1,0,%s)""", (NOW,))
        conn.execute("""INSERT INTO v2_canonical_fixtures
            (canonical_fixture_id,canonical_competition_id,squad_category,
             canonical_home_team_id,canonical_away_team_id,kickoff_at_utc)
            VALUES ('audit-canonical-b','audit-comp','SENIOR_MEN',
                    'audit-home','audit-away',%s)""", (KICKOFF,))

    with connect() as conn:
        before = tuple(conn.execute(
            f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in
            ("v2_source_records", "v2_fixture_sources",
             "v2_historical_matches", "v2_canonical_fixtures"))

    report = audit_postgres_reconciliation(connect)
    by_category = {item.category: item for item in report.findings}
    assert by_category["orphaned_source_records"].count == 1
    assert orphan.source_record_id in by_category["orphaned_source_records"].sample_ids
    assert by_category["unresolved_competition_mappings"].count >= 3
    assert by_category["unresolved_home_team_mappings"].count >= 3
    assert by_category["unresolved_away_team_mappings"].count >= 3
    assert by_category["provenance_gaps"].count == 2
    assert mismatched.source_record_id in by_category["provenance_gaps"].sample_ids
    assert by_category["duplicate_canonical_fixtures"].count == 1
    assert "audit-canonical-a,audit-canonical-b" in by_category["duplicate_canonical_fixtures"].sample_ids
    assert not report.is_clean

    with connect() as conn:
        after = tuple(conn.execute(
            f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in
            ("v2_source_records", "v2_fixture_sources",
             "v2_historical_matches", "v2_canonical_fixtures"))
    assert after == before


def test_postgres_reconciliation_audit_rejects_unbounded_sample_limit(connect):
    from veltrix_v2.audit.reconciliation import audit_postgres_reconciliation
    with pytest.raises(ValueError, match="SAMPLE_LIMIT_MUST_BE_BETWEEN_1_AND_100"):
        audit_postgres_reconciliation(connect, sample_limit=101)


def test_postgres_reconciliation_audit_flags_multiple_active_verified_mappings(connect):
    from veltrix_v2.audit.reconciliation import audit_postgres_reconciliation
    source = save_source(connect, "ambiguous-team-map")
    valid_from = KICKOFF - timedelta(days=30)
    with connect() as conn:
        conn.execute("""INSERT INTO v2_competition_mappings
            (provider,source_id,provider_competition_id,canonical_competition_id,
             squad_category,verification_state,mapping_version,evidence_ref,
             valid_from_utc,valid_to_utc,verified_at_utc)
            VALUES ('5DollarFootballAPI','five-dollar','provider-comp-1','canonical-comp-1',
                    'SENIOR_MEN','VERIFIED','v1','evidence:competition',%s,NULL,%s)""",
            (valid_from, NOW))
        for canonical_id, version in (("canonical-home-a", "v1"), ("canonical-home-b", "v2")):
            conn.execute("""INSERT INTO v2_team_mappings
                (provider,source_id,provider_team_id,canonical_team_id,squad_category,
                 verification_state,mapping_version,evidence_ref,valid_from_utc,valid_to_utc,verified_at_utc)
                VALUES ('5DollarFootballAPI','five-dollar','provider-home',%s,'SENIOR_MEN',
                        'VERIFIED',%s,'evidence:home',%s,NULL,%s)""",
                (canonical_id, version, valid_from, NOW))
        conn.execute("""INSERT INTO v2_team_mappings
            (provider,source_id,provider_team_id,canonical_team_id,squad_category,
             verification_state,mapping_version,evidence_ref,valid_from_utc,valid_to_utc,verified_at_utc)
            VALUES ('5DollarFootballAPI','five-dollar','provider-away','canonical-away','SENIOR_MEN',
                    'VERIFIED','v1','evidence:away',%s,NULL,%s)""", (valid_from, NOW))
        conn.execute("""INSERT INTO v2_fixture_sources
            (provider,source_id,provider_fixture_id,provider_competition_id,
             provider_home_team_id,provider_away_team_id,canonical_fixture_id,
             source_record_id,identity_status,reason_code,evidence_refs)
            VALUES ('5DollarFootballAPI','five-dollar','ambiguous-team-map','provider-comp-1',
                    'provider-home','provider-away',NULL,%s,'UNRESOLVED','AMBIGUOUS_TEAM','[]'::jsonb)""",
            (source.source_record_id,))

    report = audit_postgres_reconciliation(connect)
    by_category = {item.category: item for item in report.findings}
    assert by_category["unresolved_competition_mappings"].count == 0
    assert by_category["unresolved_home_team_mappings"].count == 1
    assert source.source_record_id in by_category["unresolved_home_team_mappings"].sample_ids
    assert by_category["unresolved_away_team_mappings"].count == 0
    assert by_category["orphaned_source_records"].count == 0

def test_postgres_database_acceptance_gate_checks_schema_and_migration_checksums(connect):
    from scripts.v2_apply_migrations import apply_all_migrations
    from scripts.v2_database_acceptance import inspect_database
    with connect() as conn:
        apply_all_migrations(conn)
    with connect() as conn:
        report = inspect_database(conn)
    assert report["accepted"], report
    assert report["missing_tables"] == []
    assert report["missing_columns"] == {}
    assert report["missing_indexes"] == []
    assert report["missing_constraints"] == []
    assert report["migration_checksum_errors"] == []
    assert report["tables_found"] >= report["tables_required"]

