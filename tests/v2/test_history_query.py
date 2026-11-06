from datetime import date, datetime, timedelta, timezone

from veltrix_v2.domain.contracts import HistoryState
from veltrix_v2.history.contracts import HistoricalMatch, TeamHistoryQuery
from veltrix_v2.history.query import select_team_history


CUTOFF = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def match(index, *, day, home="team-1", away="team-2", squad="senior_men", competition="comp-1"):
    kickoff = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    return HistoricalMatch(
        historical_match_id=f"hm-{index}", canonical_fixture_id=f"fx-{index}",
        canonical_competition_id=competition, squad_category=squad,
        home_team_id=home, away_team_id=away, kickoff_at_utc=kickoff,
        home_goals=index % 4, away_goals=(index + 1) % 3,
        source_record_ids=(f"src-{index}",),
        provider_fixture_refs=(("provider-a", "source-a", f"fixture-{index}"),),
    )


def query(**kwargs):
    values = {
        "canonical_team_id": "team-1", "squad_category": "senior_men",
        "cutoff_at_utc": CUTOFF, "window_start_date": date(2026, 1, 1),
        "competition_ids": (), "max_matches": 10, "minimum_matches": 5,
    }
    values.update(kwargs)
    return TeamHistoryQuery(**values)


def test_selects_only_matches_strictly_before_cutoff():
    rows = [match(i, day=f"2026-11-0{i}T10:00:00") for i in range(1, 7)]
    rows.append(match(7, day="2026-11-06T09:00:00"))
    result = select_team_history(rows, query())
    assert result.state is HistoryState.FOUND
    assert all(item.kickoff_at_utc < CUTOFF for item in result.matches)
    assert "src-7" not in result.evidence_ids


def test_history_is_sorted_chronologically():
    rows = [
        match(1, day="2026-11-03T10:00:00"),
        match(2, day="2026-11-01T10:00:00"),
        match(3, day="2026-11-02T10:00:00"),
        match(4, day="2026-11-04T10:00:00"),
        match(5, day="2026-11-05T10:00:00"),
    ]
    result = select_team_history(rows, query())
    assert [item.historical_match_id for item in result.matches] == ["hm-2", "hm-3", "hm-1", "hm-4", "hm-5"]


def test_insufficient_history_is_explicit():
    rows = [match(i, day=f"2026-11-0{i}T10:00:00") for i in range(1, 4)]
    result = select_team_history(rows, query())
    assert result.state is HistoryState.INSUFFICIENT_COVERAGE
    assert result.total_match_count == 3


def test_not_found_is_distinct_from_insufficient_coverage():
    result = select_team_history([], query())
    assert result.state is HistoryState.NOT_FOUND


def test_squad_category_conflict_is_quarantined():
    rows = [match(i, day=f"2026-11-0{i}T10:00:00", squad="women") for i in range(1, 6)]
    result = select_team_history(rows, query())
    assert result.state is HistoryState.IDENTITY_MISMATCH
    assert result.reason_code == "SQUAD_CATEGORY_CONFLICT"


def test_competition_filter_prevents_cross_competition_history():
    rows = [
        match(i, day=f"2026-11-0{i}T10:00:00", competition="comp-2")
        for i in range(1, 7)
    ]
    result = select_team_history(rows, query(competition_ids=("comp-1",)))
    assert result.state is HistoryState.NOT_FOUND


def test_max_matches_keeps_most_recent_but_returns_them_chronologically():
    rows = [match(i, day=f"2026-10-{i + 20:02d}T10:00:00") for i in range(1, 9)]
    result = select_team_history(rows, query(max_matches=5, minimum_matches=5))
    assert [item.historical_match_id for item in result.matches] == [
        "hm-4", "hm-5", "hm-6", "hm-7", "hm-8"
    ]
    assert result.total_match_count == 8


def test_matches_after_cutoff_never_enter_features():
    future = match(1, day="2026-11-06T10:00:00")
    result = select_team_history([future], query())
    assert result.state is HistoryState.NOT_FOUND


def test_history_window_date_is_interpreted_in_utc():
    local_offset_match = HistoricalMatch(
        historical_match_id="hm-offset", canonical_fixture_id="fx-offset",
        canonical_competition_id="comp-1", squad_category="senior_men",
        home_team_id="team-1", away_team_id="team-2",
        kickoff_at_utc=datetime.fromisoformat("2026-01-01T00:30:00+02:00"),
        home_goals=1, away_goals=0, source_record_ids=("src-offset",),
        provider_fixture_refs=(("provider-a", "source-a", "fixture-offset"),),
    )
    result = select_team_history(
        [local_offset_match],
        query(window_start_date=date(2026, 1, 1)),
    )
    assert result.state is HistoryState.NOT_FOUND
