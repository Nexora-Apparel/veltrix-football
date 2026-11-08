"""Bounded incremental sync orchestration with atomic watermark advancement."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Callable

from veltrix_v2.history.contracts import IncrementalSyncPlan, SyncWatermark, SyncWatermarkRepository


@dataclass(frozen=True, slots=True)
class SyncPageResult:
    status: str
    next_cursor: str | None
    has_more: bool
    fetched_count: int
    accepted_count: int
    rejected_count: int
    quota_units_consumed: int
    reason_code: str

    def __post_init__(self) -> None:
        if self.status not in {"COMPLETED", "PARTIAL", "FAILED", "WITHHELD", "DISABLED"}:
            raise ValueError("invalid sync page status")
        if min(self.fetched_count, self.accepted_count, self.rejected_count,
               self.quota_units_consumed) < 0:
            raise ValueError("sync page counts cannot be negative")
        if self.accepted_count + self.rejected_count > self.fetched_count:
            raise ValueError("accepted and rejected counts exceed fetched count")


@dataclass(frozen=True, slots=True)
class IncrementalSyncResult:
    status: str
    reason_code: str
    pages_completed: int
    fetched_count: int
    accepted_count: int
    rejected_count: int
    quota_units_consumed: int
    watermark_advanced: bool
    final_cursor: str | None


def run_incremental_sync(
    plan: IncrementalSyncPlan,
    watermarks: SyncWatermarkRepository,
    execute_page: Callable[[int, str | None], SyncPageResult],
    *,
    initial_cursor: str | None,
) -> IncrementalSyncResult:
    """Run at most max_pages; never move the cursor after a partial/failed page.

    The caller must build each page request with its own bounded quota reservation
    and idempotency key. The coordinator verifies the starting watermark and
    advances it only after every page is accepted without rejected records.
    """
    current = watermarks.read(
        provider=plan.provider, data_class=plan.data_class, scope=plan.scope
    )
    if current is None:
        if plan.expected_watermark_version != 0 or initial_cursor is not None:
            return IncrementalSyncResult("CONFLICT", "STARTING_WATERMARK_MISSING",
                0,0,0,0,0,False,initial_cursor)
    elif current.version != plan.expected_watermark_version or current.cursor != initial_cursor:
        return IncrementalSyncResult("CONFLICT", "STARTING_WATERMARK_CHANGED",
            0,0,0,0,0,False,initial_cursor)

    cursor = initial_cursor
    fetched = accepted = rejected = consumed = pages = 0
    for page_number in range(1, plan.max_pages + 1):
        result = execute_page(page_number, cursor)
        fetched += result.fetched_count
        accepted += result.accepted_count
        rejected += result.rejected_count
        consumed += result.quota_units_consumed
        if result.status != "COMPLETED" or result.rejected_count:
            status = "PARTIAL" if result.status == "PARTIAL" else "FAILED"
            return IncrementalSyncResult(
                status, result.reason_code or "SYNC_PAGE_NOT_COMPLETE",
                pages, fetched, accepted, rejected, consumed, False, cursor,
            )
        pages += 1
        if result.has_more and result.next_cursor == cursor:
            return IncrementalSyncResult(
                "FAILED", "SYNC_CURSOR_DID_NOT_ADVANCE", pages, fetched,
                accepted, rejected, consumed, False, cursor,
            )
        cursor = result.next_cursor
        if not result.has_more:
            next_watermark = SyncWatermark(
                provider=plan.provider, data_class=plan.data_class, scope=plan.scope,
                cursor=cursor, updated_at_utc=plan.upper_bound_utc.astimezone(timezone.utc),
                version=plan.expected_watermark_version + 1,
            )
            advanced = watermarks.advance(
                next_watermark, expected_version=plan.expected_watermark_version
            )
            return IncrementalSyncResult(
                "COMPLETED" if advanced else "CONFLICT",
                "SYNC_COMPLETED" if advanced else "WATERMARK_COMPARE_AND_SET_FAILED",
                pages, fetched, accepted, rejected, consumed, advanced, cursor,
            )
    return IncrementalSyncResult(
        "PARTIAL", "SYNC_PAGE_LIMIT_REACHED", pages, fetched, accepted, rejected,
        consumed, False, cursor,
    )
