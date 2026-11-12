import base64
import hashlib
import json

import pytest

from app.certification_metrics import recompute_raw_certification
from app.certification_evidence import EvidenceIntegrityError


ROLES = ("walk_forward_rows", "coverage_audit", "prospective_ledger", "odds_snapshots", "settlement_records", "source_responses", "model_manifest")


def _write_bundle(tmp_path, walk, paper, odds, settlements, source_responses=None):
    payloads = {
        "walk_forward_rows": {"rows": walk},
        "coverage_audit": {"rights_status": "APPROVED_FOR_INTENDED_USE", "commercial_use_eligible": True, "approved_source_ids": ["source-a"], "rows": []},
        "prospective_ledger": {"rows": paper},
        "odds_snapshots": {"rows": odds},
        "settlement_records": {"rows": settlements},
        "source_responses": {"rows": source_responses or []},
        "model_manifest": {"model_version": "model-v1", "code_commit": "a" * 40, "training_data_cutoff": "2025-12-31T00:00:00+00:00", "feature_schema_version": "features-v1", "calibration_versions": [], "walk_forward_folds": [{"fold_id": "fold-1", "order": 1, "training_data_cutoff": "2025-12-31T00:00:00+00:00", "test_start": "2026-01-01T00:00:00+00:00", "test_end": "2026-01-31T23:59:59+00:00"}]},
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
        "source_id": "source-a", "source_response_id": "quote-response",
        "source_pointer": "/events/0",
        "observed_at": "2026-01-01T17:00:00+00:00",
        "quote_updated_at": "2026-01-01T16:55:00+00:00", "kickoff": kickoff,
        "bookmaker": "Book A", "decimal_odds": 2.5,
    }]
    settlements = [{
        "settlement_id": "settlement-1", "fixture_id": "fixture-1",
        "source_id": "source-a", "source_response_id": "settlement-response",
        "source_pointer": "/events/0",
        "settled_at": "2026-01-01T20:00:00+00:00",
        "status": "FT", "settlement_version": "settlement-v1", "home_goals": 2, "away_goals": 1,
    }]
    quote_body = json.dumps({"events": [{
        "fixture_id": "fixture-1", "market": "1X2", "bookmaker": "Book A",
        "kickoff": kickoff, "decimal_odds": 2.5,
        "observed_at": "2026-01-01T17:00:00+00:00",
        "quote_updated_at": "2026-01-01T16:55:00+00:00",
    }]}).encode("utf-8")
    settlement_body = json.dumps({"events": [{
        "fixture_id": "fixture-1", "status": "FT", "home_goals": 2, "away_goals": 1,
        "settled_at": "2026-01-01T20:00:00+00:00", "settlement_version": "settlement-v1",
    }]}).encode("utf-8")
    quote_encoded = base64.b64encode(quote_body).decode("ascii")
    settlement_encoded = base64.b64encode(settlement_body).decode("ascii")
    quote_request = {"method": "GET", "endpoint": "/v1/odds"}
    settlement_request = {"method": "GET", "endpoint": "/v1/results"}
    fingerprint = lambda item: hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    source_responses = [
        {
            "response_id": "quote-response", "source_id": "source-a",
            "fetched_at": "2026-01-01T17:00:00+00:00", "http_status": 200,
            "request_descriptor": quote_request, "request_fingerprint": fingerprint(quote_request),
            "response_sha256": hashlib.sha256(quote_body).hexdigest(), "body_base64": quote_encoded,
        },
        {
            "response_id": "settlement-response", "source_id": "source-a",
            "fetched_at": "2026-01-01T20:05:00+00:00", "http_status": 200,
            "request_descriptor": settlement_request, "request_fingerprint": fingerprint(settlement_request),
            "response_sha256": hashlib.sha256(settlement_body).hexdigest(), "body_base64": settlement_encoded,
        },
    ]
    manifest = _write_bundle(tmp_path, [], paper, odds, settlements, source_responses)
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



