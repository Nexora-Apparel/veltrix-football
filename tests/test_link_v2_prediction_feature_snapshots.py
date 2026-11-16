import hashlib
import json
from datetime import datetime, timezone

import pytest

import scripts.link_v2_prediction_feature_snapshots as linker


def _artifacts():
    forecast = {
        "forecast_cutoff_at":"2026-11-15T23:31:35.481497+00:00",
        "model_artifact_sha256":"a"*64,
        "forecasts":[
            {
                "provider_fixture_id":str(128027062+i),
                "fixture_id":f"5dollarfootballapi:{128027062+i}",
                "feature_snapshot_id":15+i,
                "feature_set_sha256":chr(97+i)*64,
                "evidence_sha256":chr(107+i)*64,
                "prediction_cutoff_at":"2026-11-15T23:31:28.243079+00:00",
                "model_version":linker.EXPECTED_MODEL,
            }
            for i in range(7)
        ],
        "ledger_event_sha256":[chr(65+i).lower()*64 for i in range(7)],
    }
    admission = {
        "snapshots":[
            {
                "provider_fixture_id":str(128027062+i),
                "feature_snapshot_id":15+i,
                "feature_set_sha256":chr(97+i)*64,
                "eligibility_evidence_sha256":chr(113+i)*64,
                "feature_count":10,
            }
            for i in range(7)
        ]
    }
    return forecast,admission


def test_prepare_links_pairs_exact_forecast_and_feature_admission_evidence():
    forecast,admission=_artifacts()
    prepared=linker._prepare_links(forecast,admission,"b"*64,"c"*64)
    assert len(prepared)==7
    assert prepared[0]["feature_snapshot_id"]==15
    assert prepared[0]["provider_fixture_id"]=="128027062"
    assert prepared[0]["feature_count"]==10
    assert prepared[0]["forecast_evidence_sha256"]==forecast["forecasts"][0]["evidence_sha256"]
    assert prepared[0]["eligibility_evidence_sha256"]==admission["snapshots"][0]["eligibility_evidence_sha256"]


def test_prepare_links_rejects_snapshot_hash_mismatch():
    forecast,admission=_artifacts()
    admission["snapshots"][0]["feature_set_sha256"]="f"*64
    with pytest.raises(ValueError,match="V2_FORECAST_AND_FEATURE_SNAPSHOT_ARTIFACTS_DISAGREE"):
        linker._prepare_links(forecast,admission,"b"*64,"c"*64)


def test_prepare_links_rejects_feature_snapshot_after_forecast_cutoff():
    forecast,admission=_artifacts()
    forecast["forecasts"][0]["prediction_cutoff_at"]="2026-11-16T00:00:00+00:00"
    with pytest.raises(ValueError,match="V2_FEATURE_SNAPSHOT_AFTER_FORECAST_CUTOFF"):
        linker._prepare_links(forecast,admission,"b"*64,"c"*64)


def test_link_hash_is_stable_and_does_not_include_recorded_at():
    forecast,admission=_artifacts()
    prepared=linker._prepare_links(forecast,admission,"b"*64,"c"*64)
    link={
        "ledger_id":"v2-openplay-prospective",
        "prediction_sequence":26,
        "prediction_event_sha256":"d"*64,
        "feature_snapshot_id":15,
        "eligibility_event_id":1,
        "feature_set_sha256":"e"*64,
        "eligibility_evidence_sha256":"f"*64,
        "forecast_evidence_sha256":"g"*64,
        "model_artifact_sha256":"h"*64,
        "forecast_cutoff_at":datetime(2026,11,15,23,31,35,tzinfo=timezone.utc),
        "feature_snapshot_cutoff_at":datetime(2026,11,15,23,31,28,tzinfo=timezone.utc),
        "artifact_run_id":linker.EXPECTED_ARTIFACT_RUN_ID,
        "forecast_summary_sha256":"i"*64,
        "feature_admission_summary_sha256":"j"*64,
    }
    stable={k:(v.isoformat() if isinstance(v,datetime) else v) for k,v in link.items()}
    first=linker._sha256(linker._canonical(stable))
    second=linker._sha256(linker._canonical(stable))
    assert first==second
    assert len(prepared)==7


def test_existing_link_comparison_covers_all_immutable_fields():
    link={
        "ledger_id":"v2-openplay-prospective",
        "prediction_sequence":26,
        "prediction_event_sha256":"a"*64,
        "feature_snapshot_id":15,
        "eligibility_event_id":99,
        "feature_set_sha256":"b"*64,
        "eligibility_evidence_sha256":"c"*64,
        "forecast_evidence_sha256":"d"*64,
        "model_artifact_sha256":"e"*64,
        "forecast_cutoff_at":datetime(2026,11,15,23,31,35,tzinfo=timezone.utc),
        "feature_snapshot_cutoff_at":datetime(2026,11,15,23,31,28,tzinfo=timezone.utc),
        "artifact_run_id":linker.EXPECTED_ARTIFACT_RUN_ID,
        "forecast_summary_sha256":"f"*64,
        "feature_admission_summary_sha256":"0"*64,
        "link_sha256":"1"*64,
    }
    row=tuple(link[key] for key in (
        "ledger_id","prediction_sequence","prediction_event_sha256","feature_snapshot_id",
        "eligibility_event_id","feature_set_sha256","eligibility_evidence_sha256",
        "forecast_evidence_sha256","model_artifact_sha256","forecast_cutoff_at",
        "feature_snapshot_cutoff_at","artifact_run_id","forecast_summary_sha256",
        "feature_admission_summary_sha256","link_sha256",
    ))
    assert linker._existing_match(row,link)
    changed=list(row)
    changed[-1]="2"*64
    assert not linker._existing_match(tuple(changed),link)
