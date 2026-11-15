from __future__ import annotations

from scripts.veltrix_v2.import_openplay_staging import (
    APPROVAL_ID, AUTHORIZATION_SHA256, CSV_FILES, PARQUET_ROWS, TIMESTAMP_DICTIONARY_SHA256,\n    TIMESTAMP_EVIDENCE_ID, build_manifest, parse_scraped_at_utc,
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
        "scrape_timestamp_audit": {\n            "temporal_status": "CAPTURE_TIMESTAMP_CANDIDATE",\n            "data_dictionary_documented_definition_verified": True,\n            "timestamp_guarantee_evidence_id": TIMESTAMP_EVIDENCE_ID,\n            "timestamp_guarantee_evidence_sha256": TIMESTAMP_DICTIONARY_SHA256,\n            "match_rows": PARQUET_ROWS["matches.parquet"],\n            "non_null_scraped_at": PARQUET_ROWS["matches.parquet"],\n            "parseable_scraped_at": PARQUET_ROWS["matches.parquet"],\n            "unique_match_ids": PARQUET_ROWS["matches.parquet"],\n            "safely_after_match_date": PARQUET_ROWS["matches.parquet"],\n            "not_future_scrape_timestamps": PARQUET_ROWS["matches.parquet"],\n            "first_page_saved_at_utc": "2026-10-29 20:44:32+00:00",\n            "last_page_saved_at_utc": "2026-11-03 04:14:37+00:00",\n            "data_dictionary_url": "https://raw.githubusercontent.com/nlbair/openplay/ac0bd9aff52016066433ebebf818bec4278fcf54/DATA_DICTIONARY.md",\n        },\n        "authorization_evidence": {
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
    assert manifest["tag_commit"] == "ac0bd9aff52016066433ebebf818bec4278fcf54"\n    assert manifest["scrape_timestamp_evidence"]["timestamp_guarantee_evidence_sha256"] == TIMESTAMP_DICTIONARY_SHA256\n    assert manifest["scrape_timestamp_evidence"]["scope"].startswith("prospective cutoffs")


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


def test_openplay_scrape_timestamp_parser_uses_documented_utc_semantics():
    parsed = parse_scraped_at_utc("2026-10-29 20:44:32")
    assert parsed.isoformat() == "2026-10-29T20:44:32+00:00"
    assert parse_scraped_at_utc("2026-10-29T21:44:32+01:00") == parsed


def test_manifest_rejects_incomplete_scrape_timestamp_evidence():
    report = qualified_report()
    report["scrape_timestamp_audit"]["not_future_scrape_timestamps"] -= 1
    try:
        build_manifest(report)
    except RuntimeError as exc:
        assert "OPENPLAY_SCRAPE_TIMESTAMP_EVIDENCE_MISMATCH" in str(exc)
    else:
        raise AssertionError("incomplete scrape timestamp evidence must be rejected")
