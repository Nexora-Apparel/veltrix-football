"""PostgreSQL persistence adapter for V2 source history and sync state."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Callable
from veltrix_v2.history.contracts import HistoricalMatch, HistoryEvidenceResult, SyncWatermark, TeamHistoryQuery
from veltrix_v2.domain.contracts import HistoryState


class PostgresHistoryStore:
    def __init__(self, connection_factory: Callable[[], object]):
        self._connect=connection_factory

    def persist_historical_match(self, match: HistoricalMatch, *, imported_at_utc: datetime) -> bool:
        if imported_at_utc.tzinfo is None or imported_at_utc.utcoffset() is None:
            raise ValueError("imported_at_utc must be timezone-aware")
        refs=match.provider_source_record_refs
        if not refs:
            if len(match.source_record_ids)!=1 or len(match.provider_fixture_refs)!=1:
                raise ValueError("PROVIDER_SOURCE_PROVENANCE_LINKS_REQUIRED")
            refs=((match.source_record_ids[0],*match.provider_fixture_refs[0]),)
        conn=self._connect()
        try:
            cur=conn.cursor()
            cur.execute("""INSERT INTO v2_canonical_fixtures
                (canonical_fixture_id,canonical_competition_id,squad_category,
                 canonical_home_team_id,canonical_away_team_id,kickoff_at_utc)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(canonical_fixture_id) DO NOTHING""",
                (match.canonical_fixture_id,match.canonical_competition_id,match.squad_category,
                 match.home_team_id,match.away_team_id,match.kickoff_at_utc))
            cur.execute("""SELECT canonical_competition_id,squad_category,canonical_home_team_id,
                canonical_away_team_id,kickoff_at_utc FROM v2_canonical_fixtures
                WHERE canonical_fixture_id=%s""",(match.canonical_fixture_id,))
            fixture=cur.fetchone()
            expected=(match.canonical_competition_id,match.squad_category,match.home_team_id,
                      match.away_team_id,match.kickoff_at_utc)
            if not fixture or tuple(fixture)!=expected:
                raise ValueError("CANONICAL_FIXTURE_IDENTITY_CONFLICT")
            cur.execute("""INSERT INTO v2_historical_matches
                (historical_match_id,canonical_fixture_id,home_goals,away_goals,imported_at_utc)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT(historical_match_id) DO NOTHING""",
                (match.historical_match_id,match.canonical_fixture_id,match.home_goals,
                 match.away_goals,imported_at_utc.astimezone(timezone.utc)))
            cur.execute("SELECT canonical_fixture_id,home_goals,away_goals FROM v2_historical_matches WHERE historical_match_id=%s",
                        (match.historical_match_id,))
            stored=cur.fetchone()
            if not stored or tuple(stored)!=(match.canonical_fixture_id,match.home_goals,match.away_goals):
                raise ValueError("HISTORICAL_MATCH_IDEMPOTENCY_CONFLICT")
            for record_id,provider,source_id,fixture_id in refs:
                if record_id not in match.source_record_ids or (provider,source_id,fixture_id) not in match.provider_fixture_refs:
                    raise ValueError("PROVIDER_SOURCE_PROVENANCE_LINK_INVALID")
                cur.execute("""INSERT INTO v2_historical_match_sources
                    (historical_match_id,source_record_id,provider,source_id,provider_fixture_id)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (match.historical_match_id,record_id,provider,source_id,fixture_id))
                cur.execute("""SELECT source_record_id FROM v2_historical_match_sources
                    WHERE historical_match_id=%s AND source_record_id=%s AND provider=%s
                    AND source_id=%s AND provider_fixture_id=%s""",
                    (match.historical_match_id,record_id,provider,source_id,fixture_id))
                if cur.fetchone() is None:
                    raise ValueError("PROVIDER_FIXTURE_PROVENANCE_CONFLICT")
            conn.commit()
            return True
        except Exception:
            conn.rollback(); raise
        finally:
            conn.close()

    def get_team_history(self, query: TeamHistoryQuery) -> HistoryEvidenceResult:
        conn=self._connect()
        try:
            cur=conn.cursor()
            lower=datetime.combine(query.window_start_date,datetime.min.time(),tzinfo=timezone.utc)
            cur.execute("""SELECT COUNT(*) FROM v2_historical_matches h
                JOIN v2_canonical_fixtures f USING(canonical_fixture_id)
                WHERE (f.canonical_home_team_id=%s OR f.canonical_away_team_id=%s)
                AND f.squad_category<>%s AND f.kickoff_at_utc<%s AND f.kickoff_at_utc>=%s
                AND (%s=0 OR f.canonical_competition_id=ANY(%s))""",
                (query.canonical_team_id,query.canonical_team_id,query.squad_category,
                 query.cutoff_at_utc,lower,len(query.competition_ids),list(query.competition_ids)))
            mismatch_count=cur.fetchone()[0]
            if mismatch_count:
                cur.execute("""SELECT s.source_record_id FROM v2_historical_match_sources s
                    JOIN v2_historical_matches h USING(historical_match_id)
                    JOIN v2_canonical_fixtures f USING(canonical_fixture_id)
                    WHERE (f.canonical_home_team_id=%s OR f.canonical_away_team_id=%s)
                    AND f.squad_category<>%s AND f.kickoff_at_utc<%s AND f.kickoff_at_utc>=%s
                    AND (%s=0 OR f.canonical_competition_id=ANY(%s))""",
                    (query.canonical_team_id,query.canonical_team_id,query.squad_category,
                     query.cutoff_at_utc,lower,len(query.competition_ids),list(query.competition_ids)))
                ids=tuple(dict.fromkeys(row[0] for row in cur.fetchall()))
                return HistoryEvidenceResult(query.canonical_team_id,HistoryState.IDENTITY_MISMATCH,
                                             (),0,ids,"SQUAD_CATEGORY_CONFLICT")
            cur.execute("""SELECT COUNT(*) FROM v2_historical_matches h
                JOIN v2_canonical_fixtures f USING(canonical_fixture_id)
                WHERE (f.canonical_home_team_id=%s OR f.canonical_away_team_id=%s)
                AND f.squad_category=%s AND f.kickoff_at_utc<%s AND f.kickoff_at_utc>=%s
                AND (%s=0 OR f.canonical_competition_id=ANY(%s))""",
                (query.canonical_team_id,query.canonical_team_id,query.squad_category,
                 query.cutoff_at_utc,lower,len(query.competition_ids),list(query.competition_ids)))
            total=cur.fetchone()[0]
            cur.execute("""SELECT h.historical_match_id,h.canonical_fixture_id,f.canonical_competition_id,
                f.squad_category,f.canonical_home_team_id,f.canonical_away_team_id,
                f.kickoff_at_utc,h.home_goals,h.away_goals
                FROM v2_historical_matches h JOIN v2_canonical_fixtures f USING(canonical_fixture_id)
                WHERE (f.canonical_home_team_id=%s OR f.canonical_away_team_id=%s)
                AND f.squad_category=%s AND f.kickoff_at_utc<%s AND f.kickoff_at_utc>=%s
                AND (%s=0 OR f.canonical_competition_id=ANY(%s))
                ORDER BY f.kickoff_at_utc DESC LIMIT %s""",
                (query.canonical_team_id,query.canonical_team_id,query.squad_category,
                 query.cutoff_at_utc,lower,len(query.competition_ids),list(query.competition_ids),query.max_matches))
            rows=cur.fetchall(); matches=[]; evidence=[]
            for row in rows:
                cur.execute("""SELECT source_record_id,provider,source_id,provider_fixture_id
                    FROM v2_historical_match_sources WHERE historical_match_id=%s""",(row[0],))
                provenance=cur.fetchall()
                source_ids=tuple(dict.fromkeys(p[0] for p in provenance))
                provider_refs=tuple(dict.fromkeys((p[1],p[2],p[3]) for p in provenance))
                paired=tuple(dict.fromkeys((p[0],p[1],p[2],p[3]) for p in provenance))
                matches.append(HistoricalMatch(
                    historical_match_id=row[0],canonical_fixture_id=row[1],
                    canonical_competition_id=row[2],squad_category=row[3],
                    home_team_id=row[4],away_team_id=row[5],kickoff_at_utc=row[6],
                    home_goals=row[7],away_goals=row[8],source_record_ids=source_ids,
                    provider_fixture_refs=provider_refs,provider_source_record_refs=paired))
                evidence.extend(source_ids)
            matches.reverse()
            if total==0: state,reason=HistoryState.NOT_FOUND,"NO_MATCHES_IN_REQUESTED_WINDOW"
            elif total<query.minimum_matches: state,reason=HistoryState.INSUFFICIENT_COVERAGE,"BELOW_MINIMUM_TEAM_HISTORY"
            else: state,reason=HistoryState.FOUND,"MINIMUM_TEAM_HISTORY_MET"
            return HistoryEvidenceResult(query.canonical_team_id,state,tuple(matches),total,
                                         tuple(dict.fromkeys(evidence)),reason)
        finally:
            conn.close()

    def read(self, *, provider: str, data_class: str, scope: str) -> SyncWatermark | None:
        conn=self._connect()
        try:
            cur=conn.cursor()
            cur.execute("SELECT cursor,updated_at_utc,version FROM v2_sync_watermarks WHERE provider=%s AND data_class=%s AND scope=%s",
                        (provider,data_class,scope))
            row=cur.fetchone()
            return None if row is None else SyncWatermark(provider,data_class,scope,row[0],row[1],row[2])
        finally:
            conn.close()

    def advance(self, watermark: SyncWatermark, *, expected_version: int) -> bool:
        conn=self._connect()
        try:
            cur=conn.cursor()
            if expected_version==0:
                cur.execute("""INSERT INTO v2_sync_watermarks(provider,data_class,scope,cursor,updated_at_utc,version)
                    VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(provider,data_class,scope) DO NOTHING""",
                    (watermark.provider,watermark.data_class,watermark.scope,watermark.cursor,
                     watermark.updated_at_utc,watermark.version))
            else:
                cur.execute("""UPDATE v2_sync_watermarks SET cursor=%s,updated_at_utc=%s,version=%s
                    WHERE provider=%s AND data_class=%s AND scope=%s AND version=%s""",
                    (watermark.cursor,watermark.updated_at_utc,watermark.version,watermark.provider,
                     watermark.data_class,watermark.scope,expected_version))
            changed=cur.rowcount==1
            conn.commit()
            return changed
        except Exception:
            conn.rollback(); raise
        finally:
            conn.close()
