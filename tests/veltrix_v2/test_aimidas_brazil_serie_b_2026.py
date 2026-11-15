from __future__ import annotations

import pytest

from scripts.veltrix_v2 import reconcile_aimidas_brazil_serie_b_2026 as audit


def test_team_aliases_are_explicit_and_one_to_one():
    assert audit.canonical_team_name("América Mineiro") == "America MG"
    assert audit.canonical_team_name("Atlético Goianiense") == "Atletico GO"
    assert audit.canonical_team_name("São Bernardo") == "Sao Bernardo"
    assert audit.canonical_team_name("Ponte Preta") == "Ponte Preta"


def test_match_label_parser_preserves_home_away_and_score_orientation():
    assert audit.parse_match_label("Goiás 1-0 Ponte Preta") == {
        "home_raw": "Goiás", "home_score": 1, "away_score": 0, "away_raw": "Ponte Preta"
    }


def test_match_label_parser_rejects_malformed_input():
    with pytest.raises(ValueError, match="AIMIDAS_MATCH_LABEL_INVALID"):
        audit.parse_match_label("not a match")


def test_source_match_key_is_stable_and_date_sensitive():
    first = audit.source_match_key("2026-11-08", "Goiás 1-0 Ponte Preta")
    assert first == audit.source_match_key("2026-11-08", "Goiás 1-0 Ponte Preta")
    assert first != audit.source_match_key("2026-11-09", "Goiás 1-0 Ponte Preta")


def test_row_hash_is_order_independent_but_value_sensitive():
    row = {"Team": "Goiás", "Goals": "1", "Date": "2026-11-08"}
    assert audit.canonical_row_hash(row) == audit.canonical_row_hash(dict(reversed(list(row.items()))))
    assert audit.canonical_row_hash(row) != audit.canonical_row_hash({**row, "Goals": "2"})


def test_candidate_reconciliation_requires_unique_fixture_and_score():
    rows = []
    for line, team, goals, conceded in [(2, "Goiás", 1, 0), (3, "Ponte Preta", 0, 1)]:
        label = "Goiás 1-0 Ponte Preta"
        parsed = audit.parse_match_label(label)
        rows.append({
            "source_line_number": line, "source_row_sha256": "a" * 64,
            "source_row_id": f"row-{line}", "source_team_raw": team,
            "source_team_canonical": audit.canonical_team_name(team),
            "match_label": label, "source_date_raw": "2026-11-08",
            "source_date": "2026-11-08", "match": parsed,
            "row_goals": goals, "row_goals_conceded": conceded,
        })
    registry = {
        "database": "veltrix_football_staging", "role": "neondb_owner",
        "transaction_read_only": "on",
        "staging_evidence": {"source_observation_id": 1, "provider_response_id": 2},
        "teams": [
            {"id": 1, "provider_team_id": "goias", "name": "Goias"},
            {"id": 2, "provider_team_id": "ponte", "name": "Ponte Preta"},
        ],
        "fixtures": [{
            "fixture_id": 10, "provider_fixture_id": "fixture-10",
            "kickoff_at": "2026-11-08T22:00:00+00:00", "kickoff_date": "2026-11-08",
            "status": "FINISHED", "home_team_id": 1, "home_provider_team_id": "goias",
            "home_name": "Goias", "away_team_id": 2, "away_provider_team_id": "ponte",
            "away_name": "Ponte Preta", "home_score": 1, "away_score": 0,
        }],
    }
    source_record = {"git_blob_sha1": "b" * 40, "sha256": "c" * 64, "actual_bytes": 123}
    result = audit.reconcile(rows, registry, source_record,
                             expected_matches=1, expected_teams=2, expected_missing=0)
    assert result["summary"]["source_matches_verified"] == 1
    assert result["summary"]["independent_score_agreements"] == 1
    assert result["matches"][0]["review_status"] == "REVIEW_REQUIRED"
    assert result["summary"]["database_mutations"] == 0


