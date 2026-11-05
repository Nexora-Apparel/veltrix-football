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


def test_cross_provider_same_identity_merges_and_keeps_all_source_ids():
    rows = [
        fixture(
            "5d-100", "5DollarFootballAPI", "Manchester United", "Chelsea",
            39, "Premier League", "2026-11-04T22:30:00Z",
        ),
        fixture(
            "infer-200", "InferSports", "Manchester United", "Chelsea",
            "lg-epl", "Premier League", "2026-11-04T22:32:00Z",
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



def test_b_team_is_not_merged_with_senior_club():
    senior = team_identity("FC Porto")
    reserve = team_identity("FC Porto B")

    assert senior[0] == reserve[0]
    assert senior[1] == ()
    assert reserve[1] == ("reserve",)

    rows = [
        fixture("porto-senior", "ProviderA", "FC Porto", "Sporting",
                "pt-senior", "Portugal Primeira Liga", "2026-11-04T20:00:00Z"),
        fixture("porto-b", "ProviderB", "FC Porto B", "Sporting B",
                "pt-reserve", "Portugal Reserve League", "2026-11-04T20:00:00Z"),
    ]
    canonical, _ = reconcile_fixture_rows(rows)
    assert len(canonical) == 2


def test_same_named_competitions_in_different_countries_are_not_merged():
    rows = [
        fixture("eng-1", "ProviderA", "Club A", "Club B", 1,
                "Premier League", "2026-11-04T12:00:00Z"),
        fixture("rsa-1", "ProviderB", "Club A", "Club B", 2,
                "Premier League", "2026-11-04T12:01:00Z"),
    ]
    rows[0]["league"]["country"] = "England"
    rows[1]["league"]["country"] = "South Africa"

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["quarantined_rows"] == 2
    assert canonical[0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"
    assert "competition_identity_conflict" in canonical[0]["_veltrix_quarantine_reasons"]



def test_same_competition_name_in_different_countries_is_quarantined():
    left = fixture(
        "country-a", "ProviderA", "United FC", "City FC", 1,
        "Premier League", "2026-11-04T18:00:00Z",
    )
    right = fixture(
        "country-b", "ProviderB", "United FC", "City FC", "pl-2",
        "Premier League", "2026-11-04T18:01:00Z",
    )
    left["league"]["country"] = "England"
    right["league"]["country"] = "Scotland"

    canonical, meta = reconcile_fixture_rows([left, right])

    assert len(canonical) == 1
    assert canonical[0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"
    assert "competition_identity_conflict" in canonical[0]["_veltrix_quarantine_reasons"]
    assert {item["competition_country"] for item in canonical[0]["_veltrix_provenance"]} == {
        "England", "Scotland",
    }
    assert meta["quarantined_rows"] == 2


def test_same_teams_same_competition_with_small_kickoff_drift_is_quarantined():
    rows = [
        fixture("feed-a", "ProviderA", "Club A", "Club B", 55,
                "Premier League", "2026-11-04T12:00:00Z"),
        fixture("feed-b", "ProviderB", "Club A", "Club B", "epl",
                "Premier League", "2026-11-04T12:15:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["confirmed_duplicate_groups"] == 0
    assert meta["quarantined_rows"] == 2
    assert canonical[0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"
    assert "kickoff_proximity_conflict" in canonical[0]["_veltrix_quarantine_reasons"]
    assert {record["fixture_id"] for record in canonical[0]["_veltrix_source_fixture_ids"]} == {
        "feed-a", "feed-b",
    }


def test_u19_competition_supplies_squad_identity_when_team_names_omit_suffix():
    rows = [
        fixture("youth-a", "ProviderA", "Zilina", "Helsinki", 700,
                "UEFA U19", "2026-11-04T15:30:00Z"),
        fixture("youth-b", "ProviderB", "Zilina U19", "Helsinki U19", "youth-700",
                "UEFA U19", "2026-11-04T15:31:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["confirmed_duplicate_groups"] == 1
    assert meta["quarantined_rows"] == 0
    assert canonical[0]["_veltrix_reconciliation_status"] == "MATCHED"
    assert {item["fixture_id"] for item in canonical[0]["_veltrix_source_fixture_ids"]} == {
        "youth-a", "youth-b",
    }


def test_observed_u19_name_variants_are_quarantined_until_team_ids_verify_alias():
    rows = [
        fixture("sheriff-short", "InferSports", "Sheriff", "Farul",
                "lg-youth", "UEFA U19", "2026-11-04T17:00:00Z"),
        fixture("sheriff-full", "InferSports", "Sheriff Tiraspol U19", "Farul Constanta U19",
                "lg-youth", "UEFA U19", "2026-11-04T17:00:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["confirmed_duplicate_groups"] == 0
    assert meta["quarantined_rows"] == 2
    assert canonical[0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"
    assert "team_alias_not_verified" in canonical[0]["_veltrix_quarantine_reasons"]
    assert {item["fixture_id"] for item in canonical[0]["_veltrix_source_fixture_ids"]} == {
        "sheriff-short", "sheriff-full",
    }


def test_observed_reserve_name_variants_are_quarantined_not_auto_aliased():
    rows = [
        fixture("reserve-short", "InferSports", "Almirante", "DD.Belgrano",
                "lg-reserve", "Argentina Reserve League", "2026-11-04T17:00:00Z"),
        fixture("reserve-full", "InferSports", "Almirante Brown(R)", "DD.Belgrano(R)",
                "lg-reserve", "Argentina Reserve League", "2026-11-04T17:00:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 1
    assert meta["confirmed_duplicate_groups"] == 0
    assert meta["quarantined_rows"] == 2
    assert canonical[0]["_veltrix_reconciliation_status"] == "AMBIGUOUS"
    assert "team_alias_not_verified" in canonical[0]["_veltrix_quarantine_reasons"]
    assert {item["fixture_id"] for item in canonical[0]["_veltrix_source_fixture_ids"]} == {
        "reserve-short", "reserve-full",
    }


def test_abbreviated_womens_competition_keeps_unmarked_teams_separate_from_senior():
    rows = [
        fixture("senior-pol", "ProviderA", "GKS Katowice", "UKS SMS Lodz",
                "pol-senior", "Poland Ekstraklasa", "2026-11-04T17:00:00Z"),
        fixture("women-pol", "ProviderB", "GKS Katowice", "UKS SMS Lodz",
                "pol-women", "Pol(W)", "2026-11-04T17:00:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 2
    assert meta["confirmed_duplicate_groups"] == 0


def test_abbreviated_argentine_reserve_competition_infers_reserve_squad():
    rows = [
        fixture("senior-arg", "ProviderA", "Almirante Brown", "Belgrano",
                "arg-senior", "Argentine Primera Division", "2026-11-04T17:00:00Z"),
        fixture("reserve-arg", "ProviderB", "Almirante Brown", "Belgrano",
                "arg-reserve", "Arg(R)", "2026-11-04T17:00:00Z"),
    ]

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 2
    assert meta["confirmed_duplicate_groups"] == 0


def test_november_4_published_fixture_identity_audit_preserves_every_provider_id():
    rows = [
        fixture("9c9b60495c9667d04bcdba59483a623f", "The Odds API",
                "Atletico Paranaense", "Vasco da Gama", None,
                "Brazilian Serie A", "2026-11-04T22:30:00Z"),
        fixture("evt_WB7SJMR6", "InferSports",
                "Atletico PR", "Vasco DG", "lg_TF968DXK",
                "Bra A", "2026-11-04T22:30:00Z"),
        fixture("00471c0b94da413be9689767f2d4a571", "The Odds API",
                "Flamengo", "Grêmio", None,
                "Brazilian Serie A", "2026-11-04T22:30:00Z"),
        fixture("evt_CG8BZVP3", "InferSports",
                "Flamengo", "Gremio PA", "lg_TF968DXK",
                "Bra A", "2026-11-04T22:30:00Z"),
        fixture("evt_B60XEEVP", "InferSports",
                "Zilina", "Helsinki", "lg_H84K26EK",
                "UEFAU19", "2026-11-04T15:30:00Z"),
        fixture("evt_9DY03SH2", "InferSports",
                "Zilina U19", "Helsinki U19", "lg_H84K26EK",
                "UEFAU19", "2026-11-04T15:31:00Z"),
        fixture("evt_4RXTN5QV", "InferSports",
                "Sheriff", "Farul", "lg_H84K26EK",
                "UEFAU19", "2026-11-04T16:00:00Z"),
        fixture("evt_QND65ZCS", "InferSports",
                "Sheriff Tiraspol U19", "Farul Constanta U19", "lg_H84K26EK",
                "UEFAU19", "2026-11-04T16:00:00Z"),
        fixture("evt_PYMFBFWS", "InferSports",
                "Super Nova", "Hammarby", "lg_H84K26EK",
                "UEFAU19", "2026-11-04T16:00:00Z"),
        fixture("evt_CG8EE7P3", "InferSports",
                "Super Nova U19", "Hammarby U19", "lg_H84K26EK",
                "UEFAU19", "2026-11-04T16:01:00Z"),
        fixture("evt_B60X73VP", "InferSports",
                "Almirante", "DD.Belgrano", "lg_M42A7TV6",
                "Arg(R)", "2026-11-04T16:00:00Z"),
        fixture("evt_QND6XRCS", "InferSports",
                "Almirante Brown(R)", "DD.Belgrano(R)", "lg_M42A7TV6",
                "Arg(R)", "2026-11-04T16:00:00Z"),
        fixture("evt_YT1AMNBW", "InferSports",
                "Agropecuario", "CAF midland", "lg_M42A7TV6",
                "Arg(R)", "2026-11-04T16:00:00Z"),
        fixture("evt_YT1A3VBW", "InferSports",
                "Agropecuario Argentino(R)", "Ferrocarril Midland(R)", "lg_M42A7TV6",
                "Arg(R)", "2026-11-04T16:00:00Z"),
    ]
    for row in rows:
        if row["_veltrix_source"] == "The Odds API":
            row["league"]["country"] = "Brazil"
        elif row["league"]["name"] in {"Brazilian Serie A", "Bra A"}:
            row["league"]["country"] = "Brazil"

    canonical, meta = reconcile_fixture_rows(rows)

    assert len(canonical) == 7
    assert meta["input_rows"] == 14
    assert meta["confirmed_duplicate_groups"] == 2
    assert meta["quarantined_rows"] == 10
    preserved = {
        record["fixture_id"]
        for row in canonical
        for record in row["_veltrix_source_fixture_ids"]
    }
    assert preserved == {row["fixture"]["id"] for row in rows}
    assert len(preserved) == 14
    assert all(row["_veltrix_provenance"] for row in canonical)
    assert all(
        len(row["_veltrix_source_fixture_ids"]) == 2
        for row in canonical
    )
