from datetime import date, datetime, timedelta, timezone

from veltrix_v2.ingestion.provider_access import (
    ProviderAccessProfile,
    ProviderAccessStatus,
    evaluate_provider_access,
)


NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def profile(**overrides):
    values = dict(
        provider="primary-provider",
        account_plan="verified-community",
        verified_at_utc=NOW - timedelta(hours=1),
        verification_evidence_ref="account-plan-export-2026-11-06",
        supported_competition_ids=frozenset({"league-1", "league-2"}),
        available_data_classes=frozenset({"FIXTURES", "RESULTS", "HISTORICAL_RESULTS"}),
        history_start_date=date(2025, 1, 1),
        quota_snapshot_id="quota-2026-11-06",
    )
    values.update(overrides)
    return ProviderAccessProfile(**values)


def evaluate(candidate=None, **overrides):
    values = dict(
        required_competition_ids=frozenset({"league-1"}),
        required_data_class="HISTORICAL_RESULTS",
        required_history_start=date(2025, 6, 1),
        now_utc=NOW,
    )
    values.update(overrides)
    return evaluate_provider_access(candidate, **values)


def test_verified_account_profile_allows_only_covered_workload():
    decision = evaluate(profile())
    assert decision.status is ProviderAccessStatus.AVAILABLE


def test_missing_account_profile_fails_closed():
    decision = evaluate(None)
    assert decision.status is ProviderAccessStatus.PROFILE_MISSING


def test_stale_account_plan_verification_fails_closed():
    decision = evaluate(profile(verified_at_utc=NOW - timedelta(days=8)))
    assert decision.status is ProviderAccessStatus.PROFILE_STALE


def test_future_account_plan_verification_fails_closed():
    decision = evaluate(profile(verified_at_utc=NOW + timedelta(seconds=1)))
    assert decision.status is ProviderAccessStatus.PROFILE_INVALID


def test_missing_competitions_are_reported_explicitly():
    decision = evaluate(
        profile(),
        required_competition_ids=frozenset({"league-1", "league-3"}),
    )
    assert decision.status is ProviderAccessStatus.COMPETITION_UNSUPPORTED
    assert decision.missing_competition_ids == ("league-3",)


def test_unavailable_data_class_is_rejected():
    decision = evaluate(profile(), required_data_class="HISTORICAL_ODDS")
    assert decision.status is ProviderAccessStatus.DATA_CLASS_UNAVAILABLE


def test_history_request_older_than_plan_window_is_rejected():
    decision = evaluate(profile(), required_history_start=date(2024, 1, 1))
    assert decision.status is ProviderAccessStatus.HISTORY_WINDOW_INSUFFICIENT


def test_plan_without_quota_snapshot_is_rejected():
    decision = evaluate(profile(quota_snapshot_id=None))
    assert decision.status is ProviderAccessStatus.QUOTA_SNAPSHOT_MISSING


def test_profile_without_verification_reference_is_rejected():
    decision = evaluate(profile(verification_evidence_ref=""))
    assert decision.status is ProviderAccessStatus.PROFILE_INVALID


def test_timezone_naive_evaluation_clock_is_rejected():
    decision_clock = datetime(2026, 11, 6, 12, 0)
    try:
        evaluate(profile(), now_utc=decision_clock)
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("naive evaluation timestamp must be rejected")
