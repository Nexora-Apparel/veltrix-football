from datetime import date, datetime, timedelta, timezone

from veltrix_v2.ingestion.budget import QuotaSnapshot
from veltrix_v2.ingestion.ports import ProviderRequestSpec
from veltrix_v2.ingestion.preflight import evaluate_ingestion_preflight
from veltrix_v2.ingestion.provider_access import ProviderAccessProfile, ProviderAccessStatus


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=timezone.utc)


def request():
    return ProviderRequestSpec(
        request_id="req-1", provider="5DollarFootballAPI", endpoint="fixtures",
        data_class="fixtures", quota_scope="daily", quota_units=2,
        competition_ids=("league-1",), history_start_date=None,
        idempotency_key="req-1", parameters={"date": "2026-11-06"},
    )


def profile(snapshot_id="quota-1"):
    return ProviderAccessProfile(
        provider="5DollarFootballAPI", account_plan="verified-test-plan",
        verified_at_utc=NOW - timedelta(minutes=5),
        verification_evidence_ref="account-audit-1",
        supported_competition_ids=frozenset({"league-1"}),
        available_data_classes=frozenset({"fixtures"}),
        history_start_date=date(2026, 1, 1),
        quota_snapshot_id=snapshot_id,
    )


def quota(provider="5DollarFootballAPI", scope="daily", snapshot_id="quota-1"):
    return QuotaSnapshot(
        provider=provider, quota_scope=scope, unit_name="requests",
        snapshot_id=snapshot_id, measured_at_utc=NOW - timedelta(minutes=1),
        period_ends_at_utc=NOW + timedelta(hours=12),
        limit_units=100, used_units=10, reserved_units=5,
    )


def test_preflight_allows_matching_verified_account_and_quota():
    result = evaluate_ingestion_preflight(profile(), quota(), request(), now_utc=NOW)
    assert result.allowed is True
    assert result.reason_code == "INGESTION_PREFLIGHT_ALLOWED"


def test_preflight_blocks_missing_account_profile():
    result = evaluate_ingestion_preflight(None, quota(), request(), now_utc=NOW)
    assert result.allowed is False
    assert result.provider_access.status is ProviderAccessStatus.PROFILE_MISSING


def test_preflight_blocks_unsupported_competition():
    unsupported = ProviderAccessProfile(
        provider="5DollarFootballAPI", account_plan="verified-test-plan",
        verified_at_utc=NOW, verification_evidence_ref="account-audit-1",
        supported_competition_ids=frozenset(), available_data_classes=frozenset({"fixtures"}),
        history_start_date=None, quota_snapshot_id="quota-1",
    )
    result = evaluate_ingestion_preflight(unsupported, quota(), request(), now_utc=NOW)
    assert result.allowed is False
    assert result.provider_access.status is ProviderAccessStatus.COMPETITION_UNSUPPORTED


def test_preflight_blocks_provider_or_scope_mismatch():
    result = evaluate_ingestion_preflight(
        profile(), quota(scope="monthly"), request(), now_utc=NOW
    )
    assert result.allowed is False
    assert result.reason_code == "QUOTA_PROVIDER_OR_SCOPE_MISMATCH"


def test_preflight_requires_quota_snapshot_linked_to_account_profile():
    result = evaluate_ingestion_preflight(
        profile("quota-old"), quota(snapshot_id="quota-new"), request(), now_utc=NOW
    )
    assert result.allowed is False
    assert result.reason_code == "QUOTA_PROFILE_SNAPSHOT_MISMATCH"


def test_preflight_blocks_missing_quota_snapshot():
    result = evaluate_ingestion_preflight(profile(), None, request(), now_utc=NOW)
    assert result.allowed is False
    assert result.quota.reason_code == "QUOTA_SNAPSHOT_MISSING"


def test_preflight_blocks_stale_quota_snapshot():
    stale = QuotaSnapshot(
        provider="5DollarFootballAPI", quota_scope="daily", unit_name="requests",
        snapshot_id="quota-1", measured_at_utc=NOW - timedelta(days=2),
        period_ends_at_utc=NOW + timedelta(hours=12),
        limit_units=100, used_units=10, reserved_units=5,
    )
    result = evaluate_ingestion_preflight(profile(), stale, request(), now_utc=NOW)
    assert result.allowed is False
    assert result.reason_code == "QUOTA_SNAPSHOT_STALE"



def test_preflight_blocks_account_profile_for_different_provider():
    wrong_provider = ProviderAccessProfile(
        provider="different-provider", account_plan="verified-test-plan",
        verified_at_utc=NOW, verification_evidence_ref="account-audit-1",
        supported_competition_ids=frozenset({"league-1"}),
        available_data_classes=frozenset({"fixtures"}),
        history_start_date=date(2026, 1, 1), quota_snapshot_id="quota-1",
    )
    result = evaluate_ingestion_preflight(
        wrong_provider, quota(), request(), now_utc=NOW
    )
    assert result.allowed is False
    assert result.reason_code == "ACCOUNT_PROVIDER_MISMATCH"
