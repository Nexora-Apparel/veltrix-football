from datetime import datetime, timezone
from veltrix_v2.history.contracts import HistoricalMatch
from veltrix_v2.history.coverage import assess_historical_coverage


def match(fixture="f1", team="t1", source="s1"):
    return HistoricalMatch(fixture,fixture,"comp","SENIOR_MEN",team,"t2",
        datetime(2026,1,1,tzinfo=timezone.utc),1,0,(source,),
        (("5DollarFootballAPI","five-dollar",fixture),))


def test_coverage_counts_dates_competitions_teams_and_provenance():
    report=assess_historical_coverage([match(),match("f2","t3","s2")])
    assert report.total_matches==2
    assert report.distinct_competitions==1
    assert report.distinct_teams==3
    assert report.provider_fixture_reference_count==2
    assert report.source_record_reference_count==2


def test_duplicate_canonical_fixture_is_reported_not_silently_hidden():
    report=assess_historical_coverage([match(),match()])
    assert report.duplicate_canonical_fixture_ids==("f1",)


def test_empty_dataset_has_explicit_empty_date_range():
    report=assess_historical_coverage([])
    assert report.total_matches==0
    assert report.first_match_date is None and report.last_match_date is None
