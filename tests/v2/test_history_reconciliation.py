from veltrix_v2.history.batch_import import HistoryImportBatchReport, HistoryImportRowResult
from veltrix_v2.history.reconciliation import reconcile_history_import


def report(*rows):
    imported=sum(row.status=="IMPORTED" for row in rows)
    rejected=sum(row.status=="REJECTED" for row in rows)
    quarantined=sum(row.status=="QUARANTINED" for row in rows)
    return HistoryImportBatchReport(
        "COMPLETED" if not rejected and not quarantined else "PARTIAL",
        len(rows),imported,rejected,quarantined,"a"*64,tuple(rows))


def row(source_id,status="IMPORTED"):
    return HistoryImportRowResult(source_id,"provider-"+source_id,status,"REASON",None)


def test_reconciliation_accounts_for_every_source_record():
    result=reconcile_history_import(["a","b","c"],[
        report(row("a"),row("b","REJECTED")),report(row("c","QUARANTINED"))])
    assert result.complete
    assert (result.imported_count,result.rejected_count,result.quarantined_count)==(1,1,1)
    assert result.reason_code=="SOURCE_MANIFEST_FULLY_ACCOUNTED"


def test_missing_source_record_is_detected():
    result=reconcile_history_import(["a","b"],[report(row("a"))])
    assert not result.complete and result.missing_source_record_ids==("b",)


def test_unexpected_source_record_is_detected():
    result=reconcile_history_import(["a"],[report(row("a"),row("x"))])
    assert result.unexpected_source_record_ids==("x",)


def test_duplicate_terminal_outcome_is_detected():
    result=reconcile_history_import(["a"],[report(row("a")),report(row("a"))])
    assert result.duplicate_outcome_source_record_ids==("a",)


def test_duplicate_expected_manifest_ids_are_rejected():
    try:
        reconcile_history_import(["a","a"],[])
    except ValueError as exc:
        assert str(exc)=="EXPECTED_SOURCE_RECORD_IDS_MUST_BE_UNIQUE"
    else:
        raise AssertionError("duplicate expected IDs must fail closed")


def test_report_count_tampering_is_rejected():
    bad=HistoryImportBatchReport("COMPLETED",2,1,0,0,"a"*64,(row("a"),))
    try:
        reconcile_history_import(["a"],[bad])
    except ValueError as exc:
        assert str(exc)=="BATCH_REPORT_ROW_COUNT_MISMATCH"
    else:
        raise AssertionError("tampered batch counts must fail closed")
