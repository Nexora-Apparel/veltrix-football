"""Deterministic read-only reconciliation of StrikerAPI and 5DollarFootballAPI JSON exports."""
from __future__ import annotations
import argparse, hashlib, json, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("kickoff timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def payload_hash(row: dict) -> str:
    raw = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def striker_record(row: dict, league_key: str) -> dict:
    h, a = row.get("home") or {}, row.get("away") or {}
    return {"provider":"strikerapi","source_id":str(row.get("game_id","")),
            "competition_key":league_key,"home_id":str(h.get("team_id","")),
            "away_id":str(a.get("team_id","")),"home":str(h.get("name","")),
            "away":str(a.get("name","")),"kickoff":str(row.get("starts_at","")),
            "status":str(row.get("status","")),"home_score":h.get("score"),
            "away_score":a.get("score"),"payload_sha256":payload_hash(row),"raw":row}


def fivedollar_record(row: dict) -> dict:
    t, g, l = row.get("teams") or {}, row.get("goals") or {}, row.get("league") or {}
    h, a = t.get("home") or {}, t.get("away") or {}
    return {"provider":"fivedollar","source_id":str(row.get("id","")),
            "competition_key":str(l.get("id","")),"home_id":str(h.get("id","")),
            "away_id":str(a.get("id","")),"home":str(h.get("name","")),
            "away":str(a.get("name","")),"kickoff":str(row.get("kickoff_utc","")),
            "status":str(row.get("status","")),"home_score":g.get("home"),
            "away_score":g.get("away"),"payload_sha256":payload_hash(row),"raw":row}


def valid_identity(row: dict) -> bool:
    if not all(row.get(k) for k in ("source_id","home","away","kickoff")):
        return False
    try: parse_utc(row["kickoff"])
    except (TypeError, ValueError): return False
    return True


def reconcile(striker_rows: list[dict], dollar_rows: list[dict], competition_map: dict,
              tolerance_seconds: int = 300) -> dict:
    left, right = list(striker_rows), list(dollar_rows)
    invalid_left = {i for i,r in enumerate(left) if not valid_identity(r)}
    invalid_right = {j for j,r in enumerate(right) if not valid_identity(r)}
    duplicate_left = sorted({r["source_id"] for r in left if r.get("source_id") and
                             sum(x.get("source_id")==r["source_id"] for x in left)>1})
    duplicate_right = sorted({r["source_id"] for r in right if r.get("source_id") and
                              sum(x.get("source_id")==r["source_id"] for x in right)>1})
    edges, orientations = {}, {}
    for i,s in enumerate(left):
        if i in invalid_left or s.get("competition_key") not in competition_map: continue
        mapped = str(competition_map[s["competition_key"]])
        for j,d in enumerate(right):
            if j in invalid_right or str(d.get("competition_key","")) != mapped: continue
            delta = abs((parse_utc(s["kickoff"])-parse_utc(d["kickoff"])).total_seconds())
            sh,sa,dh,da = map(normalize_name,(s["home"],s["away"],d["home"],d["away"]))
            if sh==dh and sa==da and delta<=tolerance_seconds: edges[(i,j)] = int(delta)
            elif sh==da and sa==dh and delta<=tolerance_seconds: orientations[(i,j)] = int(delta)
    ld, rd = {}, {}
    for i,j in edges:
        ld[i]=ld.get(i,0)+1; rd[j]=rd.get(j,0)+1
    used_l, used_r, ql, qr, decisions = set(),set(),set(invalid_left),set(invalid_right),[]
    for i in sorted(invalid_left):
        decisions.append({"outcome":"INVALID_SOURCE_ROW","striker":left[i],"fivedollar":None,"reason":"missing identity or invalid timezone-aware kickoff"})
    for j in sorted(invalid_right):
        decisions.append({"outcome":"INVALID_SOURCE_ROW","striker":None,"fivedollar":right[j],"reason":"missing identity or invalid timezone-aware kickoff"})
    for (i,j),delta in sorted(orientations.items()):
        ql.add(i); qr.add(j)
        decisions.append({"outcome":"IDENTITY_CONFLICT","striker":left[i],"fivedollar":right[j],
                          "kickoff_delta_seconds":delta,"reason":"home_away_orientation_reversed"})
    for (i,j),delta in sorted(edges.items()):
        s,d=left[i],right[j]
        if ld.get(i,0)>1 or rd.get(j,0)>1:
            ql.add(i); qr.add(j)
            decisions.append({"outcome":"AMBIGUOUS_MULTIPLE_CANDIDATES","striker":s,"fivedollar":d,
                              "kickoff_delta_seconds":delta,"reason":"candidate_graph_degree_exceeds_one"})
            continue
        used_l.add(i); used_r.add(j)
        ss = "finished" if s["status"]=="final" else s["status"]
        if ss != d["status"]: outcome,reason="STATUS_CONFLICT","provider_status_disagreement"
        elif ss=="finished" and (s.get("home_score")!=d.get("home_score") or s.get("away_score")!=d.get("away_score")):
            outcome,reason="RESULT_CONFLICT","final_score_disagreement"
        else: outcome,reason="MATCHED_UNIQUE","competition_teams_orientation_and_kickoff_match"
        if outcome in ("STATUS_CONFLICT","RESULT_CONFLICT"): ql.add(i); qr.add(j)
        decisions.append({"outcome":outcome,"striker":s,"fivedollar":d,
                          "kickoff_delta_seconds":delta,"reason":reason})
    for i,s in enumerate(left):
        if i not in used_l and i not in ql:
            decisions.append({"outcome":"UNMATCHED_STRIKER_ONLY","striker":s,"fivedollar":None,"reason":"no unique candidate"})
    for j,d in enumerate(right):
        if j not in used_r and j not in qr:
            decisions.append({"outcome":"UNMATCHED_5DOLLAR_ONLY","striker":None,"fivedollar":d,"reason":"no unique candidate"})
    matched_l,matched_r=len(used_l-ql),len(used_r-qr)
    unmatched_l=sum(x["outcome"]=="UNMATCHED_STRIKER_ONLY" for x in decisions)
    unmatched_r=sum(x["outcome"]=="UNMATCHED_5DOLLAR_ONLY" for x in decisions)
    return {"schema_version":1,"mode":"read_only_no_merge","tolerance_seconds":tolerance_seconds,
            "competition_map_striker_to_fivedollar":competition_map,
            "source_counts":{"striker":len(left),"fivedollar":len(right)},
            "duplicate_source_ids":{"striker":duplicate_left,"fivedollar":duplicate_right},
            "accounting":{
                "striker":{"total":len(left),"matched":matched_l,"unmatched":unmatched_l,"quarantined":len(ql),
                           "balanced":len(left)==matched_l+unmatched_l+len(ql)},
                "fivedollar":{"total":len(right),"matched":matched_r,"unmatched":unmatched_r,"quarantined":len(qr),
                              "balanced":len(right)==matched_r+unmatched_r+len(qr)}},
            "decisions":decisions}


def load_envelope(path: str, provider: str):
    env=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(env,dict) or not isinstance(env.get("data"),(dict,list)):
        raise ValueError(f"{provider} input must be an envelope")
    if provider=="strikerapi":
        key=env.get("league_key"); rows=env["data"].get("games") if isinstance(env["data"],dict) else None
        if not isinstance(key,str) or not isinstance(rows,list): raise ValueError("Striker envelope requires league_key and data.games")
        return [striker_record(x,key) for x in rows],env
    rows=env["data"]
    if not isinstance(rows,list): raise ValueError("5Dollar envelope data must be an array")
    return [fivedollar_record(x) for x in rows],env


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--striker",required=True); p.add_argument("--fivedollar",required=True)
    p.add_argument("--competition-map",required=True); p.add_argument("--output",required=True)
    a=p.parse_args()
    s,sm=load_envelope(a.striker,"strikerapi"); d,dm=load_envelope(a.fivedollar,"fivedollar")
    mapping=json.loads(Path(a.competition_map).read_text(encoding="utf-8"))
    if not isinstance(mapping,dict) or not mapping: raise ValueError("competition map must be a non-empty object")
    report=reconcile(s,d,mapping)
    report["provenance"]={"striker_retrieved_at":sm.get("retrieved_at"),"striker_query":sm.get("query"),
                          "fivedollar_retrieved_at":dm.get("retrieved_at"),"fivedollar_query":dm.get("query")}
    Path(a.output).write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"RECONCILIATION_REPORT: {a.output}")
    print(f"STRIKER_BALANCED: {report['accounting']['striker']['balanced']}")
    print(f"FIVEDOLLAR_BALANCED: {report['accounting']['fivedollar']['balanced']}")
    print("DATABASE_WRITES: 0; CANONICAL_MERGES: 0")
    return 0 if all(x["balanced"] for x in report["accounting"].values()) else 2


if __name__=="__main__": raise SystemExit(main())
