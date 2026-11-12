"""Bounded read-only history assessment and lossless manifest reconciliation."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timezone
from hashlib import sha256
from typing import Iterable, Sequence

from veltrix_v2.data.contracts import (
    FixtureImportDecision, HistoricalFixture, ImportBatchReport,
    ImportOutcomeStatus, SourceApproval,
)
from veltrix_v2.data.rights import evaluate_fixture_import


@dataclass(frozen=True, slots=True)
class HistoryBatchAssessment:
    report: ImportBatchReport
    decisions: tuple[FixtureImportDecision, ...]
    fixture_ids: tuple[str, ...]


def assess_history_batch(
    fixtures: Sequence[HistoricalFixture],
    approval: SourceApproval,
    *,
    evaluated_at_utc,
    request_count: int,
    request_budget: int,
) -> HistoryBatchAssessment:
    if request_count < 0 or request_budget < 1 or request_count > request_budget:
        raise ValueError("HISTORY_REQUEST_BUDGET_INVALID")
    fixture_ids = [row.provider_fixture_id for row in fixtures]
    counts = Counter(fixture_ids)
    duplicates = tuple(sorted(key for key, count in counts.items() if count > 1))
    decisions = []
    seen: set[str] = set()
    for row in fixtures:
        if row.provider_fixture_id in seen:
            decisions.append(FixtureImportDecision(
                ImportOutcomeStatus.QUARANTINED,
                "DUPLICATE_PROVIDER_FIXTURE_ID_ACROSS_PAGES",
                row.provider_fixture_id,
            ))
            continue
        seen.add(row.provider_fixture_id)
        decisions.append(evaluate_fixture_import(
            row, approval, evaluated_at_utc=evaluated_at_utc
        ))

    importable = sum(item.status is ImportOutcomeStatus.IMPORTABLE for item in decisions)
    rejected = sum(item.status is ImportOutcomeStatus.REJECTED for item in decisions)
    quarantined = sum(item.status is ImportOutcomeStatus.QUARANTINED for item in decisions)
    by_comp = Counter(
        row.provider_competition_id for row, decision in zip(fixtures, decisions)
        if decision.status is ImportOutcomeStatus.IMPORTABLE
    )
    settled = [
        row.kickoff_at_utc.astimezone(timezone.utc)
        for row, decision in zip(fixtures, decisions)
        if decision.status is ImportOutcomeStatus.IMPORTABLE
    ]
    manifest_parts = sorted(
        f"{row.provider}|{row.source_id}|{row.provider_fixture_id}|{row.provider_competition_id}|{row.payload_sha256}"
        for row in fixtures
    )
    manifest_hash = sha256("\n".join(manifest_parts).encode("utf-8")).hexdigest()
    status = "COMPLETE" if not rejected and not quarantined else "PARTIAL"
    report = ImportBatchReport(
        status=status,
        total_records=len(fixtures),
        importable_count=importable,
        rejected_count=rejected,
        quarantined_count=quarantined,
        duplicate_provider_fixture_ids=duplicates,
        first_kickoff_utc=min(settled).isoformat() if settled else None,
        last_kickoff_utc=max(settled).isoformat() if settled else None,
        counts_by_competition=tuple(sorted(by_comp.items())),
        source_manifest_sha256=manifest_hash,
        request_count=request_count,
        request_budget=request_budget,
    )
    return HistoryBatchAssessment(report, tuple(decisions), tuple(fixture_ids))


@dataclass(frozen=True, slots=True)
class ManifestReconciliation:
    complete: bool
    expected_count: int
    outcome_count: int
    missing_ids: tuple[str, ...]
    unexpected_ids: tuple[str, ...]
    duplicate_outcome_ids: tuple[str, ...]
    manifest_sha256: str
    reason_code: str


def reconcile_source_manifest(
    expected_ids: Iterable[str],
    decisions: Sequence[FixtureImportDecision],
) -> ManifestReconciliation:
    expected = list(expected_ids)
    if any(not value or not value.strip() for value in expected):
        raise ValueError("EXPECTED_FIXTURE_IDS_REQUIRED")
    if len(expected) != len(set(expected)):
        raise ValueError("EXPECTED_FIXTURE_IDS_MUST_BE_UNIQUE")
    outcomes = [item.provider_fixture_id for item in decisions]
    counts = Counter(outcomes)
    expected_set, outcome_set = set(expected), set(outcomes)
    missing = tuple(sorted(expected_set - outcome_set))
    unexpected = tuple(sorted(outcome_set - expected_set))
    duplicates = tuple(sorted(key for key, count in counts.items() if count > 1))
    complete = not (missing or unexpected or duplicates)
    digest = sha256("\n".join(sorted(expected)).encode("utf-8")).hexdigest()
    return ManifestReconciliation(
        complete, len(expected), len(outcomes), missing, unexpected, duplicates,
        digest, "SOURCE_MANIFEST_FULLY_ACCOUNTED" if complete else "SOURCE_MANIFEST_RECONCILIATION_FAILED",
    )
