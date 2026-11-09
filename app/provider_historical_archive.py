"""Deterministic offline assembly of non-overlapping 5Dollar history batches."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, timedelta
from typing import Any

from app.provider_acquisition_artifact import (
    FIVEDOLLAR_HISTORY_COMPETITIONS,
    validate_fivedollar_history_batch_report,
)


class HistoricalArchiveError(ValueError):
    pass


def _hash(value: dict) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assemble_fivedollar_history_archive(*, reports: list[dict],
                                        target_start_date: str,
                                        target_end_date: str) -> dict:
    if not isinstance(reports, list) or not reports:
        raise HistoricalArchiveError("history_batch_reports_required")
    try:
        target_start = date.fromisoformat(target_start_date)
        target_end = date.fromisoformat(target_end_date)
    except (TypeError, ValueError):
        raise HistoricalArchiveError("archive_target_window_invalid") from None
    if target_end < target_start or (target_end - target_start).days > 89:
        raise HistoricalArchiveError("archive_target_window_must_be_one_to_ninety_days")

    validated = []
    for index, report in enumerate(reports):
        try:
            integrity = validate_fivedollar_history_batch_report(report)
        except ValueError as exc:
            raise HistoricalArchiveError(f"batch_integrity_failed:{index}:{exc}") from None
        window = report["window"]
        validated.append((date.fromisoformat(window["start_date"]),
                          date.fromisoformat(window["end_date"]), report, integrity))
    validated.sort(key=lambda item: (item[0], item[1]))

    cursor = target_start
    seen_ids: set[tuple[str, str, str]] = set()
    records = []
    batches = []
    page_totals = Counter()
    requests_total = 0

    for start, end, report, integrity in validated:
        if start != cursor:
            reason = "overlapping_batch_windows" if start < cursor else "historical_window_gap"
            raise HistoricalArchiveError(f"{reason}:{cursor.isoformat()}:{start.isoformat()}")
        if end > target_end:
            raise HistoricalArchiveError("batch_exceeds_archive_target_window")
        for record in report["records"]:
            identity = (record["provider"], record["competition_key"], record["source_id"])
            if identity in seen_ids:
                raise HistoricalArchiveError("duplicate_fixture_identity_across_batches")
            seen_ids.add(identity)
            records.append(record)
        budget = report["request_budget"]
        requests_total += budget["actual_requests"]
        page_totals.update(budget["pages_by_competition"])
        batches.append({
            "run_id": report["run_id"],
            "report_sha256": integrity["report_sha256"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "accepted_count": integrity["accepted_count"],
            "actual_requests": integrity["actual_requests"],
        })
        cursor = end + timedelta(days=1)

    if cursor != target_end + timedelta(days=1):
        raise HistoricalArchiveError(f"historical_window_incomplete:{cursor.isoformat()}")
    records.sort(key=lambda row: (
        row["kickoff_at"], row["competition_key"], row["source_id"]
    ))
    by_competition = Counter(row["competition_key"] for row in records)
    archive = {
        "schema_version": 1,
        "archive_type": "veltrix_fivedollar_historical_archive",
        "provider": "fivedollar",
        "competition_scope": sorted(FIVEDOLLAR_HISTORY_COMPETITIONS),
        "target_window": {
            "start_date": target_start.isoformat(),
            "end_date": target_end.isoformat(),
            "timezone": "Africa/Lagos",
            "semantics": "inclusive_calendar_dates",
        },
        "batches": batches,
        "request_budget": {
            "actual_requests": requests_total,
            "pages_by_competition": dict(sorted(page_totals.items())),
            "automatic_retries": 0,
        },
        "quality": {
            "coverage_complete": True,
            "batch_count": len(batches),
            "accepted_count": len(records),
            "accepted_by_competition": {
                key: by_competition.get(key, 0)
                for key in sorted(FIVEDOLLAR_HISTORY_COMPETITIONS)
            },
            "duplicate_fixture_identities": 0,
            "quarantined_rows": 0,
        },
        "records": records,
        "side_effects": {
            "provider_requests": 0,
            "database_writes": 0,
            "imports": 0,
            "checkpoints": 0,
            "canonical_merges": 0,
            "prediction_publications": 0,
        },
    }
    archive["archive_sha256"] = _hash(archive)
    return archive


def validate_fivedollar_history_archive(archive: Any) -> dict:
    if not isinstance(archive, dict) or archive.get("schema_version") != 1:
        raise HistoricalArchiveError("archive_schema_invalid")
    if archive.get("archive_type") != "veltrix_fivedollar_historical_archive":
        raise HistoricalArchiveError("archive_type_invalid")
    supplied = archive.get("archive_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64:
        raise HistoricalArchiveError("archive_hash_invalid")
    unhashed = dict(archive)
    unhashed.pop("archive_sha256", None)
    if _hash(unhashed) != supplied:
        raise HistoricalArchiveError("archive_hash_mismatch")
    if archive.get("provider") != "fivedollar" or archive.get("competition_scope") != sorted(FIVEDOLLAR_HISTORY_COMPETITIONS):
        raise HistoricalArchiveError("archive_provider_scope_invalid")
    target = archive.get("target_window")
    if not isinstance(target, dict) or target.get("timezone") != "Africa/Lagos":
        raise HistoricalArchiveError("archive_target_window_invalid")
    try:
        target_start = date.fromisoformat(target["start_date"])
        target_end = date.fromisoformat(target["end_date"])
    except (KeyError, TypeError, ValueError):
        raise HistoricalArchiveError("archive_target_dates_invalid") from None
    batches = archive.get("batches")
    records = archive.get("records")
    quality = archive.get("quality")
    if not isinstance(batches, list) or not batches or not isinstance(records, list) or not isinstance(quality, dict):
        raise HistoricalArchiveError("archive_content_invalid")
    cursor = target_start
    batch_hashes = set()
    for index, batch in enumerate(batches):
        if not isinstance(batch, dict):
            raise HistoricalArchiveError(f"archive_batch_invalid:{index}")
        try:
            start = date.fromisoformat(batch["start_date"])
            end = date.fromisoformat(batch["end_date"])
        except (KeyError, TypeError, ValueError):
            raise HistoricalArchiveError(f"archive_batch_dates_invalid:{index}") from None
        if start != cursor or end < start or (end - start).days > 6:
            raise HistoricalArchiveError(f"archive_batch_continuity_invalid:{index}")
        digest = batch.get("report_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or digest in batch_hashes:
            raise HistoricalArchiveError(f"archive_batch_hash_invalid:{index}")
        batch_hashes.add(digest)
        cursor = end + timedelta(days=1)
    if cursor != target_end + timedelta(days=1):
        raise HistoricalArchiveError("archive_coverage_incomplete")
    if quality.get("coverage_complete") is not True or quality.get("batch_count") != len(batches):
        raise HistoricalArchiveError("archive_quality_not_complete")
    if quality.get("accepted_count") != len(records) or quality.get("duplicate_fixture_identities") != 0 or quality.get("quarantined_rows") != 0:
        raise HistoricalArchiveError("archive_record_accounting_invalid")
    side_effects = archive.get("side_effects")
    if not isinstance(side_effects, dict) or any(side_effects.get(key) != 0 for key in (
        "provider_requests", "database_writes", "imports", "checkpoints",
        "canonical_merges", "prediction_publications",
    )):
        raise HistoricalArchiveError("archive_side_effect_boundary_invalid")
    return {
        "valid": True,
        "archive_sha256": supplied,
        "batch_count": len(batches),
        "accepted_count": len(records),
        "start_date": target_start.isoformat(),
        "end_date": target_end.isoformat(),
    }
