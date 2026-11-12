import hashlib
import json

import pytest

from app.certification_metrics import recompute_raw_certification
from app.certification_evidence import EvidenceIntegrityError


ROLES = ("walk_forward_rows", "coverage_audit", "prospective_ledger", "odds_snapshots", "settlement_records", "model_manifest")


def _write_bundle(tmp_path, walk, paper, odds, settlements):
    payloads = {
        "walk_forward_rows": {"rows": walk},
        "coverage_audit": {"rights_status": "APPROVED_FOR_INTENDED_USE", "commercial_use_eligible": True, "approved_source_ids": ["source-a"], "rows": []},
        "prospective_ledger": {"rows": paper},
        "odds_snapshots": {"rows": odds},
        "settlement_records": {"rows": settlements},
        "source_responses": {"rows": []},
        "model_manifest": {"model_version": "model-v1", "code_commit": "a" * 40, "training_data_cutoff": "2025-12-31T00:00:00+00:00", "feature_schema_version": "features-v1", "calibration_versions": []},
    }
    entries = []
    for role, payload in payloads.items():
        path = tmp_path / f"{role}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        entries.append({"role": role, "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "purpose": "VELTRIX_VALUE_CERTIFICATION", "artifacts": entries}), encoding="utf-8")
    return manifest


def test_raw_certification_rejects_empty_unverifiable_evidence(tmp_path):
    manifest = _write_bundle(tmp_path, [], [], [], [])
    result = recompute_raw_certification(manifest)
    assert result["statistical_status"] == "RAW_EVIDENCE_INCOMPLETE"
    assert result["release_authorized"] is False
    assert all(result["markets"][market]["diagnostic_pass"] is False for market in result["markets"])


def test_raw_certification_rejects_probability_leakage_and_missing_fixture_provenance(tmp_path):
    walk = [{
        "fixture_id": "f1", "market": "1X2", "kickoff": "2026-01-01T18:00:00+00:00",
        "prediction_at": "2026-01-01T17:00:00+00:00", "features": [{"name": "form", "value": 0.5, "observed_at": "2026-01-01T18:00:00+00:00", "source_id": "source-a"}],
        "model_version": "model-v1", "model_commit": "a" * 40, "feature_schema_version": "features-v1", "split": "full", "outcome": "home",
        "model_probabilities": {"home": .6, "draw": .2, "away": .2},
        "bookmaker_probabilities": {"home": .5, "draw": .3, "away": .2},
    }]
    manifest = _write_bundle(tmp_path, walk, [], [], [])
    result = recompute_raw_certification(manifest, min_walk_forward=1, min_prospective=0, min_dates=0)
    assert result["markets"]["1X2"]["walk_forward_unique_fixtures"] == 0
    assert any("leakage" in reason for reason in result["markets"]["1X2"]["failures"])


def test_raw_certification_rejects_duplicate_paper_fixture_market(tmp_path):
    paper = [
        {"fixture_id": "f1", "market": "BTTS"},
        {"fixture_id": "f1", "market": "BTTS"},
    ]
    manifest = _write_bundle(tmp_path, [], paper, [], [])
    result = recompute_raw_certification(manifest, min_walk_forward=0, min_prospective=0, min_dates=0)
    assert any("duplicate fixture-market" in reason for reason in result["markets"]["BTTS"]["failures"])


def test_raw_certification_rejects_missing_settlement_and_odds_join(tmp_path):
    paper = [{
        "fixture_id": "f1", "market": "1X2", "kickoff": "2026-01-01T18:00:00+00:00",
        "odds_fetched_at": "2026-01-01T17:00:00+00:00", "quote_updated_at": "2026-01-01T16:55:00+00:00",
        "odds_snapshot_id": "missing", "settlement_id": "missing",
    }]
    manifest = _write_bundle(tmp_path, [], paper, [], [])
    result = recompute_raw_certification(manifest, min_walk_forward=0, min_prospective=0, min_dates=0)
    assert any("odds snapshot" in reason for reason in result["markets"]["1X2"]["failures"])



def test_raw_certification_recomputes_profit_and_rejects_fabricated_roi(tmp_path):
    kickoff = "2026-01-01T18:00:00+00:00"
    paper = [{
        "fixture_id": "fixture-1", "market": "1X2", "kickoff": kickoff,
        "odds_fetched_at": "2026-01-01T17:00:00+00:00",
        "quote_updated_at": "2026-01-01T16:55:00+00:00",
        "odds_snapshot_id": "quote-1", "settlement_id": "settlement-1",
        "bookmaker": "Book A", "decimal_odds": 2.5,
        "model_version": "model-v1", "model_commit": "a" * 40,
        "selection": "home", "outcome": "home", "won": True,
        "stake": 1.0, "fees": 0.0, "recorded_profit": 999999.0,
        "summary": {"net_roi": 999999.0, "roi_lower_95_ci": 999999.0},
    }]
    odds = [{
        "snapshot_id": "quote-1", "fixture_id": "fixture-1", "market": "1X2",
        "source_id": "source-a", "observed_at": "2026-01-01T17:00:00+00:00",
        "quote_updated_at": "2026-01-01T16:55:00+00:00", "kickoff": kickoff,
        "bookmaker": "Book A", "decimal_odds": 2.5,
    }]
    settlements = [{
        "settlement_id": "settlement-1", "fixture_id": "fixture-1",
        "source_id": "source-a", "settled_at": "2026-01-01T20:00:00+00:00",
        "status": "FT", "settlement_version": "settlement-v1", "home_goals": 2, "away_goals": 1,
    }]
    manifest = _write_bundle(tmp_path, [], paper, odds, settlements)
    result = recompute_raw_certification(manifest, min_walk_forward=0, min_prospective=0, min_dates=0)
    assert any("recorded net profit" in reason for reason in result["markets"]["1X2"]["failures"])
    assert result["markets"]["1X2"]["prospective_joined_selections"] == 0


def test_raw_certification_rejects_unapproved_rights(tmp_path):
    manifest = _write_bundle(tmp_path, [], [], [], [])
    payload = json.loads((tmp_path / "coverage_audit.json").read_text(encoding="utf-8"))
    payload["rights_status"] = "UNVERIFIED"
    (tmp_path / "coverage_audit.json").write_text(json.dumps(payload), encoding="utf-8")
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    for artifact in manifest_payload["artifacts"]:
        if artifact["role"] == "coverage_audit":
            artifact["sha256"] = hashlib.sha256((tmp_path / artifact["path"]).read_bytes()).hexdigest()
    manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="approved rights"):
        recompute_raw_certification(manifest)
