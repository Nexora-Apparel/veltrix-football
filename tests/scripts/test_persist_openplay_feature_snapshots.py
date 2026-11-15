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
