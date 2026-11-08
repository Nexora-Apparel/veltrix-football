from datetime import date, datetime, timezone
from veltrix_v2.history.contracts import HistoricalMatch, TeamHistoryQuery, SyncWatermark
from veltrix_v2.history.postgres import PostgresHistoryStore


class Cursor:
    def __init__(self, conn): self.conn, self.rowcount, self._one, self._all = conn, 0, None, []
    def execute(self, sql, params=()):
        if "INSERT INTO v2_canonical_fixtures" in sql:
            self.conn.fixtures.setdefault(params[0], params)
            self.rowcount = 1
        elif "INSERT INTO v2_historical_matches" in sql:
            self.conn.matches.setdefault(params[0], params)
            self.rowcount = 1
        elif "SELECT canonical_fixture_id, home_goals, away_goals" in sql:
            v=self.conn.matches.get(params[0]); self._one=(v[1],v[2],v[3]) if v else None
        elif "INSERT INTO v2_historical_match_sources" in sql:
            key=(params[2],params[3],params[4]); self.conn.refs.setdefault(key,params); self.rowcount=1
        elif "SELECT source_record_id FROM v2_historical_match_sources" in sql:
            v=self.conn.refs.get(tuple(params)); self._one=(v[1],) if v else None
        elif "SELECT cursor, updated_at_utc, version" in sql:
            v=self.conn.watermarks.get(tuple(params)); self._one=v
        elif "INSERT INTO v2_sync_watermarks" in sql:
            key=params[:3]
            if key not in self.conn.watermarks:
                self.conn.watermarks[key]=params[3:]; self.rowcount=1
        elif "UPDATE v2_sync_watermarks" in sql:
            key=params[3:6]; old=self.conn.watermarks.get(key)
            if old and old[2] == params[6]:
                self.conn.watermarks[key]=(params[0],params[1],params[2]); self.rowcount=1
    def fetchone(self): return self._one
    def fetchall(self): return self._all


class Conn:
    def __init__(self):
        self.fixtures,self.matches,self.refs,self.watermarks={},{},{},{}
    def cursor(self): return Cursor(self)
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass


def sample():
    return HistoricalMatch("hist-1","fix-1","comp-1","SENIOR_MEN","home","away",
        datetime(2026,1,1,tzinfo=timezone.utc),2,0,("src-1",),
        (("5DollarFootballAPI","five-dollar","provider-fix-1"),))


def test_persist_history_preserves_provider_fixture_reference_idempotently():
    db=Conn(); store=PostgresHistoryStore(lambda: db); match=sample()
    assert store.persist_historical_match(match, imported_at_utc=datetime.now(timezone.utc))
    assert store.persist_historical_match(match, imported_at_utc=datetime.now(timezone.utc))
    assert ("5DollarFootballAPI","five-dollar","provider-fix-1") in db.refs


def test_watermark_compare_and_set_rejects_stale_writer():
    db=Conn(); store=PostgresHistoryStore(lambda: db)
    first=SyncWatermark("5DollarFootballAPI","fixtures","league-1","cursor-1",
                        datetime.now(timezone.utc),1)
    assert store.advance(first, expected_version=0)
    stale=SyncWatermark("5DollarFootballAPI","fixtures","league-1","cursor-0",
                        datetime.now(timezone.utc),1)
    assert not store.advance(stale, expected_version=0)
