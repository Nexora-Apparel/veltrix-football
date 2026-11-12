import hashlib
import json

import pytest

from app.certification_metrics import recompute_raw_certification
from app.certification_evidence import EvidenceIntegrityError


ROLES = ("walk_forward_rows", "coverage_audit", "prospective_ledger", "odds_snapshots", "settlement_records", "model_manifest")


def _write_bundle(tmp_path, walk, paper, odds, settlements):
    payloads = {
        "walk_forward_rows": {"rows": walk},
        "coverage_audit": {"rows": []},
        "prospective_ledger": {"rows": paper},
        "odds_snapshots": {"rows": odds},
        "settlement_records": {"rows": settlements},
        "model_manifest": {"model_version": "model-v1"},
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
        "prediction_at": "2026-01-01T19:00:00+00:00", "feature_max_observed_at": "2026-01-01T19:00:00+00:00",
        "model_version": "model-v1", "split": "full", "outcome": "home",
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
