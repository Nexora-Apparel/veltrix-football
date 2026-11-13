from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.providers.odds_api_v4.budget import CreditBudget
from veltrix_v2.providers.odds_api_v4.orchestrator import (
    CaptureRequest, FixtureBoundary, RightsEvidence, build_manifest, evaluate_preflight,
)


NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)


def request(**changes):
    values = dict(
        request_id="req-1", run_id="run-1", provider="the_odds_api",
        api_version="v4", endpoint_class="bulk_odds", sport_key="soccer_epl",
        competition_keys=("EPL",),
        fixture_boundaries=(FixtureBoundary(
            "fixture-1", "event-1", NOW, NOW + timedelta(hours=2)
        ),),
        markets=("h2h", "totals"), regions=("uk",),
        prediction_use="derived_features", expected_terms_version="terms-2026-01",
        rights_evaluated_at=NOW, created_at=NOW, max_attempts=2, timeout_seconds=10,
    )
    values.update(changes)
    return CaptureRequest(**values)


def rights(**changes):
    values = dict(
        provider="the_odds_api", status="APPROVED",
        accepted_terms_version="terms-2026-01", terms_evidence_id="terms-evidence-1",
        approval_evidence_id="approval-1", effective_at=NOW - timedelta(days=2),
        recorded_at=NOW - timedelta(days=1), valid_until=NOW + timedelta(days=30),
        competitions=("EPL",), markets=("h2h", "totals", "btts"),
        regions=("uk",), permitted_uses=("derived_features",),
    )
    values.update(changes)
    return RightsEvidence(**values)


def budget(**changes):
    values = dict(monthly_allowance=100, provider_remaining=50,
                  monthly_hard_cap=80, per_run_hard_cap=20,
                  month_committed=0, run_committed=0)
    values.update(changes)
    return CreditBudget(**values)


def test_manifest_hash_is_deterministic_and_scope_order_independent():
    first = build_manifest(request())
    second = build_manifest(request(markets=("totals", "h2h"), regions=("uk",)))
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.request_fingerprint == second.request_fingerprint
    assert "api_key" not in repr(first).casefold()


def test_manifest_rejects_naive_timestamps_and_cutoff_after_kickoff():
    with pytest.raises(ValueError, match="RIGHTS_EVALUATED_AT_MUST_BE_TIMEZONE_AWARE"):
        build_manifest(request(rights_evaluated_at=datetime(2026, 11, 13, 12)))
    boundary = FixtureBoundary("fixture-1", "event-1", NOW + timedelta(hours=3), NOW + timedelta(hours=2))
    with pytest.raises(ValueError, match="PREDICTION_CUTOFF_NOT_BEFORE_KICKOFF"):
        build_manifest(request(fixture_boundaries=(boundary,)))


def test_preflight_approves_exact_scoped_evidence_and_budget():
    manifest = build_manifest(request())
    result = evaluate_preflight(manifest, rights(), budget(), {"fixture-1": "event-1"})
    assert result.allowed
    assert result.state == "PREFLIGHT_APPROVED"
    assert result.estimated_credits == 2


def test_preflight_blocks_missing_terms_and_approval_evidence():
    manifest = build_manifest(request())
    missing = replace(rights(), terms_evidence_id="")
    result = evaluate_preflight(manifest, missing, budget(), {"fixture-1": "event-1"})
    assert not result.allowed
    assert "ACCOUNT_TERMS_EVIDENCE_MISSING" in result.reason_codes
    missing_approval = replace(rights(), approval_evidence_id="")
    result = evaluate_preflight(manifest, missing_approval, budget(), {"fixture-1": "event-1"})
    assert "APPROVAL_EVIDENCE_ID_MISSING" in result.reason_codes


def test_preflight_blocks_terms_version_mismatch_provisional_and_expired_rights():
    manifest = build_manifest(request())
    mismatch = evaluate_preflight(manifest, replace(rights(), accepted_terms_version="other"), budget(), {"fixture-1": "event-1"})
    assert "ACCOUNT_TERMS_VERSION_MISMATCH" in mismatch.reason_codes
    provisional = evaluate_preflight(manifest, replace(rights(), status="PROVISIONAL"), budget(), {"fixture-1": "event-1"})
    assert "RIGHTS_NOT_APPROVED" in provisional.reason_codes
    expired = evaluate_preflight(manifest, replace(rights(), valid_until=NOW), budget(), {"fixture-1": "event-1"})
    assert "RIGHTS_NOT_VALID_AT_EVALUATION" in expired.reason_codes


def test_preflight_blocks_scope_and_crosswalk_mismatch():
    manifest = build_manifest(request())
    narrow = replace(rights(), markets=("h2h",))
    result = evaluate_preflight(manifest, narrow, budget(), {"fixture-1": "wrong-event"})
    assert "MARKET_SCOPE_NOT_APPROVED" in result.reason_codes
    assert "EVENT_CROSSWALK_MISMATCH" in result.reason_codes


def test_preflight_blocks_budget_overrun_without_mutating_budget():
    manifest = build_manifest(request())
    original = budget(per_run_hard_cap=1)
    result = evaluate_preflight(manifest, rights(), original, {"fixture-1": "event-1"})
    assert not result.allowed
    assert "PER_RUN_CAP_EXCEEDED" in result.reason_codes
    assert original.run_committed == 0


def test_no_fixture_event_crosswalk_is_accepted_for_discovery_only():
    discovery = request(endpoint_class="events_discovery", fixture_boundaries=(), markets=())
    manifest = build_manifest(discovery)
    result = evaluate_preflight(manifest, rights(), budget(), {})
    assert result.allowed
    assert result.estimated_credits == 0



def test_preflight_rejects_tampered_manifest_fields():
    manifest = build_manifest(request())
    altered = replace(manifest, markets=("btts",))
    result = evaluate_preflight(altered, rights(), budget(), {"fixture-1": "event-1"})
    assert not result.allowed
    assert "MANIFEST_INTEGRITY_INVALID" in result.reason_codes


def test_manifest_rejects_malformed_scope_and_event_odds_fanout():
    with pytest.raises(ValueError, match="MARKET_SCOPE_INVALID"):
        build_manifest(request(markets=(["h2h"],)))
    second = FixtureBoundary("fixture-2", "event-2", NOW, NOW + timedelta(hours=3))
    with pytest.raises(ValueError, match="EVENT_ODDS_REQUIRES_EXACTLY_ONE_EVENT"):
        build_manifest(request(endpoint_class="event_odds", fixture_boundaries=(
            request().fixture_boundaries[0], second
        )))


def test_preflight_rejects_malformed_rights_scope_and_naive_rights_time():
    manifest = build_manifest(request())
    malformed = replace(rights(), markets=(["h2h"],))
    result = evaluate_preflight(manifest, malformed, budget(), {"fixture-1": "event-1"})
    assert "RIGHTS_SCOPE_EVIDENCE_INVALID" in result.reason_codes
    naive = replace(rights(), effective_at=datetime(2026, 11, 12, 12))
    result = evaluate_preflight(manifest, naive, budget(), {"fixture-1": "event-1"})
    assert "RIGHTS_TIMESTAMP_INVALID" in result.reason_codes

def test_manifest_attempt_limit_matches_dispatch_guard_maximum():
    with pytest.raises(ValueError, match="MAX_ATTEMPTS_OUT_OF_RANGE"):
        build_manifest(request(max_attempts=3))
    assert build_manifest(request(max_attempts=2)).max_attempts == 2