def test_raw_certification_rejects_altered_provider_response_bytes(tmp_path):
    body = base64.b64encode(b'{"events":[]}').decode("ascii")
    response = {
        "response_id": "raw-1", "source_id": "source-a",
        "fetched_at": "2026-01-01T17:00:00+00:00", "http_status": 200,
        "request_descriptor": {"method": "GET", "endpoint": "/v1/fixtures"},
        "request_fingerprint": hashlib.sha256(json.dumps({"method": "GET", "endpoint": "/v1/fixtures"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "response_sha256": hashlib.sha256(base64.b64decode(body)).hexdigest(),
        "body_base64": body,
    }
    manifest = _write_bundle(tmp_path, [], [], [], [], [response])
    response["body_base64"] = base64.b64encode(b'{"events":[{"tampered":true}]}').decode("ascii")
    (tmp_path / "source_responses.json").write_text(json.dumps({"rows": [response]}), encoding="utf-8")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for artifact in payload["artifacts"]:
        if artifact["role"] == "source_responses":
            artifact["sha256"] = hashlib.sha256((tmp_path / artifact["path"]).read_bytes()).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="response body SHA-256 mismatch"):
        recompute_raw_certification(manifest)



def test_source_request_fingerprint_rejects_credentials():
    from app.certification_metrics import _request_fingerprint

    with pytest.raises(EvidenceIntegrityError, match="credentials"):
        _request_fingerprint({
            "method": "GET", "endpoint": "/v1/results",
            "headers": {"Authorization": "Bearer do-not-store"},
        })



def test_raw_certification_rejects_overlapping_walk_forward_folds(tmp_path):
    manifest = _write_bundle(tmp_path, [], [], [], [])
    model_path = tmp_path / "model_manifest.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model["walk_forward_folds"] = [
        {
            "fold_id": "fold-1", "order": 1,
            "training_data_cutoff": "2025-12-31T00:00:00+00:00",
            "test_start": "2026-01-01T00:00:00+00:00",
            "test_end": "2026-01-10T23:59:59+00:00",
        },
        {
            "fold_id": "fold-2", "order": 2,
            "training_data_cutoff": "2025-12-31T00:00:00+00:00",
            "test_start": "2026-01-10T00:00:00+00:00",
            "test_end": "2026-01-20T23:59:59+00:00",
        },
    ]
    model_path.write_text(json.dumps(model), encoding="utf-8")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    for artifact in payload["artifacts"]:
        if artifact["role"] == "model_manifest":
            artifact["sha256"] = hashlib.sha256(model_path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError, match="overlap"):
        recompute_raw_certification(manifest)


def test_match_date_clusters_use_west_africa_time():
    from app.certification_metrics import _match_date

    assert _match_date("2026-01-01T23:30:00+00:00") == "2026-01-02"



def test_walk_forward_bookmaker_benchmark_requires_exact_raw_quote():
    from datetime import datetime
    from app.certification_metrics import _verify_walk_forward_bookmaker_odds

    raw = {
        "fixture_id": "fixture-1", "bookmaker": "Book A",
        "kickoff": "2026-01-01T18:00:00+00:00",
        "observed_at": "2026-01-01T17:00:00+00:00",
        "quote_updated_at": "2026-01-01T16:55:00+00:00",
        "home": 2.5, "draw": 3.2, "away": 2.9,
    }
    row = {
        "fixture_id": "fixture-1", "bookmaker": "Book A",
        "kickoff": raw["kickoff"], "prediction_at": "2026-01-01T17:10:00+00:00",
        "bookmaker_odds": {"home": 2.5, "draw": 3.2, "away": 2.9},
        "bookmaker_odds_source_id": "source-a",
        "bookmaker_odds_source_response_id": "benchmark-response",
        "bookmaker_odds_source_pointer": "/events/0",
        "bookmaker_odds_observed_at": raw["observed_at"],
        "bookmaker_odds_updated_at": raw["quote_updated_at"],
    }
    responses = {"benchmark-response": {
        "source_id": "source-a",
        "_fetched_at": datetime.fromisoformat(raw["observed_at"]),
        "_body_json": {"events": [raw]},
    }}
    _verify_walk_forward_bookmaker_odds(row, responses, {"source-a"})

    forged = dict(row)
    forged["bookmaker_odds"] = {"home": 2.51, "draw": 3.2, "away": 2.9}
    with pytest.raises(EvidenceIntegrityError, match="does not match home odds"):
        _verify_walk_forward_bookmaker_odds(forged, responses, {"source-a"})

    post_kickoff = dict(row)
    post_kickoff["bookmaker_odds_observed_at"] = "2026-01-01T18:01:00+00:00"
    responses["benchmark-response"]["_fetched_at"] = datetime.fromisoformat(post_kickoff["bookmaker_odds_observed_at"])
    raw["observed_at"] = post_kickoff["bookmaker_odds_observed_at"]
    with pytest.raises(EvidenceIntegrityError, match="point-in-time"):
        _verify_walk_forward_bookmaker_odds(post_kickoff, responses, {"source-a"})



def test_json_pointer_rejects_noncanonical_array_index():
    from app.certification_metrics import _json_pointer

    with pytest.raises(EvidenceIntegrityError, match="does not resolve"):
        _json_pointer({"events": [{"fixture_id": "f1"}]}, "/events/00")


def test_walk_forward_bookmaker_benchmark_supports_explicit_provider_field_mapping():
    from datetime import datetime
    from app.certification_metrics import _verify_walk_forward_bookmaker_odds

    raw = {
        "match_id": "fixture-2", "operator": "Book B",
        "start_time": "2026-01-02T18:00:00+00:00",
        "captured": "2026-01-02T17:00:00+00:00",
        "last_change": "2026-01-02T16:58:00+00:00",
        "h": 2.2, "d": 3.4, "a": 3.1,
    }
    row = {
        "fixture_id": "fixture-2", "bookmaker": "Book B",
        "kickoff": raw["start_time"], "prediction_at": "2026-01-02T17:05:00+00:00",
        "bookmaker_odds": {"home": 2.2, "draw": 3.4, "away": 3.1},
        "bookmaker_odds_source_id": "source-a",
        "bookmaker_odds_source_response_id": "benchmark-response",
        "bookmaker_odds_source_pointer": "/matches/0",
        "bookmaker_odds_observed_at": raw["captured"],
        "bookmaker_odds_updated_at": raw["last_change"],
        "bookmaker_odds_metadata_field_map": {
            "fixture_id": "match_id", "bookmaker": "operator",
            "kickoff": "start_time", "observed_at": "captured",
            "quote_updated_at": "last_change",
        },
        "bookmaker_odds_field_map": {"home": "h", "draw": "d", "away": "a"},
    }
    responses = {"benchmark-response": {
        "source_id": "source-a",
        "_fetched_at": datetime.fromisoformat(raw["captured"]),
        "_body_json": {"matches": [raw]},
    }}
    _verify_walk_forward_bookmaker_odds(row, responses, {"source-a"})