def test_conflicting_fixture_candidates_fail_closed():
    rows = []
    for line, team, goals, conceded in [(2, "Goiás", 1, 0), (3, "Ponte Preta", 0, 1)]:
        label = "Goiás 1-0 Ponte Preta"
        rows.append({
            "source_line_number": line, "source_row_sha256": "a" * 64,
            "source_row_id": f"row-{line}", "source_team_raw": team,
            "source_team_canonical": audit.canonical_team_name(team),
            "match_label": label, "source_date_raw": "2026-11-08",
            "source_date": "2026-11-08", "match": audit.parse_match_label(label),
            "row_goals": goals, "row_goals_conceded": conceded,
        })
    fixture = {
        "fixture_id": 10, "provider_fixture_id": "fixture-10",
        "kickoff_at": "2026-11-08T22:00:00+00:00", "kickoff_date": "2026-11-08",
        "status": "FINISHED", "home_team_id": 1, "home_provider_team_id": "goias",
        "home_name": "Goias", "away_team_id": 2, "away_provider_team_id": "ponte",
        "away_name": "Ponte Preta", "home_score": 1, "away_score": 0,
    }
    registry = {
        "database": "veltrix_football_staging", "role": "neondb_owner",
        "transaction_read_only": "on", "staging_evidence": {"source_observation_id": 1, "provider_response_id": 2},
        "teams": [{"id": 1, "provider_team_id": "goias", "name": "Goias"},
                  {"id": 2, "provider_team_id": "ponte", "name": "Ponte Preta"}],
        "fixtures": [fixture, {**fixture, "fixture_id": 11, "provider_fixture_id": "fixture-11"}],
    }
    source_record = {"git_blob_sha1": "b" * 40, "sha256": "c" * 64, "actual_bytes": 123}
    with pytest.raises(RuntimeError, match="FIXTURE_CANDIDATE_CARDINALITY"):
        audit.reconcile(rows, registry, source_record,
                        expected_matches=1, expected_teams=2, expected_missing=0)


def test_team_stat_mismatch_is_quarantined_without_rejecting_match_identity():
    label = "Náutico 0-3 CRB"
    rows = [
        {
            "source_line_number": 8, "source_row_sha256": "d" * 64,
            "source_row_id": "row-8", "source_team_raw": "CRB",
            "source_team_canonical": "CRB", "match_label": label,
            "source_date_raw": "2026-03-22", "source_date": "2026-03-22",
            "match": audit.parse_match_label(label), "row_goals": 2,
            "row_goals_conceded": 0,
        },
        {
            "source_line_number": 9, "source_row_sha256": "e" * 64,
            "source_row_id": "row-9", "source_team_raw": "Náutico",
            "source_team_canonical": "Nautico", "match_label": label,
            "source_date_raw": "2026-03-22", "source_date": "2026-03-22",
            "match": audit.parse_match_label(label), "row_goals": 0,
            "row_goals_conceded": 2,
        },
    ]
    registry = {
        "database": "veltrix_football_staging", "role": "neondb_owner",
        "transaction_read_only": "on",
        "staging_evidence": {"source_observation_id": 1, "provider_response_id": 2},
        "teams": [
            {"id": 1, "provider_team_id": "nautico", "name": "Nautico"},
            {"id": 2, "provider_team_id": "crb", "name": "CRB"},
        ],
        "fixtures": [{
            "fixture_id": 30, "provider_fixture_id": "fixture-30",
            "kickoff_at": "2026-03-22T20:00:00+00:00", "kickoff_date": "2026-03-22",
            "status": "FINISHED", "home_team_id": 1, "home_provider_team_id": "nautico",
            "home_name": "Nautico", "away_team_id": 2, "away_provider_team_id": "crb",
            "away_name": "CRB", "home_score": 0, "away_score": 3,
        }],
    }
    source_record = {"git_blob_sha1": "b" * 40, "sha256": "c" * 64, "actual_bytes": 123}
    result = audit.reconcile(rows, registry, source_record,
                             expected_matches=1, expected_teams=2, expected_missing=0)
    assert result["summary"]["source_matches_verified"] == 1
    assert result["summary"]["independent_score_agreements"] == 1
    assert result["summary"]["source_row_score_consistency_checks"] == 2
    assert result["summary"]["source_row_score_consistency_failures"] == 2
    assert result["summary"]["quarantined_team_stat_rows"] == 2
    assert result["matches"][0]["team_stats_quality_status"] == "QUARANTINED_ROW_SCORE_MISMATCH"
    assert {item["source_line_number"] for item in result["row_score_discrepancies"]} == {8, 9}
