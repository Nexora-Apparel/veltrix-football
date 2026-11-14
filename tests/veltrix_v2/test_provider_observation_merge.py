from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest

from veltrix_v2.data.provider_observation_merge import merge_certified_observations
from veltrix_v2.models.poisson import MatchObservation

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)
HASH_A = "a" * 64
HASH_B = "b" * 64


def observation(provider="5DollarFootballAPI", *, score=(2, 1), fixture="fx-1",
                payload=HASH_A, available=None, recorded=None):
    return MatchObservation(
        fixture_id=fixture, competition_id="comp-1",
        home_team_id="home-1", away_team_id="away-1",
        kickoff_at=NOW - timedelta(days=3),
        available_at=available or NOW - timedelta(days=2),
        recorded_at=recorded or NOW - timedelta(days=1),
        home_goals=score[0], away_goals=score[1],
        provider=provider, source_id=provider.lower(),
        availability_basis="provider_evidence_manifest_v1",
        point_in_time_certifiable=True, payload_sha256=payload,
        rights_approval_id=f"approval-{provider}",
        evidence_manifest_sha256=HASH_A, capture_evidence_sha256=HASH_B,
    )


def test_identical_cross_provider_results_are_counted_once_with_both_provenances():
    a = observation()
    b = observation("ProviderB", payload=HASH_B, available=NOW - timedelta(hours=12), recorded=NOW - timedelta(hours=6))
    report = merge_certified_observations([a, b])
    assert len(report.observations) == 1
    assert report.duplicate_observation_count == 1
    assert report.observations[0].provider == "5DollarFootballAPI"
    assert len(report.source_evidence_by_fixture[0][1]) == 2


def test_explicit_source_priority_precedes_availability_order():
    a = observation("ProviderA", payload=HASH_A, available=NOW - timedelta(hours=1), recorded=NOW)
    b = observation("ProviderB", payload=HASH_B, available=NOW - timedelta(days=1), recorded=NOW - timedelta(hours=12))
    report = merge_certified_observations([a, b], source_priority={"ProviderB": 1, "ProviderA": 2})
    assert report.observations[0].provider == "ProviderB"


def test_conflicting_scores_quarantine_entire_fixture_group():
    a = observation()
    b = observation("ProviderB", score=(0, 3), payload=HASH_B)
    report = merge_certified_observations([a, b])
    assert report.observations == ()
    assert report.conflicting_fixture_ids == ("fx-1",)


def test_identity_conflict_quarantines_entire_fixture_group():
    a = observation()
    b = replace(observation("ProviderB", payload=HASH_B), home_team_id="wrong-home")
    report = merge_certified_observations([a, b])
    assert report.observations == ()
    assert report.conflicting_fixture_ids == ("fx-1",)


def test_uncertified_or_manifest_unlinked_observations_are_rejected():
    good = observation()
    bad = replace(good, fixture_id="fx-2", point_in_time_certifiable=False)
    missing_hash = replace(good, fixture_id="fx-3", capture_evidence_sha256=None)
    report = merge_certified_observations([good, bad, missing_hash])
    assert len(report.observations) == 1
    assert report.rejected_uncertified_count == 2


def test_duplicate_fixture_from_same_provider_is_not_double_counted():
    a = observation()
    report = merge_certified_observations([a, a])
    assert len(report.observations) == 1
    assert report.duplicate_observation_count == 1


def test_invalid_source_priority_fails_closed():
    with pytest.raises(ValueError, match="SOURCE_PRIORITY_MAP_INVALID"):
        merge_certified_observations([], source_priority={"ProviderA": True})

def test_result_available_before_kickoff_is_rejected():
    invalid = observation(available=NOW - timedelta(days=4))
    report = merge_certified_observations([invalid])
    assert report.observations == ()
    assert report.rejected_uncertified_count == 1

def test_truthy_non_boolean_certification_is_rejected():
    invalid = replace(observation(), point_in_time_certifiable=1)
    report = merge_certified_observations([invalid])
    assert report.observations == ()
    assert report.rejected_uncertified_count == 1
