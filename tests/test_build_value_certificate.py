import hashlib
import json

from scripts.build_value_certificate import build


def test_certificate_builder_fails_closed_without_paper_ledger(tmp_path):
    backtest = {
        "live_pipeline": {
            "goal_markets": {"rolling_origin_calibration": {"markets": {}}},
            "historical_odds_subset": {"models_compared_on_same_matches": {}},
        },
        "recent_holdout": {"historical_odds_subset": {"models_compared_on_same_matches": {}}},
        "dataset_provenance": {"rows_loaded": 1234},
    }
    backtest_path = tmp_path / "backtest.json"
    backtest_path.write_text(json.dumps(backtest), encoding="utf-8")
    report_path = tmp_path / "daily.json"
    report_path.write_text(json.dumps({"predictions": []}), encoding="utf-8")
    certificate_path = tmp_path / "certificate.json"

    certificate = build(
        str(report_path),
        str(tmp_path / "missing-ledger.json"),
        str(certificate_path),
        backtest_path=str(backtest_path),
    )

    assert certificate["status"] == "LOCKED_SOURCE_ATTESTATION_REQUIRED"
    assert certificate["approved_markets"] == []
    assert certificate["alerts_enabled"] is False
    assert certificate["paper_ledger_present"] is False
    assert json.loads(certificate_path.read_text(encoding="utf-8"))["status"] == certificate["status"]
    updated_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert updated_report["value_validation_certificate"]["status"] == certificate["status"]
    assert updated_report["value_bet_screen"]["alerts_enabled"] is False



def test_certificate_builder_attaches_raw_audit_but_never_unlocks(tmp_path):
    roles = {
        "walk_forward_rows": {"rows": []},
        "coverage_audit": {
            "rights_status": "APPROVED_FOR_INTENDED_USE",
            "commercial_use_eligible": True,
            "approved_source_ids": ["licensed-source"],
        },
        "prospective_ledger": {"rows": []},
        "odds_snapshots": {"rows": []},
        "settlement_records": {"rows": []},
        "model_manifest": {
            "model_version": "model-v1",
            "code_commit": "a" * 40,
            "training_data_cutoff": "2025-01-01T00:00:00+00:00",
            "feature_schema_version": "features-v1",
            "calibration_versions": [],
        },
    }
    artifacts = []
    for role, payload in roles.items():
        path = tmp_path / f"{role}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        artifacts.append({
            "role": role,
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "purpose": "VELTRIX_VALUE_CERTIFICATION",
        "artifacts": artifacts,
    }), encoding="utf-8")

    backtest_path = tmp_path / "backtest.json"
    backtest_path.write_text(json.dumps({"live_pipeline": {}, "dataset_provenance": {}}), encoding="utf-8")
    report_path = tmp_path / "daily.json"
    report_path.write_text(json.dumps({"predictions": []}), encoding="utf-8")
    certificate = build(
        str(report_path),
        str(tmp_path / "missing-ledger.json"),
        str(tmp_path / "certificate.json"),
        backtest_path=str(backtest_path),
        evidence_manifest_path=str(manifest),
    )

    assert certificate["status"] == "LOCKED_SOURCE_ATTESTATION_REQUIRED"
    assert certificate["approved_markets"] == []
    assert certificate["alerts_enabled"] is False
    assert certificate["raw_evidence_audit"]["release_authorized"] is False
    assert certificate["raw_evidence_audit"]["statistical_status"] == "RAW_EVIDENCE_INCOMPLETE"
