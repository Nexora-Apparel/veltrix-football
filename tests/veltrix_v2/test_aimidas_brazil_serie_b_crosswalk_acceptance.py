from __future__ import annotations

from scripts.veltrix_v2.accept_aimidas_brazil_serie_b_crosswalks import (
    EXPECTED_CROSSWALKS, REVIEWER_ID, validate_report,
)


def _fixture_match(i, *, stats="ROW_STATS_CONSISTENT"):
    return {
        "source_match_key_sha256": f"{i:064x}",
        "canonical_fixture_id": 10000 + i,
        "canonical_provider_fixture_id": str(20000 + i),
        "source_date": "2026-03-21",
        "canonical_kickoff_at": "2026-03-21T20:00:00+00:00",
        "source_to_canonical_utc_date_delta_days": 0,
        "source_row_line_numbers": [2 + 2*i, 3 + 2*i],
        "source_row_sha256": [f"{i+1:064x}", f"{i+2:064x}"],
        "source_row_ids": ["row-a", "row-b"],
        "score_agreement": True,
        "review_status": "REVIEW_REQUIRED",
        "crosswalk_resolution": "NOT_RESOLVED",
        "team_stat_discrepancy_count": 2 if stats != "ROW_STATS_CONSISTENT" else 0,
        "team_stats_quality_status": stats,
    }


def _report():
    team_names = [
        ("América Mineiro", "America MG", 3618, "EXPLICIT_ALIAS_TABLE"),
        ("Athletic Club MG", "Athletic Club MG", 3619, "EXACT_NAME"),
    ] + [
        (f"Source Team {i}", f"Canonical Team {i}", 3620+i, "EXACT_NAME")
        for i in range(18)
    ]
    teams = [{
        "source_team": source, "canonical_team": canonical,
        "canonical_team_registry_id": cid, "canonical_provider_team_id": str(5000+i),
        "mapping_method": method, "review_status": "REVIEW_REQUIRED",
    } for i, (source, canonical, cid, method) in enumerate(team_names)]
    matches = [_fixture_match(i) for i in range(369)]
    matches[-1]["team_stat_discrepancy_count"] = 2
    matches[-1]["team_stats_quality_status"] = "QUARANTINED_ROW_SCORE_MISMATCH"
    return {
        "schema_version": "veltrix-aimidas-brazil-serie-b-identity-audit-v1",
        "source": {
            "commit": "29baca362a34ce5dcd3924b07ec9c7d5139d83fc",
            "file_sha256": "55b0c00629abd2d4ff3c31659ada950b67ffc2752609284b32c15c99f71152ab",
            "approval_id": "approval-aimidas-football-data-noncommercial-2026-11-15",
            "source_id": "ai-midas-github-csv",
            "source_observation_id": 432397,
        },
        "database": {
            "database": "veltrix_football_staging",
            "canonical_2026_fixture_count": 371,
            "canonical_team_count": 20,
        },
        "summary": {
            "source_matches_total": 369, "source_matches_verified": 369,
            "unique_canonical_fixture_ids": 369, "independent_score_agreements": 369,
            "score_disagreements": 0, "ambiguous_fixture_candidates": 0,
            "fixture_identity_failures": 0, "duplicate_source_match_groups": 0,
            "source_team_identities_verified": 20, "quarantined_team_stat_rows": 2,
            "team_stat_matches_with_discrepancies": 1, "canonical_fixtures_absent_from_source": 2,
            "crosswalk_rows_written": 0, "crosswalk_rows_resolved": 0,
        },
        "team_mappings": teams,
        "matches": matches,
        "missing_canonical_fixtures": [
            {"disposition": "UNRESOLVED_NO_REPLACEMENT_MAPPING"},
            {"disposition": "UNRESOLVED_NO_REPLACEMENT_MAPPING"},
        ],
    }


def _source_rows(report):
    rows = []
    for match in report["matches"]:
        for index, line in enumerate(match["source_row_line_numbers"]):
            rows.append({
                "source_line_number": line,
                "source_row_sha256": match["source_row_sha256"][index],
                "source_date": match["source_date"],
                "match_label": "América Mineiro 1-0 Athletic Club MG",
                "source_team_raw": "América Mineiro" if index == 0 else "Athletic Club MG",
                "match": {"home_raw": "América Mineiro", "away_raw": "Athletic Club MG", "home_score": 1, "away_score": 0},
            })
    return rows


def test_acceptance_prepares_only_20_teams_and_369_fixtures():
    report = _report()
    team_rows, fixture_rows = validate_report(report, _source_rows(report))
    assert len(team_rows) == 20
    assert len(fixture_rows) == 369
    assert len(team_rows) + len(fixture_rows) == EXPECTED_CROSSWALKS
    assert REVIEWER_ID == "automated-independent-reconciliation-v1"
    assert all(row["entity_type"] == "TEAM" for row in team_rows)
    assert all(row["entity_type"] == "FIXTURE" for row in fixture_rows)


def test_identity_mapping_can_be_resolved_while_conflicting_team_stats_stay_quarantined():
    report = _report()
    _, fixture_rows = validate_report(report, _source_rows(report))
    disputed = next(row for row in fixture_rows if "TEAM_STATS_QUARANTINE" in row["decision_reason"])
    assert disputed["mapping_method"] == "EXACT_TEAM_ORIENTATION_DATE_SCORE"
    assert "those statistics remain excluded" in disputed["decision_reason"]


def test_acceptance_rejects_any_score_disagreement_or_ambiguous_identity():
    report = _report()
    report["matches"][0]["score_agreement"] = False
    try:
        validate_report(report, _source_rows(report))
    except RuntimeError as exc:
        assert "FIXTURE_EVIDENCE_INVALID" in str(exc)
    else:
        raise AssertionError("score disagreement was accepted")

    report = _report()
    report["summary"]["ambiguous_fixture_candidates"] = 1
    try:
        validate_report(report, _source_rows(report))
    except RuntimeError as exc:
        assert "AUDIT_GATES_NOT_PASSED" in str(exc)
    else:
        raise AssertionError("ambiguous candidates were accepted")


def test_acceptance_never_resolves_the_two_unmatched_canonical_fixtures():
    report = _report()
    team_rows, fixture_rows = validate_report(report, _source_rows(report))
    fixture_source_ids = {row["provider_entity_id"] for row in fixture_rows}
    assert len(fixture_source_ids) == 369
    assert len(report["missing_canonical_fixtures"]) == 2
    assert all(item["disposition"] == "UNRESOLVED_NO_REPLACEMENT_MAPPING" for item in report["missing_canonical_fixtures"])
