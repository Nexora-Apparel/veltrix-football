"""Append-only prospective odds evidence ledger for VELTRIX shadow research."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any

VERSION = "VELTRIX_VALUE_EVIDENCE_V1"

def _valid_price(value: Any) -> bool:
    try: return float(value) > 1
    except (TypeError, ValueError, OverflowError): return False

def fixture_key(row: Mapping[str, Any]) -> str:
    kickoff = str(row.get("kickoff_local") or row.get("kickoff") or "")
    comp = str(row.get("competition") or row.get("league") or "")
    home, away = str(row.get("home_team") or ""), str(row.get("away_team") or "")
    fid = str(row.get("fixture_id") or "")
    return "|".join((fid, kickoff, comp, home, away)).casefold()

def _snapshot_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows=[]
    for fixture in report.get("predictions") or []:
        if not isinstance(fixture, Mapping): continue
        key=fixture_key(fixture)
        diagnostics=fixture.get("value_intelligence") or {}
        fetched=diagnostics.get("snapshot_fetched_at")
        markets=diagnostics.get("markets") or {}
        for market, details in markets.items():
            if not isinstance(details, Mapping): continue
            probs=details.get("conservative_screening_probabilities") or {}
            model=details.get("model_probabilities") or {}
            consensus=details.get("market_consensus_probabilities") or {}
            candidate_rows = details.get("candidate_quote_keys") or []
            candidate_keys = {
                (str(item.get("bookmaker") or "UNKNOWN"), str(item.get("selection") or ""))
                for item in candidate_rows if isinstance(item, Mapping)
            }
            candidate_details = {
                (str(item.get("bookmaker") or "UNKNOWN"), str(item.get("selection") or "")): item
                for item in (details.get("candidates") or []) if isinstance(item, Mapping)
            }
            for quote in details.get("bookmaker_quotes") or []:
                if not isinstance(quote, Mapping): continue
                timestamp=str(quote.get("last_update") or fetched or "")
                for selection, odds in (quote.get("odds") or {}).items():
                    if not _valid_price(odds): continue
                    rows.append({
                        "observation_id":"|".join((key,str(market),str(selection),str(quote.get("bookmaker") or "UNKNOWN"),timestamp)),
                        "fixture_key":key,"fixture_id":fixture.get("fixture_id"),
                        "kickoff":fixture.get("kickoff_local") or fixture.get("kickoff"),
                        "competition":fixture.get("competition") or fixture.get("league"),
                        "home_team":fixture.get("home_team"),"away_team":fixture.get("away_team"),
                        "market":market,"selection":selection,"bookmaker":quote.get("bookmaker") or "UNKNOWN",
                        "quote_timestamp":timestamp,"snapshot_fetched_at":fetched,"decimal_odds":float(odds),
                        "model_probability":model.get(selection),"market_consensus_probability":consensus.get(selection),
                        "conservative_probability":probs.get(selection),"model":fixture.get("model"),
                        "shadow_candidate":(str(quote.get("bookmaker") or "UNKNOWN"), str(selection)) in candidate_keys,
                        "candidate_evaluation":candidate_details.get((str(quote.get("bookmaker") or "UNKNOWN"), str(selection))),
                        "source":"The Odds API","evidence_status":"OBSERVED_QUOTE",
                    })
    return rows

def _clv(opening: float, closing: float) -> float:
    # Positive means the earlier price was better: closing implied probability is higher.
    return (1.0/closing - 1.0/opening)*100.0

def merge_evidence_ledger(previous: Mapping[str, Any] | None, report: Mapping[str, Any],
                          results: Mapping[str, Any] | None = None) -> dict[str, Any]:
    prior=dict(previous or {})
    observations=list(prior.get("observations") or [])
    known={str(x.get("observation_id")) for x in observations if isinstance(x, Mapping)}
    added=0
    for row in _snapshot_rows(report):
        if row["observation_id"] not in known:
            observations.append(row); known.add(row["observation_id"]); added+=1
    # Keep all evidence; derive per bookmaker/selection time series without inventing missing prices.
    groups={}
    for row in observations:
        key=(row.get("fixture_key"),row.get("market"),row.get("selection"),row.get("bookmaker"))
        groups.setdefault(key,[]).append(row)
    series=[]
    for key, items in groups.items():
        ordered=sorted(items,key=lambda x:str(x.get("quote_timestamp") or ""))
        prices=[float(x["decimal_odds"]) for x in ordered if _valid_price(x.get("decimal_odds"))]
        first,last=ordered[0],ordered[-1]
        series.append({
            "fixture_key":key[0],"market":key[1],"selection":key[2],"bookmaker":key[3],
            "opening_odds":prices[0] if len(prices)>=2 else None,
            "latest_odds":prices[-1] if prices else None,
            "closing_odds":None,"observations":len(ordered),
            "clv_probability_points":_clv(prices[0],prices[-1]) if len(prices)>=2 else None,
            "clv_status":"PROVISIONAL_NOT_CLOSING" if len(prices)>=2 else "INSUFFICIENT_SNAPSHOTS",
            "first_seen":first.get("quote_timestamp"),"last_seen":last.get("quote_timestamp"),
        })
    result_rows=[]
    for item in (results or {}).get("matches",[]):
        if isinstance(item,Mapping):
            result_rows.append(item)
    # Result matching deliberately requires explicit fixture id and completed score.
    result_by_id={str(x.get("fixture_id")):x for x in result_rows if x.get("fixture_id") is not None}
    settlement_conflicts=list(prior.get("settlement_conflicts") or [])
    conflict_keys={(str(x.get("observation_id")), str(x.get("new_score"))) for x in settlement_conflicts if isinstance(x, Mapping)}
    for row in observations:
        result=result_by_id.get(str(row.get("fixture_id")))
        if not result: continue
        status=str(result.get("fixture_status") or "").upper()
        hg,ag=result.get("home_goals"),result.get("away_goals")
        if (status not in {"FT","AET","PEN"} or not isinstance(hg,int) or isinstance(hg,bool)
                or not isinstance(ag,int) or isinstance(ag,bool)): continue
        market,sel=row.get("market"),row.get("selection")
        if market=="1X2": won=(sel=="home_win" and hg>ag) or (sel=="draw" and hg==ag) or (sel=="away_win" and hg<ag)
        elif market=="BTTS": won=(sel=="yes" and hg>0 and ag>0) or (sel=="no" and (hg==0 or ag==0))
        elif str(market).startswith("OVER_UNDER_"):
            line=float(str(market).replace("OVER_UNDER_","").replace("_","."))
            total=hg+ag
            won=(sel=="over" and total>line) or (sel=="under" and total<line)
        else: continue
        settlement={"status":"SETTLED","home_goals":hg,"away_goals":ag,"won":bool(won),
                    "paper_profit_per_unit":float(row["decimal_odds"])-1 if won else -1.0}
        existing_settlement=row.get("settlement")
        if isinstance(existing_settlement, Mapping) and dict(existing_settlement) != settlement:
            new_score=f"{hg}-{ag}"
            conflict_key=(str(row.get("observation_id")),new_score)
            if conflict_key not in conflict_keys:
                settlement_conflicts.append({
                    "observation_id":row.get("observation_id"),
                    "existing_settlement":dict(existing_settlement),
                    "new_score":new_score,
                    "new_settlement":settlement,
                    "status":"RESULT_CONFLICT_REVIEW_REQUIRED",
                })
                conflict_keys.add(conflict_key)
        elif not isinstance(existing_settlement, Mapping):
            row["settlement"]=settlement
    settled_rows = [x for x in observations if isinstance(x.get("settlement"), Mapping)]
    settled_candidates = [x for x in settled_rows if x.get("shadow_candidate") is True]
    candidate_profit = sum(float(x["settlement"].get("paper_profit_per_unit", 0.0)) for x in settled_candidates)
    candidate_wins = sum(bool(x["settlement"].get("won")) for x in settled_candidates)
    return {"version":VERSION,"status":"SHADOW_ONLY","release_status":"LOCKED_SHADOW_MODE",
            "observations":observations,"price_series":series,"settlement_conflicts":settlement_conflicts,
            "summary":{"observations_total":len(observations),"observations_added":added,
                       "price_series":len(series),"series_with_multiple_snapshots":sum(x["observations"]>=2 for x in series),
                       "settled_observations":len(settled_rows),
                       "shadow_candidate_observations":sum(1 for x in observations if x.get("shadow_candidate") is True),
                       "settled_shadow_candidates":len(settled_candidates),
                       "shadow_candidate_wins":candidate_wins,
                       "shadow_candidate_losses":len(settled_candidates)-candidate_wins,
                       "shadow_candidate_quote_net_units":round(candidate_profit,4),
                       "shadow_candidate_quote_roi_percent":round(candidate_profit/len(settled_candidates)*100,4) if settled_candidates else None,
                       "alerts_enabled":False},
            "last_report_date":report.get("as_of_date")}
