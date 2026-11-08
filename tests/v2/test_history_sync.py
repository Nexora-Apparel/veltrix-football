from datetime import datetime, timezone, timedelta
from veltrix_v2.history.contracts import SyncWatermark, IncrementalSyncPlan
from veltrix_v2.history.sync import SyncPageResult, run_incremental_sync

NOW=datetime(2026,11,8,tzinfo=timezone.utc)


class Watermarks:
    def __init__(self, version=4, cursor="old", result=True):
        self.current=SyncWatermark("5DollarFootballAPI","fixtures","league-1",cursor,NOW,version)
        self.calls=[]; self.result=result
    def read(self, **kwargs): return self.current
    def advance(self, watermark, *, expected_version):
        self.calls.append((watermark,expected_version))
        return self.result


def plan(max_pages=3):
    return IncrementalSyncPlan("5DollarFootballAPI","fixtures","league-1",
        NOW-timedelta(days=1),NOW,max_pages,100,4)


def page(cursor,more=False,status="COMPLETED",rejected=0):
    return SyncPageResult(status,cursor,more,10,10-rejected,rejected,1,
                          "OK" if status=="COMPLETED" else "PAGE_FAILED")


def test_watermark_advances_only_after_all_pages_complete():
    store=Watermarks()
    pages={1:page("next",True),2:page("done")}
    result=run_incremental_sync(plan(),store,lambda n,c:pages[n],initial_cursor="old")
    assert result.status=="COMPLETED" and result.pages_completed==2
    assert result.watermark_advanced and store.calls[0][1]==4
    assert store.calls[0][0].cursor=="done"


def test_failed_page_never_advances_watermark():
    store=Watermarks()
    result=run_incremental_sync(plan(),store,lambda n,c:page(c,status="FAILED"),initial_cursor="old")
    assert result.status=="FAILED" and not result.watermark_advanced and not store.calls


def test_rejected_records_prevent_watermark_advance():
    store=Watermarks()
    result=run_incremental_sync(plan(),store,lambda n,c:page("next",rejected=1),initial_cursor="old")
    assert not result.watermark_advanced and result.rejected_count==1


def test_page_limit_reached_never_advances_watermark():
    store=Watermarks()
    result=run_incremental_sync(plan(2),store,lambda n,c:page(str(n),True),initial_cursor="old")
    assert result.reason_code=="SYNC_PAGE_LIMIT_REACHED" and not result.watermark_advanced


def test_compare_and_set_conflict_is_reported():
    store=Watermarks(result=False)
    result=run_incremental_sync(plan(),store,lambda n,c:page("new"),initial_cursor="old")
    assert result.status=="CONFLICT" and not result.watermark_advanced


def test_stale_starting_watermark_blocks_before_provider_call():
    store=Watermarks(version=5); called=[]
    result=run_incremental_sync(plan(),store,lambda n,c:called.append(n),initial_cursor="old")
    assert result.reason_code=="STARTING_WATERMARK_CHANGED" and not called


def test_non_advancing_page_cursor_is_rejected():
    store=Watermarks()
    result=run_incremental_sync(plan(),store,lambda n,c:page(c,True),initial_cursor="old")
    assert result.reason_code=="SYNC_CURSOR_DID_NOT_ADVANCE"
