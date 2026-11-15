from __future__ import annotations

from scripts.veltrix_v2.import_openplay_staging import (
    APPROVAL_ID, AUTHORIZATION_SHA256, CSV_FILES, PARQUET_ROWS, build_manifest,
)


def qualified_report():
    return {
        "status": "PASS_NONCOMMERCIAL_SOURCE_QUALIFIED",
        "assets": {
            name: {"sha256": "a" * 64, "bytes": 10, "release_asset_id": index}
            for index, name in enumerate(sorted(set(PARQUET_ROWS) | set(CSV_FILES)), 1)
        },
        "parquet_tables": {
            name: {"rows": rows} for name, rows in PARQUET_ROWS.items()
        },
        "authorization_evidence": {
            "status": "USER_CONFIRMED_NONCOMMERCIAL_AUTHORIZATION",
            "sha256": AUTHORIZATION_SHA256,
            "commercial_use_allowed": False,
            "raw_redistribution_allowed": False,
        },
    }


def test_manifest_covers_all_pinned_release_assets_and_noncommercial_rights():
    manifest = build_manifest(qualified_report())
    assert len(manifest["assets"]) == 15
    assert manifest["authorization_approval_id"] == APPROVAL_ID
    assert manifest["commercial_use_allowed"] is False
    assert manifest["monetisation_prohibited"] is True
    assert manifest["tag_commit"] == "ac0bd9aff52016066433ebebf818bec4278fcf54"


def test_manifest_rejects_unqualified_or_rights_mismatched_report():
    report = qualified_report()
    report["status"] = "REVIEW_REQUIRED"
    try:
        build_manifest(report)
    except RuntimeError as exc:
        assert "OPENPLAY_QUALIFICATION_NOT_PASSED" in str(exc)
    else:
        raise AssertionError("unqualified release must be rejected")

    report = qualified_report()
    report["authorization_evidence"]["commercial_use_allowed"] = True
    try:
        build_manifest(report)
    except RuntimeError as exc:
        assert "OPENPLAY_AUTHORIZATION_EVIDENCE_MISMATCH" in str(exc)
    else:
        raise AssertionError("commercial rights must remain disabled")


def test_manifest_rejects_missing_release_assets_and_wrong_row_counts():
    report = qualified_report()
    report["assets"].pop("shots.parquet")
    try:
        build_manifest(report)
    except RuntimeError as exc:
        assert "OPENPLAY_ASSET_SET_MISMATCH" in str(exc)
    else:
        raise AssertionError("missing asset must be rejected")

    report = qualified_report()
    report["parquet_tables"]["shots.parquet"]["rows"] -= 1
    try:
        build_manifest(report)
    except RuntimeError as exc:
        assert "OPENPLAY_PARQUET_ROW_COUNT_MISMATCH" in str(exc)
    else:
        raise AssertionError("wrong row count must be rejected")
