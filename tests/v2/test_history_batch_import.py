from datetime import datetime, timedelta, timezone
from veltrix_v2.domain.contracts import DataUsePurpose, RightsStatus, SourceRights
from veltrix_v2.domain.identity import SquadCategory, ProviderFixtureIdentity
from veltrix_v2.identity.registry import (
    MappingResolutionStatus, ProviderFixtureSourceIdentity, ResolvedProviderFixture,
)
from veltrix_v2.history.batch_import import HistoryImportCandidate, import_history_batch
from veltrix_v2.ingestion.providers.five_dollar_fixture import (
    FiveDollarFixtureRecord, FiveDollarFixtureStatus,
)

NOW=datetime(2026,11,8,9,tzinfo=timezone.utc)
KICKOFF=NOW-timedelta(days=3)


def candidate(source_id="source-record-1", verified=True, canonical_id="canonical-fixture-1",
              status=FiveDollarFixtureStatus.FINISHED, rights_ok=True):
    source=ProviderFixtureSourceIdentity("5DollarFootballAPI","five-dollar","provider-fx-1",
        "provider-comp-1","provider-home","provider-away",None,KICKOFF)
    canonical=ProviderFixtureIdentity("5DollarFootballAPI","provider-fx-1","provider-comp-1",
        "canonical-comp",SquadCategory.SENIOR_MEN,"team-home","team-away",KICKOFF) if verified else None
    resolved=ResolvedProviderFixture(
        MappingResolutionStatus.VERIFIED if verified else MappingResolutionStatus.UNVERIFIED,
        source,canonical,"MAPPING_VERIFIED" if verified else "TEAM_MAPPING_UNVERIFIED",
        ("competition-evidence","home-evidence","away-evidence"))
    fixture=FiveDollarFixtureRecord(source,status,status.value.lower(),"Home","Away","League",
        2 if status is FiveDollarFixtureStatus.FINISHED else None,
        1 if status is FiveDollarFixtureStatus.FINISHED else None,None,"full","a"*64)
    uses=frozenset({DataUsePurpose.HISTORICAL_IMPORT,DataUsePurpose.CACHE,DataUsePurpose.MODEL_TRAINING})
    rights=SourceRights("five-dollar",RightsStatus.VERIFIED,rights_ok,uses,
        "https://provider.example/terms","2026-11",NOW,"b"*64)
    return HistoryImportCandidate(fixture,resolved,source_id,rights,canonical_id)


class Writer:
    def __init__(self): self.rows=[]
    def persist_historical_match(self,match,*,imported_at_utc):
        self.rows.append(match); return True


def test_batch_imports_settled_verified_rights_cleared_match():
    writer=Writer()
    report=import_history_batch([candidate()],writer,imported_at_utc=NOW,
        evaluated_at_utc=NOW,max_batch_size=10)
    assert report.status=="COMPLETED" and report.imported_count==1
    assert writer.rows[0].provider_fixture_refs==(("5DollarFootballAPI","five-dollar","provider-fx-1"),)
    assert report.source_manifest_sha256


def test_unverified_identity_is_quarantined_not_silently_dropped():
    writer=Writer()
    report=import_history_batch([candidate(verified=False)],writer,
        imported_at_utc=NOW,evaluated_at_utc=NOW)
    assert report.quarantined_count==1 and not writer.rows
    assert report.rows[0].reason_code=="TEAM_MAPPING_UNVERIFIED"


def test_missing_canonical_fixture_reconciliation_is_quarantined():
    writer=Writer()
    report=import_history_batch([candidate(canonical_id=None)],writer,
        imported_at_utc=NOW,evaluated_at_utc=NOW)
    assert report.quarantined_count==1 and not writer.rows


def test_unsettled_result_is_rejected_with_explicit_reason():
    writer=Writer()
    report=import_history_batch([candidate(status=FiveDollarFixtureStatus.SCHEDULED)],writer,
        imported_at_utc=NOW,evaluated_at_utc=NOW)
    assert report.rejected_count==1
    assert report.rows[0].reason_code=="FIXTURE_RESULT_NOT_SETTLED"


def test_rights_denial_prevents_historical_import():
    writer=Writer()
    report=import_history_batch([candidate(rights_ok=False)],writer,
        imported_at_utc=NOW,evaluated_at_utc=NOW)
    assert report.rejected_count==1 and not writer.rows


def test_batch_is_bounded_and_rejects_duplicate_source_ids():
    writer=Writer()
    try:
        import_history_batch([candidate(),candidate("source-record-2")],writer,
            imported_at_utc=NOW,evaluated_at_utc=NOW,max_batch_size=1)
    except ValueError as exc:
        assert str(exc)=="HISTORY_IMPORT_BATCH_LIMIT_EXCEEDED"
    else:
        raise AssertionError("oversized history import must be rejected")
    try:
        import_history_batch([candidate(),candidate()],writer,
            imported_at_utc=NOW,evaluated_at_utc=NOW)
    except ValueError as exc:
        assert str(exc)=="DUPLICATE_SOURCE_RECORD_IN_IMPORT_BATCH"
    else:
        raise AssertionError("duplicate source IDs must be rejected")
