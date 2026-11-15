from datetime import date, datetime, timezone

from scripts.veltrix_v2.persist_openplay_feature_snapshots import (
    _feature_value,
    _select_team_rows,
    sha256,
)
from veltrix_v2.data.openplay_feature_bundle import canonical_json_bytes


def _row(team="10", comp="20", match_date="2026-11-01", eligibility="2026-11-15T13:00:00+00:00"):
    return {
        "canonical_team_id":team,
        "canonical_competition_id":comp,
        "match_date":match_date,
        "eligibility_at":eligibility,
        "provider_match_id":"m-"+match_date,
        "metrics":{"xg":1.2},
        "xg_model":"openplay_xg_v1",
        "feature_sha256":"a"*64,
        "source_timestamp_basis":"documented_guarantee",
        "source_observation_payload_sha256":"b"*64,
        "point_in_time_certifiable":True,
        "commercial_use_allowed":False,
        "monetisation_prohibited":True,
        "rights_approval_id":"approval-openplay-whoscored-opta-noncommercial-2026-11-15",
        "source_observation_id":1,
        "provider_response_id":1,
        "asset_provenance":{
            name:{"provider_response_id":1,"source_observation_id":1,"sha256":"c"*64}
            for name in ("matches.parquet","team_match_stats.parquet","player_match_stats.parquet",
                         "lineups.parquet","shots.parquet","cards.parquet","formations.parquet",
                         "teams.parquet","competitions.parquet")
        },
        "crosswalk_provenance":{
            "team":{"provider_entity_id":"p-team","canonical_entity_id":team,"crosswalk_version_id":1,
                    "evidence_observation_id":1,"mapping_status":"RESOLVED","mapping_method":"EXACT_NAME_AND_COMPETITION_OVERLAP"},
            "opponent":{"provider_entity_id":"p-opp","canonical_entity_id":"11","crosswalk_version_id":2,
                        "evidence_observation_id":1,"mapping_status":"RESOLVED","mapping_method":"EXACT_NAME_AND_COMPETITION_OVERLAP"},
            "competition":{"provider_entity_id":"comp","canonical_entity_id":comp,"crosswalk_version_id":3,
                           "evidence_observation_id":1,"mapping_status":"RESOLVED","mapping_method":"EXPLICIT_REGION_NAME_ALIAS"},
        },
        "approval_provenance":{"status":"APPROVED","evidence_sha256":"5e6bd00416f180109751e422521d76910da8b491c62507c4d9836e6700c38c46"},
    }


def test_selector_returns_only_features_strictly_before_cutoff_and_target_day():
    cutoff=datetime(2026,11,16,tzinfo=timezone.utc)
    rows=[
        _row(match_date="2026-11-01"),
        _row(match_date="2026-11-02"),
        _row(match_date="2026-11-18"),
        _row(match_date="2026-11-03",eligibility="2026-11-17T00:00:00+00:00"),
        _row(team="11",match_date="2026-11-04"),
        _row(match_date="2026-11-05",eligibility="2026-11-15T00:00:00+00:00"),
    ]
    selected=_select_team_rows(
        rows,team_id="10",competition_id="20",cutoff_at=cutoff,
        target_date=date(2026,11,18),limit=5,
    )
    assert [row["match_date"] for row in selected]==["2026-11-05","2026-11-02","2026-11-01"]


def test_selector_is_competition_and_team_scoped():
    rows=[_row(),_row(team="11"),_row(comp="21")]
    selected=_select_team_rows(
        rows,team_id="10",competition_id="20",
        cutoff_at=datetime(2026,11,16,tzinfo=timezone.utc),
        target_date=date(2026,11,18),
    )
    assert len(selected)==1
    assert selected[0]["canonical_team_id"]=="10"


def test_feature_value_is_reduced_to_provenance_bound_metrics():
    value=_feature_value(_row())
    assert value["provider_match_id"]=="m-2026-11-01"
    assert value["metrics"]=={"xg":1.2}
    assert len(sha256(canonical_json_bytes(value)))==64
