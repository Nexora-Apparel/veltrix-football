from app.value_evidence_ledger import merge_evidence_ledger, _clv

def report(ts, price=2.2):
    return {"as_of_date":"2026-10-31","predictions":[{
      "fixture_id":123,"kickoff_local":"2026-11-01T16:00:00+00:00","competition":"League",
      "home_team":"Home","away_team":"Away","model":"test",
      "value_intelligence":{"snapshot_fetched_at":ts,"markets":{"BTTS":{
       "model_probabilities":{"yes":.6,"no":.4},"market_consensus_probabilities":{"yes":.5,"no":.5},
       "conservative_screening_probabilities":{"yes":.55,"no":.45},
       "bookmaker_quotes":[{"bookmaker":"Book","last_update":ts,"odds":{"yes":price,"no":1.8}}]}}}
    }]}

def test_duplicate_observations_are_suppressed():
    a=merge_evidence_ledger(None,report("2026-10-31T10:00:00+00:00"))
    b=merge_evidence_ledger(a,report("2026-10-31T10:00:00+00:00"))
    assert b["summary"]["observations_total"]==2
    assert b["summary"]["observations_added"]==0

def test_clv_sign_positive_when_early_price_exceeds_later_price():
    assert _clv(2.2,2.0)>0
    assert _clv(1.9,2.1)<0

def test_single_snapshot_does_not_invent_open_or_close():
    ledger=merge_evidence_ledger(None,report("2026-10-31T10:00:00+00:00"))
    assert all(x["opening_odds"] is None for x in ledger["price_series"])
    assert all(x["closing_odds"] is None for x in ledger["price_series"])
    assert ledger["release_status"]=="LOCKED_SHADOW_MODE"

def test_second_timestamp_builds_provisional_clv_not_closing_line():
    a=merge_evidence_ledger(None,report("2026-10-31T10:00:00+00:00",2.2))
    b=merge_evidence_ledger(a,report("2026-10-31T11:00:00+00:00",2.0))
    yes=next(x for x in b["price_series"] if x["selection"]=="yes")
    assert yes["observations"]==2 and yes["clv_probability_points"]>0
    assert yes["closing_odds"] is None
