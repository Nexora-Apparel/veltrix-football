from datetime import datetime, timezone
import pytest

from veltrix_v2.domain.identity import (
    ProviderFixtureIdentity, ReconciliationDecision, ReconciliationStatus, SquadCategory,
)
from veltrix_v2.identity.registry import (
    MappingResolutionStatus, ProviderFixtureSourceIdentity, ResolvedProviderFixture,
)
from veltrix_v2.identity.postgres_fixtures import PostgresFixtureDecisionRepository

NOW=datetime(2026,11,8,10,tzinfo=timezone.utc)


class Cursor:
    def __init__(self,db):
        self.db=db; self.one=None; self.rowcount=0
    def execute(self,sql,params=()):
        if "SELECT provider,source_id,provider_fixture_id" in sql:
            self.one=self.db.source if params[0]=="source-1" else None
        elif "INSERT INTO v2_canonical_fixtures" in sql:
            self.db.fixtures.setdefault(params[0],params[1:]); self.rowcount=1
        elif "SELECT canonical_competition_id,squad_category" in sql:
            self.one=self.db.fixtures.get(params[0])
        elif "INSERT INTO v2_fixture_sources" in sql:
            self.db.sources.setdefault((params[0],params[1],params[2],params[7]),params)
            self.rowcount=1
        elif "SELECT canonical_fixture_id,identity_status,reason_code" in sql:
            self.one=self.db.sources.get((params[0],params[1],params[2],params[3]))
    def fetchone(self): return self.one


class Connection:
    def __init__(self,source=("5DollarFootballAPI","five-dollar","provider-fx-1"),fixtures=None):
        self.source=source; self.fixtures=fixtures or {}; self.sources={}
        self.committed=False; self.rolled_back=False
    def cursor(self): return Cursor(self)
    def commit(self): self.committed=True
    def rollback(self): self.rolled_back=True
    def close(self): pass


def objects():
    source=ProviderFixtureSourceIdentity("5DollarFootballAPI","five-dollar","provider-fx-1",
        "provider-comp-1","provider-home","provider-away",SquadCategory.SENIOR_MEN,NOW)
    provider=ProviderFixtureIdentity("5DollarFootballAPI","provider-fx-1","provider-comp-1",
        "canonical-comp",SquadCategory.SENIOR_MEN,"team-home","team-away",NOW)
    mapping=ResolvedProviderFixture(MappingResolutionStatus.VERIFIED,source,provider,
        "MAPPING_VERIFIED",("competition-evidence","home-evidence","away-evidence"))
    return source,provider,mapping


def test_new_canonical_fixture_persists_only_when_source_record_identity_matches():
    db=Connection(); source,provider,mapping=objects()
    decision=ReconciliationDecision(ReconciliationStatus.NEW_CANONICAL_FIXTURE,None,(),provider)
    status=PostgresFixtureDecisionRepository(lambda:db).persist_decision(
        source,"source-1",mapping,decided_at_utc=NOW,reconciliation=decision,
        new_canonical_fixture_id="canonical-fx-1")
    assert status=="NEW_CANONICAL_FIXTURE"
    assert db.committed and not db.rolled_back
    assert db.sources[("5DollarFootballAPI","five-dollar","provider-fx-1","source-1")][6]=="canonical-fx-1"


def test_source_record_from_different_provider_fixture_is_rejected():
    db=Connection(source=("5DollarFootballAPI","five-dollar","different-fixture"))
    source,provider,mapping=objects()
    decision=ReconciliationDecision(ReconciliationStatus.NEW_CANONICAL_FIXTURE,None,(),provider)
    with pytest.raises(ValueError,match="SOURCE_RECORD_PROVIDER_FIXTURE_MISMATCH"):
        PostgresFixtureDecisionRepository(lambda:db).persist_decision(
            source,"source-1",mapping,decided_at_utc=NOW,reconciliation=decision,
            new_canonical_fixture_id="canonical-fx-1")
    assert db.rolled_back and not db.committed


def test_matched_existing_fixture_must_have_exact_canonical_identity():
    wrong={"canonical-fx-1":("wrong-competition","SENIOR_MEN","team-home","team-away",NOW)}
    db=Connection(fixtures=wrong); source,provider,mapping=objects()
    decision=ReconciliationDecision(ReconciliationStatus.MATCHED_EXISTING,"canonical-fx-1",
                                    ("canonical-fx-1",),provider)
    with pytest.raises(ValueError,match="CANONICAL_FIXTURE_IDENTITY_CONFLICT"):
        PostgresFixtureDecisionRepository(lambda:db).persist_decision(
            source,"source-1",mapping,decided_at_utc=NOW,reconciliation=decision)
    assert db.rolled_back and not db.committed
