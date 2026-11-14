from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

import pytest

from veltrix_v2.evaluation.publication_certification import (
    CERTIFICATION_MANIFEST_SCHEMA,
    build_publication_verifier,
    verify_publication_authorization,
)
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity


def make_report():
    return bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "publication-gate-2026-11-14",
        "as_of_date": "2026-11-14",
        "release_mode": "RESTRICTED_PUBLIC",
        "predictions": [{
            "fixture_id": "fixture-1",
            "competition_id": "competition-1",
            "model_build_id": "model-build-7",
            "publication_status": "PUBLISHED",
            "certified_markets": ["1X2", "BTTS"],
        }],
    })


def certification(market):
    record = {
        "status": "CERTIFIED",
        "competition_id": "competition-1",
        "market": market,
        "model_build_id": "model-build-7",
        "walk_forward_matches": 1200,
        "prospective_settled_selections": 340,
        "distinct_dates": 96,
        "timestamped_odds_coverage": 0.995,
        "net_roi": 0.035,
        "roi_ci95_lower": 0.008,
        "rights_approval_id": "rights-approval-17",
        "rights_evaluated_at": "2026-11-14T10:00:00+00:00",
        "evidence_uri": f"s3://veltrix-evidence/{market}.json",
        "evidence_sha256": hashlib.sha256(f"{market}-evidence".encode()).hexdigest(),
        "rights_evidence_uri": "s3://veltrix-evidence/rights.json",
        "rights_evidence_sha256": hashlib.sha256(b"rights-evidence").hexdigest(),
    }
    if market == "1X2":
        record.update({
            "brier_score": 0.19,
            "bookmaker_brier_score": 0.21,
            "log_loss": 0.58,
            "bookmaker_log_loss": 0.62,
        })
    return record


def make_manifest(report, records=None, **overrides):
    manifest = {
        "manifest_schema": CERTIFICATION_MANIFEST_SCHEMA,
        "report_id": report["report_id"],
        "report_sha256": report["report_sha256"],
        "certifications": records if records is not None else [
            certification("1X2"),
            certification("BTTS"),
        ],
    }
    manifest.update(overrides)
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()


def attestation_ok(raw, digest):
    return hashlib.sha256(raw).hexdigest() == digest


def rights_ok(record):
    return (
        record.get("rights_approval_id") == "rights-approval-17"
        and record.get("rights_evidence_sha256") == hashlib.sha256(b"rights-evidence").hexdigest()
    )


def evidence_reader(uri):
    if uri.startswith("s3://veltrix-evidence/") and uri.endswith("/rights.json"):
        return b"rights-evidence"
    if uri.startswith("s3://veltrix-evidence/"):
        market = uri.rsplit("/", 1)[-1].removesuffix(".json")
        return f"{market}-evidence".encode()
    return b""


def test_valid_manifest_and_exact_report_identity_authorize_certified_markets():
    report = make_report()
    raw = make_manifest(report)
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is True
    identity = __import__("veltrix_v2.reporting.report_identity", fromlist=["verify_report_identity"]).verify_report_identity(report)
    verifier = build_publication_verifier(raw, attestation_ok, rights_ok, evidence_reader)
    assert verifier(report, identity) is True


@pytest.mark.parametrize(("field", "value"), [
    ("walk_forward_matches", 999),
    ("prospective_settled_selections", 299),
    ("distinct_dates", 89),
    ("timestamped_odds_coverage", 0.979),
    ("net_roi", 0.0),
    ("roi_ci95_lower", 0.0),
    ("status", "SHADOW_ONLY"),
])
def test_any_failed_market_gate_denies_publication(field, value):
    report = make_report()
    one_x_two = certification("1X2")
    one_x_two[field] = value
    raw = make_manifest(report, [one_x_two, certification("BTTS")])
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is False


@pytest.mark.parametrize(("field", "value"), [
    ("brier_score", 0.21),
    ("log_loss", 0.62),
])
def test_1x2_must_beat_both_bookmaker_baselines(field, value):
    report = make_report()
    one_x_two = certification("1X2")
    one_x_two[field] = value
    raw = make_manifest(report, [one_x_two, certification("BTTS")])
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is False


def test_report_and_manifest_identity_must_match_exactly():
    report = make_report()
    assert verify_publication_authorization(
        report,
        make_manifest(report, report_id="different-report"),
        attestation_ok,
        rights_ok,
        evidence_reader,
    ) is False
    assert verify_publication_authorization(
        report,
        make_manifest(report, report_sha256="0" * 64),
        attestation_ok,
        rights_ok,
        evidence_reader,
    ) is False


def test_attestation_and_rights_verifiers_are_mandatory_and_fail_closed():
    report = make_report()
    raw = make_manifest(report)
    assert verify_publication_authorization(report, raw, lambda *_: False, rights_ok, evidence_reader) is False
    assert verify_publication_authorization(report, raw, attestation_ok, lambda *_: False, evidence_reader) is False
    assert verify_publication_authorization(report, raw, None, rights_ok, evidence_reader) is False
    assert verify_publication_authorization(report, raw, attestation_ok, None, evidence_reader) is False


def test_wrong_model_build_or_missing_market_evidence_denies_publication():
    report = make_report()
    wrong_build = certification("BTTS")
    wrong_build["model_build_id"] = "different-model"
    raw = make_manifest(report, [certification("1X2"), wrong_build])
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is False

    raw = make_manifest(report, [certification("1X2")])
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is False


def test_duplicate_certification_records_are_rejected():
    report = make_report()
    raw = make_manifest(report, [
        certification("1X2"),
        certification("1X2"),
        certification("BTTS"),
    ])
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is False


def test_shadow_or_unpublished_report_is_never_authorized():
    report = make_report()
    report["release_mode"] = "INTERNAL_SHADOW"
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    raw = make_manifest(report)
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is False

    report = make_report()
    report["predictions"][0]["publication_status"] = "SHADOW_ONLY"
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    raw = make_manifest(report)
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is False


def test_rights_evaluation_timestamp_must_be_timezone_aware():
    report = make_report()
    btts = certification("BTTS")
    btts["rights_evaluated_at"] = "2026-11-14T10:00:00"
    raw = make_manifest(report, [certification("1X2"), btts])
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is False


def test_tampered_report_hash_and_malformed_manifest_fail_closed():
    report = make_report()
    raw = make_manifest(report)
    tampered = deepcopy(report)
    tampered["predictions"][0]["model_build_id"] = "tampered"
    assert verify_publication_authorization(tampered, raw, attestation_ok, rights_ok, evidence_reader) is False
    assert verify_publication_authorization(report, b"not-json", attestation_ok, rights_ok, evidence_reader) is False


def test_over_under_market_uses_common_sample_roi_and_odds_gates_without_1x2_baseline():
    report = make_report()
    report["predictions"][0]["certified_markets"] = ["OVER_UNDER"]
    report = bind_report_identity({key: value for key, value in report.items() if key != "report_sha256"})
    raw = make_manifest(report, [certification("OVER_UNDER")])
    assert verify_publication_authorization(report, raw, attestation_ok, rights_ok, evidence_reader) is True
