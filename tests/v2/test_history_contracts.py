from datetime import date, datetime, timezone

import pytest

from veltrix_v2.domain.contracts import HistoryState
from veltrix_v2.history.contracts import (
    HistoricalMatch,
    HistoryEvidenceResult,
    IncrementalSyncPlan,
    SyncWatermark,
    TeamHistoryQuery,
)


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def match():
    return HistoricalMatch(
        historical_match_id="hm-1", canonical_fixture_id="fx-1",
        canonical_competition_id="comp-1", squad_category="senior_men", home_team_id="team-1",
        away_team_id="team-2", kickoff_at_utc=datetime(2026, 11, 1, 15, 0, tzinfo=timezone.utc),
        home_goals=2, away_goals=1, source_record_ids=("src-1",),
        provider_fixture_refs=(("provider-a", "source-a", "fixture-a"),),
    )


def test_historical_match_requires_provenance():
    with pytest.raises(ValueError, match="source-record provenance"):
        HistoricalMatch(
            historical_match_id="hm-1", canonical_fixture_id="fx-1",
            canonical_competition_id="comp-1", squad_category="senior_men", home_team_id="t1", away_team_id="t2",
            kickoff_at_utc=NOW, home_goals=0, away_goals=0,
            source_record_ids=(), provider_fixture_refs=(("p", "s", "f"),),
        )


def test_historical_match_preserves_provider_fixture_ids():
    item = match()
    assert item.provider_fixture_refs[0] == ("provider-a", "source-a", "fixture-a")


def test_historical_match_rejects_naive_kickoff():
    with pytest.raises(ValueError, match="timezone-aware"):
        HistoricalMatch(
            historical_match_id="hm-1", canonical_fixture_id="fx-1",
            canonical_competition_id="comp-1", squad_category="senior_men", home_team_id="t1", away_team_id="t2",
            kickoff_at_utc=datetime(2026, 11, 1), home_goals=0, away_goals=0,
            source_record_ids=("src-1",), provider_fixture_refs=(("p", "s", "f"),),
        )


def test_team_history_query_requires_pre_cutoff_window():
    with pytest.raises(ValueError, match="before the cutoff"):
        TeamHistoryQuery(
            canonical_team_id="team-1", squad_category="senior_men",
            cutoff_at_utc=NOW, window_start_date=NOW.date(),
            competition_ids=(), max_matches=10,
        )


def test_team_history_query_rejects_zero_limit():
    with pytest.raises(ValueError, match="max_matches"):
        TeamHistoryQuery(
            canonical_team_id="team-1", squad_category="senior_men",
            cutoff_at_utc=NOW, window_start_date=date(2026, 1, 1),
            competition_ids=(), max_matches=0,
        )


def test_found_history_requires_at_least_one_match():
    with pytest.raises(ValueError, match="at least one"):
        HistoryEvidenceResult(
            canonical_team_id="team-1", state=HistoryState.FOUND,
            matches=(), total_match_count=0, evidence_ids=(), reason_code="FOUND",
        )


def test_not_found_history_cannot_contain_matches():
    with pytest.raises(ValueError, match="NOT_FOUND"):
        HistoryEvidenceResult(
            canonical_team_id="team-1", state=HistoryState.NOT_FOUND,
            matches=(match(),), total_match_count=1,
            evidence_ids=("src-1",), reason_code="NOT_FOUND",
        )


def test_query_failed_is_explicit_and_may_not_claim_found_matches():
    result = HistoryEvidenceResult(
        canonical_team_id="team-1", state=HistoryState.QUERY_FAILED,
        matches=(), total_match_count=0, evidence_ids=(),
        reason_code="REPOSITORY_TIMEOUT",
    )
    assert result.state is HistoryState.QUERY_FAILED


def test_sync_watermark_requires_timezone_and_version():
    with pytest.raises(ValueError, match="timezone-aware"):
        SyncWatermark(
            provider="p", data_class="fixtures", scope="league-1",
            cursor=None, updated_at_utc=datetime(2026, 11, 6), version=0,
        )


def test_incremental_sync_plan_is_bounded_and_forward_only():
    plan = IncrementalSyncPlan(
        provider="p", data_class="fixtures", scope="league-1",
        lower_bound_utc=datetime(2026, 11, 1, tzinfo=timezone.utc),
        upper_bound_utc=NOW, max_pages=3, page_size=100,
        expected_watermark_version=4,
    )
    assert plan.max_pages == 3
    assert plan.page_size == 100


def test_incremental_sync_plan_rejects_reversed_window():
    with pytest.raises(ValueError, match="positive duration"):
        IncrementalSyncPlan(
            provider="p", data_class="fixtures", scope="league-1",
            lower_bound_utc=NOW, upper_bound_utc=NOW,
            max_pages=1, page_size=100, expected_watermark_version=0,
        )


def test_multi_source_history_requires_exact_provider_record_pairings():
    with pytest.raises(ValueError, match="every source record"):
        HistoricalMatch(
            historical_match_id="hm-2", canonical_fixture_id="fx-2",
            canonical_competition_id="comp-1", squad_category="senior_men",
            home_team_id="team-1", away_team_id="team-2", kickoff_at_utc=NOW,
            home_goals=1, away_goals=0, source_record_ids=("src-1","src-2"),
            provider_fixture_refs=(("provider-a","source-a","fixture-a"),),
            provider_source_record_refs=(("src-1","provider-a","source-a","fixture-a"),),
        )


def test_multiple_source_versions_preserve_provider_fixture_provenance():
    item=HistoricalMatch(
        historical_match_id="hm-3", canonical_fixture_id="fx-3",
        canonical_competition_id="comp-1", squad_category="senior_men",
        home_team_id="team-1", away_team_id="team-2", kickoff_at_utc=NOW,
        home_goals=1, away_goals=0, source_record_ids=("src-1","src-2"),
        provider_fixture_refs=(("provider-a","source-a","fixture-a"),),
        provider_source_record_refs=(
            ("src-1","provider-a","source-a","fixture-a"),
            ("src-2","provider-a","source-a","fixture-a"),
        ),
    )
    assert len(item.provider_source_record_refs)==2
