from __future__ import annotations

from app.fixture_identity import reconcile_fixture_rows, team_identity


def fixture(
    fixture_id: str,
    provider: str,
    home: str,
    away: str,
    competition_id: str | int | None,
    competition: str | None,
    kickoff: str,
):
    return {
        "fixture": {
            "id": fixture_id,
            "date": kickoff,
            "status": {"short": "NS"},
        },
        "teams": {
            "home": {"id": f"{provider}-home-{fixture_id}", "name": home},
            "away": {"id": f"{provider}-away-{fixture_id}", "name": away},
        },
        "league": {"id": competition_id, "name": competition},
        "_veltrix_source": provider,
    }


def test_cross_provider_verified_aliases_merge_and_keep_all_source_ids():
    rows = [
        fixture(
            "5d-100", "5DollarFootballAPI", "Manchester United", "Chelsea",
            39, "Premier League", "2026-11-04T22:30:00Z",
        ),
        fixture(
            "infer-200", "InferSports", "Man Utd", "Chelsea",
            "lg-epl", "English Premier League", "2026-11-04T22:32:00Z",
        ),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["confirmed_duplicate_groups"] == 1
    merged = canonical[0]
    assert merged["_veltrix_canonical_fixture"] is True
    assert merged["_veltrix_reconciliation_status"] == "MATCHED"
    assert merged["_veltrix_source_fixture_ids"] == [
        {"provider": "5DollarFootballAPI", "fixture_id": "5d-100"},
        {"provider": "InferSports", "fixture_id": "infer-200"},
    ]
    assert {item["competition_id"] for item in merged["_veltrix_provenance"]} == {39, "lg-epl"}
    assert {item["provider"] for item in merged["_veltrix_provenance"]} == {
        "5DollarFootballAPI", "InferSports",
    }


def test_senior_and_u19_fixtures_are_never_merged():
    rows = [
        fixture("senior-1", "ProviderA", "Zilina", "Helsinki", 10,
                "Domestic Cup", "2026-11-04T15:30:00Z"),
        fixture("youth-1", "ProviderB", "Zilina U19", "Helsinki U19", "youth-10",
                "UEFA U19", "2026-11-04T15:30:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 2
    assert meta["confirmed_duplicate_groups"] == 0
    assert {row["fixture"]["id"] for row in canonical} == {"senior-1", "youth-1"}


def test_reserve_identity_is_distinct_from_senior_club_identity():
    senior = team_identity("Almirante Brown")
    reserve = team_identity("Almirante Brown (R)")

    assert senior[0] == reserve[0]
    assert senior[1] == ()
    assert reserve[1] == ("reserve",)

    rows = [
        fixture("senior-2", "ProviderA", "Almirante Brown", "Belgrano",
                "arg-senior", "Argentine Primera Division", "2026-11-04T16:00:00Z"),
        fixture("reserve-2", "ProviderB", "Almirante Brown (R)", "Belgrano (R)",
                "arg-reserve", "Argentina Reserve League", "2026-11-04T16:00:00Z"),
    ]

    canonical, _ = reconcile_fixture_rows(rows)

    assert len(canonical) == 2


def test_same_team_doubleheaders_with_distinct_kickoffs_are_preserved():
    rows = [
        fixture("match-early", "ProviderA", "Club A", "Club B", 55,
                "Premier League", "2026-11-04T12:00:00Z"),
        fixture("match-late", "ProviderA", "Club A", "Club B", 55,
                "Premier League", "2026-11-04T14:00:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 2
    assert meta["confirmed_duplicate_groups"] == 0
    assert {row["fixture"]["id"] for row in canonical} == {"match-early", "match-late"}


def test_missing_competition_identity_quarantines_instead_of_dropping():
    rows = [
        fixture("unknown-a", "ProviderA", "Club A", "Club B", 55,
                None, "2026-11-04T12:00:00Z"),
        fixture("unknown-b", "ProviderB", "Club A", "Club B", 99,
                None, "2026-11-04T12:01:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["quarantined_rows"] == 2
    assert canonical[0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"
    assert {row["fixture_id"] for row in canonical[0]["_veltrix_source_fixture_ids"]} == {"unknown-a", "unknown-b"}



def test_same_teams_and_kickoff_with_conflicting_competitions_are_quarantined():
    rows = [
        fixture("comp-a", "ProviderA", "Club A", "Club B", 1,
                "League Alpha", "2026-11-04T12:00:00Z"),
        fixture("comp-b", "ProviderB", "Club A", "Club B", 2,
                "League Beta", "2026-11-04T12:01:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["quarantined_rows"] == 2
    assert canonical[0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"


def test_inter_is_not_misclassified_as_a_reserve_team():
    from app.live_predictions import _name_key, _team_variant_signature

    assert _team_variant_signature(_name_key("Inter")) == ()
    assert "reserve" in _team_variant_signature(_name_key("Almirante Brown (R)"))
    assert "women" in _team_variant_signature(_name_key("Arsenal (W)"))


def test_fixture_selection_does_not_truncate_provider_records_at_25():
    from datetime import date, datetime
    from scripts.run_daily_predictions import _limit_fixture_payload

    rows = [
        fixture(
            f"fixture-{index}", "ProviderA", f"Home Club {index}", f"Away Club {index}",
            "premier-league", "Premier League",
            f"2026-11-04T{12 + index // 60:02d}:{index % 60:02d}:00Z",
        )
        for index in range(30)
    ]
    payload = {"response": rows}
    selected = _limit_fixture_payload(
        payload, 25, as_of_date=date(2026, 11, 4),
        now=datetime.fromisoformat("2026-11-04T09:00:00+01:00"),
    )

    assert len(selected["response"]) == 30
    assert len({
        record["fixture_id"]
        for row in selected["response"]
        for record in row["_veltrix_source_fixture_ids"]
    }) == 30
    assert selected["_veltrix_meta"]["legacy_fixture_cap_ignored"] == 25


def test_unverified_provider_team_abbreviations_are_quarantined_not_merged():
    rows = [
        fixture("primary-1", "5DollarFootballAPI", "Atletico Paranaense", "Vasco da Gama",
                71, "Brazilian Serie A", "2026-11-04T22:30:00Z"),
        fixture("infer-1", "InferSports", "Atletico PR", "Vasco DG",
                "lg-bra", "Bra A", "2026-11-04T22:32:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["confirmed_duplicate_groups"] == 0
    assert meta["quarantined_rows"] == 2
    assert canonical[0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"
    assert "team_alias_not_verified" in canonical[0]["_veltrix_quarantine_reasons"]
    assert {row["fixture_id"] for row in canonical[0]["_veltrix_source_fixture_ids"]} == {"primary-1", "infer-1"}


def test_missing_kickoff_fixture_is_retained_and_quarantined():
    row = fixture(
        "missing-kickoff", "ProviderA", "Club A", "Club B",
        55, "Premier League", "2026-11-04T12:00:00Z",
    )
    row["fixture"]["date"] = None

    from scripts.run_daily_predictions import _limit_fixture_payload
    from datetime import date

    selected = _limit_fixture_payload(
        {"response": [row]}, 25, as_of_date=date(2026, 11, 4),
    )

    assert len(selected["response"]) == 1
    assert selected["response"][0]["fixture"]["id"] == "missing-kickoff"
    assert selected["response"][0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"
    assert "MISSING_KICKOFF" in selected["_veltrix_meta"]["invalid_fixture_source_records"][0]["reason"]
