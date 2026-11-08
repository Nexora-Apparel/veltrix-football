"""Exact source-manifest reconciliation for lossless historical imports."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from collections import Counter
from typing import Iterable

from veltrix_v2.history.batch_import import HistoryImportBatchReport


@dataclass(frozen=True, slots=True)
class HistoricalImportReconciliation:
    complete: bool
    expected_count: int
    reported_count: int
    imported_count: int
    rejected_count: int
    quarantined_count: int
    missing_source_record_ids: tuple[str, ...]
    unexpected_source_record_ids: tuple[str, ...]
    duplicate_outcome_source_record_ids: tuple[str, ...]
    manifest_sha256: str
    reason_code: str


def reconcile_history_import(
    expected_source_record_ids: Iterable[str],
    batch_reports: Iterable[HistoryImportBatchReport],
) -> HistoricalImportReconciliation:
    """Prove every expected source record has exactly one explicit terminal outcome.

    Rejected and quarantined records are accounted for, not silently discarded.
    This verifies accounting completeness, not that all records were importable.
    """
    expected=list(expected_source_record_ids)
    if any(not value or not value.strip() for value in expected):
        raise ValueError("EXPECTED_SOURCE_RECORD_IDS_MUST_BE_NONEMPTY")
    if len(set(expected)) != len(expected):
        raise ValueError("EXPECTED_SOURCE_RECORD_IDS_MUST_BE_UNIQUE")

    outcomes=[]
    imported=rejected=quarantined=reported=0
    for report in batch_reports:
        if report.total_candidates != len(report.rows):
            raise ValueError("BATCH_REPORT_ROW_COUNT_MISMATCH")
        if report.imported_count + report.rejected_count + report.quarantined_count != report.total_candidates:
            raise ValueError("BATCH_REPORT_TERMINAL_COUNTS_MISMATCH")
        for row in report.rows:
            if row.status not in {"IMPORTED","REJECTED","QUARANTINED"}:
                raise ValueError("NONTERMINAL_HISTORY_IMPORT_OUTCOME")
            outcomes.append(row.source_record_id)
            reported+=1
            if row.status=="IMPORTED": imported+=1
            elif row.status=="REJECTED": rejected+=1
            else: quarantined+=1

    counts=Counter(outcomes)
    expected_set=set(expected)
    outcome_set=set(outcomes)
    missing=tuple(sorted(expected_set-outcome_set))
    unexpected=tuple(sorted(outcome_set-expected_set))
    duplicates=tuple(sorted(value for value,count in counts.items() if count>1))
    complete=not (missing or unexpected or duplicates)
    manifest=sha256("\n".join(sorted(expected)).encode("utf-8")).hexdigest()
    reason=("SOURCE_MANIFEST_FULLY_ACCOUNTED" if complete
            else "SOURCE_MANIFEST_RECONCILIATION_FAILED")
    return HistoricalImportReconciliation(
        complete,len(expected),reported,imported,rejected,quarantined,
        missing,unexpected,duplicates,manifest,reason,
    )
