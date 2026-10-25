from app.historical_data import completed_fixture_rows, add_leakage_safe_rolling_features, validate_date_range
import pytest

def fx(i,d,h,a,hg,ag,status="FT"):
 return {"fixture":{"id":i,"date":d,"status":{"short":status}},"league":{"id":39,"name":"Example","season":2025},"teams":{"home":{"id":h,"name":str(h)},"away":{"id":a,"name":str(a)}},"goals":{"home":hg,"away":ag}}

def test_only_completed_valid_matches_sorted():
 rows=completed_fixture_rows([fx(2,"2025-01-02T15:00:00+00:00",1,2,1,0),fx(3,"2025-01-03T15:00:00+00:00",1,3,None,None,"NS"),fx(1,"2025-01-01T15:00:00+00:00",2,3,2,2)])
 assert [r["fixture_id"] for r in rows]==[1,2]

def test_features_use_only_prior_results():
 rows=completed_fixture_rows([fx(1,"2025-01-01T15:00:00+00:00",1,2,2,0),fx(2,"2025-01-04T15:00:00+00:00",1,3,0,1),fx(3,"2025-01-08T15:00:00+00:00",1,2,3,1)])
 out=add_leakage_safe_rolling_features(rows,5)
 assert out[0]["home_prior_matches"]==0 and out[0]["home_avg_goals_for"] is None
 assert out[1]["home_avg_goals_for"]==pytest.approx(2)
 assert out[2]["home_avg_goals_for"]==pytest.approx(1)
 assert out[2]["away_avg_goals_for"]==pytest.approx(0)

def test_window_and_dates_validated():
 with pytest.raises(ValueError): add_leakage_safe_rolling_features([],0)
 with pytest.raises(ValueError): validate_date_range("2025-02-01","2025-01-01")
 with pytest.raises(ValueError): validate_date_range("2024-01-01","2025-01-02")



def test_highlightly_history_range_is_capped_at_seven_calendar_days():
 assert validate_date_range("2026-10-01", "2026-10-07") == ("2026-10-01", "2026-10-07")
 with pytest.raises(ValueError, match="7 calendar days"):
  validate_date_range("2026-10-01", "2026-10-08")
