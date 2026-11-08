from datetime import timedelta

from veltrix_v2.audit.reconciliation import audit_postgres_reconciliation


def test_postgres_reconciliation_audit_reports_clean_empty_schema(connect):
    report = audit_postgres_reconciliation(connect)
    assert report.is_clean
    assert report.total_issues == 0
    assert {item.category for item in report.findings} == {
        "orphaned_source_records",
        "unresolved_competition_mappings",
        "unresolved_home_team_mappings",
        "unresolved_away_team_mappings",
        "provenance_gaps",
        "duplicate_canonical_fixtures",
    }


def test_postgres_reconciliation_audit_detects_orphans_mappings_provenance_and_duplicates(connect):
    orphan = save_source(connect, "orphan-fixture")
    linked = save_source(connect, "linked-but-unverified")
    mismatched = save_source(connect, "mismatched-provider-provenance")

    with connect() as conn:
        # An explicit fixture-source row exists, but it does not match the
        # immutable provider identity stored on the source record.
        conn.execute("""INSERT INTO v2_fixture_sources
            (provider,source_id,provider_fixture_id,provider_competition_id,
             provider_home_team_id,provider_away_team_id,canonical_fixture_id,
             source_record_id,identity_status,reason_code,evidence_refs)
            VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,'[]'::jsonb)""",
            ("wrong-provider", "wrong-source", "wrong-fixture", "wrong-comp",
             "wrong-home", "wrong-away", mismatched.source_record_id,
             "UNRESOLVED", "TEST_IDENTITY_MISMATCH"))
        # A linked but unresolved provider identity must not be called orphaned.
        conn.execute("""INSERT INTO v2_fixture_sources
            (provider,source_id,provider_fixture_id,provider_competition_id,
             provider_home_team_id,provider_away_team_id,canonical_fixture_id,
             source_record_id,identity_status,reason_code,evidence_refs)
            VALUES (%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,'[]'::jsonb)""",
            ("5DollarFootballAPI", "five-dollar", "linked-but-unverified",
             "provider-comp-1", "provider-home", "provider-away",
             linked.source_record_id, "UNRESOLVED", "TEST_MAPPING_PENDING"))

        # A historical match without a source link is a provenance gap.
        conn.execute("""INSERT INTO v2_canonical_fixtures
            (canonical_fixture_id,canonical_competition_id,squad_category,
             canonical_home_team_id,canonical_away_team_id,kickoff_at_utc)
            VALUES ('audit-canonical-a','audit-comp','SENIOR_MEN',
                    'audit-home','audit-away',%s)""", (KICKOFF,))
        conn.execute("""INSERT INTO v2_historical_matches
            (historical_match_id,canonical_fixture_id,home_goals,away_goals,imported_at_utc)
            VALUES ('audit-history-a','audit-canonical-a',1,0,%s)""", (NOW,))

        # Exact duplicate natural fixture identity under a second canonical ID.
        conn.execute("""INSERT INTO v2_canonical_fixtures
            (canonical_fixture_id,canonical_competition_id,squad_category,
             canonical_home_team_id,canonical_away_team_id,kickoff_at_utc)
            VALUES ('audit-canonical-b','audit-comp','SENIOR_MEN',
                    'audit-home','audit-away',%s)""", (KICKOFF,))

    before = None
    with connect() as conn:
        before = (
            conn.execute("SELECT COUNT(*) FROM v2_source_records").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM v2_fixture_sources").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM v2_historical_matches").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM v2_canonical_fixtures").fetchone()[0],
        )

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

    # Audit must not repair, quarantine, merge or otherwise mutate records.
    with connect() as conn:
        after = (
            conn.execute("SELECT COUNT(*) FROM v2_source_records").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM v2_fixture_sources").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM v2_historical_matches").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM v2_canonical_fixtures").fetchone()[0],
        )
    assert after == before


def test_postgres_reconciliation_audit_rejects_unbounded_sample_limit(connect):
    import pytest
    with pytest.raises(ValueError, match="SAMPLE_LIMIT_MUST_BE_BETWEEN_1_AND_100"):
        audit_postgres_reconciliation(connect, sample_limit=101)
