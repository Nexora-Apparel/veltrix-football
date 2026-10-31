from app.value_evidence_ledger import merge_evidence_ledger, _clv

def report(ts, price=2.2):
    return {"as_of_date":"2026-10-31","predictions":[{
      "fixture_id":123,"kickoff_local":"2026-11-01T16:00:00+00:00","competition":"League",
      "home_team":"Home","away_team":"Away","model":"test",
      "value_intelligence":{"snapshot_fetched_at":ts,"markets":{"BTTS":{
       "model_probabilities":{"yes":.6,"no":.4},"market_consensus_probabilities":{"yes":.5,"no":.5},
       "conservative_screening_probabilities":{"yes":.55,"no":.45},
       "bookmaker_quotes":[{"bookmaker":"Book","last_update":ts,"odds":{"yes":price,"no":1.8}}],
       "candidate_quote_keys":[{"bookmaker":"Book","selection":"yes"}],
       "candidates":[{"bookmaker":"Book","selection":"yes","edge":0.1,"expected_value_per_unit":0.2}]}}}
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


def test_completed_result_settles_candidate_and_calculates_quote_level_roi():
    result = {"matches": [{
        "fixture_id": 123, "fixture_status": "FT", "home_goals": 2, "away_goals": 1,
    }]}
    ledger = merge_evidence_ledger(None, report("2026-10-31T10:00:00+00:00"), result)
    yes = next(row for row in ledger["observations"] if row["selection"] == "yes")
    no = next(row for row in ledger["observations"] if row["selection"] == "no")
    assert yes["settlement"]["won"] is True
    assert no["settlement"]["won"] is False
    assert ledger["summary"]["settled_shadow_candidates"] == 1
    assert ledger["summary"]["shadow_candidate_wins"] == 1
    assert ledger["summary"]["shadow_candidate_quote_net_units"] == 1.2
    assert ledger["summary"]["shadow_candidate_quote_roi_percent"] == 120.0


def test_corrected_result_does_not_overwrite_existing_settlement():
    first = {"matches": [{
        "fixture_id": 123, "fixture_status": "FT", "home_goals": 2, "away_goals": 1,
    }]}
    corrected = {"matches": [{
        "fixture_id": 123, "fixture_status": "FT", "home_goals": 0, "away_goals": 1,
    }]}
    ledger = merge_evidence_ledger(None, report("2026-10-31T10:00:00+00:00"), first)
    updated = merge_evidence_ledger(ledger, report("2026-10-31T10:00:00+00:00"), corrected)
    yes = next(row for row in updated["observations"] if row["selection"] == "yes")
    assert yes["settlement"]["home_goals"] == 2
    assert len(updated["settlement_conflicts"]) == 2
    assert all(row["status"] == "RESULT_CONFLICT_REVIEW_REQUIRED" for row in updated["settlement_conflicts"])


def test_legacy_candidate_counts_are_preserved_without_fabricating_settlements():
    previous = {
        "version": "VELTRIX_VALUE_EVIDENCE_V1",
        "observations": [],
        "summary": {"shadow_candidate_observations": 7},
    }
    ledger = merge_evidence_ledger(previous, {"as_of_date": "2026-10-31", "predictions": []})
    assert ledger["summary"]["shadow_candidate_observations"] == 7
    assert ledger["summary"]["legacy_candidate_observations_unannotated"] == 7
    assert ledger["summary"]["settled_shadow_candidates"] == 0
