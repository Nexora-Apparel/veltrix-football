from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, SourceApproval
from veltrix_v2.data.provider_evidence_capture import (
    ProviderResultCapture,
    ResolvedFixtureCrosswalk,
    capture_provider_result_evidence,
    certified_match_observations,
)

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 14, 0, tzinfo=UTC)
HASH = sha256(b"evidence").hexdigest()


def approval():
    return SourceApproval(
        approval_id="approval-5d-epl",
        provider="5dollarfootball",
        source_id="5dollarfootball",
        competition_scope="epl",
        data_type="fixtures_and_results",
        status=ApprovalStatus.APPROVED,
        permitted_uses=frozenset({
            DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
            DataUsePurpose.MODEL_TRAINING,
        }),
        commercial_use_allowed=True,
        terms_url="https://provider.invalid/terms",
        terms_version="2026-11",
        evidence_uri="https://evidence.invalid/approval",
        evidence_sha256=HASH,
        rights_basis="OPEN_LICENSE",
        reviewed_at_utc=NOW - timedelta(days=1),
        reviewer_id="reviewer-1",
        valid_from_utc=NOW - timedelta(days=2),
    )


def capture(**overrides):
    values = dict(
        provider="5dollarfootball",
        source_id="5dollarfootball",
        endpoint="/v1/results",
        request_id="req-001",
        provider_fixture_id="fx-100",
        provider_competition_id="epl",
        provider_home_team_id="team-1",
        provider_away_team_id="team-2",
        kickoff_at=NOW - timedelta(hours=3),
        home_goals=2,
        away_goals=1,
        raw_response=b'{"fixture":"fx-100","score":[2,1]}',
        source_published_at=NOW - timedelta(minutes=40),
        source_timestamp_basis="provider_timestamp",
        source_timestamp_evidence_sha256=sha256(b'{"fixture":"fx-100","score":[2,1]}').hexdigest(),
        availability_timestamp_basis="provider_timestamp",
        availability_timestamp_evidence_sha256=sha256(b'{"fixture":"fx-100","score":[2,1]}').hexdigest(),
        source_effective_at=NOW - timedelta(minutes=35),
        available_at=NOW - timedelta(minutes=30),
        retrieved_at=NOW - timedelta(minutes=20),
        recorded_at=NOW - timedelta(minutes=19),
        requested_at=NOW - timedelta(minutes=21),
        revision_history_complete=True,
        crosswalk=ResolvedFixtureCrosswalk(
            provider="5dollarfootball",
            source_id="5dollarfootball",
            provider_fixture_id="fx-100",
            provider_competition_id="epl",
            provider_home_team_id="team-1",
            provider_away_team_id="team-2",
            canonical_fixture_id="epl:fixture-100",
            canonical_competition_id="5dollarfootball:epl",
            canonical_home_team_id="club-a",
            canonical_away_team_id="club-b",
            mapping_version=1,
            mapping_status="RESOLVED",
            valid_from=NOW - timedelta(days=1),
            evidence_sha256=HASH,
        ),
        rights_approval=approval(),
    )
    values.update(overrides)
    return ProviderResultCapture(**values)


def test_capture_builds_raw_hash_manifest_and_certified_model_observation():
    row = capture()
    report = capture_provider_result_evidence([row])
    evidence = report.observations[0]

    assert report.manifest.item_count == 1
    assert report.manifest.certified_count == 1
    assert report.manifest.rejected_count == 0
    assert evidence.raw_response_sha256 == sha256(row.raw_response).hexdigest()
    assert evidence.point_in_time_certifiable is True

    observations = certified_match_observations(report, [row])
    assert len(observations) == 1
    assert observations[0].fixture_id == "epl:fixture-100"
    assert observations[0].point_in_time_certifiable is True
    assert observations[0].payload_sha256 == evidence.raw_response_sha256


def test_missing_source_publication_time_is_not_replaced_by_retrieval_time():
    report = capture_provider_result_evidence([capture(source_published_at=None)])
    evidence = report.observations[0]

    assert evidence.point_in_time_certifiable is False
    assert "SOURCE_PUBLICATION_TIMESTAMP_MISSING" in evidence.reason_codes
    assert evidence.source_published_at is None
    assert certified_match_observations(report, [capture(source_published_at=None)]) == ()


def test_incomplete_revision_history_fails_closed():
    report = capture_provider_result_evidence([capture(revision_history_complete=False)])
    assert report.observations[0].point_in_time_certifiable is False
    assert "REVISION_HISTORY_INCOMPLETE" in report.observations[0].reason_codes


def test_provider_identity_mismatch_in_crosswalk_fails_closed():
    row = capture(crosswalk=ResolvedFixtureCrosswalk(
        provider="other-provider",
        source_id="5dollarfootball",
        provider_fixture_id="fx-100",
        provider_competition_id="epl",
        provider_home_team_id="team-1",
        provider_away_team_id="team-2",
        canonical_fixture_id="epl:fixture-100",
        canonical_competition_id="5dollarfootball:epl",
        canonical_home_team_id="club-a",
        canonical_away_team_id="club-b",
        mapping_version=1,
        mapping_status="RESOLVED",
        valid_from=NOW - timedelta(days=1),
        evidence_sha256=HASH,
    ))
    report = capture_provider_result_evidence([row])
    assert report.observations[0].point_in_time_certifiable is False
    assert "CROSSWALK_PROVIDER_IDENTITY_MISMATCH" in report.observations[0].reason_codes


def test_duplicate_canonical_fixture_identity_invalidates_all_duplicates():
    first = capture()
    second = capture(
        provider_fixture_id="fx-101",
        provider_home_team_id="team-3",
        provider_away_team_id="team-4",
        crosswalk=ResolvedFixtureCrosswalk(
            provider="5dollarfootball",
            source_id="5dollarfootball",
            provider_fixture_id="fx-101",
            provider_competition_id="epl",
            provider_home_team_id="team-3",
            provider_away_team_id="team-4",
            canonical_fixture_id="epl:fixture-100",
            canonical_competition_id="5dollarfootball:epl",
            canonical_home_team_id="club-c",
            canonical_away_team_id="club-d",
            mapping_version=1,
            mapping_status="RESOLVED",
            valid_from=NOW - timedelta(days=1),
            evidence_sha256=HASH,
        ),
    )
    report = capture_provider_result_evidence([first, second])
    assert report.manifest.certified_count == 0
    assert all("DUPLICATE_FIXTURE_IDENTITY" in row.reason_codes for row in report.observations)


def test_manifest_hash_is_deterministic():
    row = capture()
    left = capture_provider_result_evidence([row]).manifest
    right = capture_provider_result_evidence([row]).manifest
    assert left.manifest_sha256 == right.manifest_sha256
    assert left.item_evidence_sha256 == right.item_evidence_sha256


def test_untrusted_timezone_and_result_before_kickoff_fail_closed():
    row = capture(available_at=NOW - timedelta(hours=4))
    report = capture_provider_result_evidence([row])
    assert report.observations[0].point_in_time_certifiable is False
    assert "RESULT_AVAILABLE_BEFORE_KICKOFF" in report.observations[0].reason_codes

    naive = capture(retrieved_at=datetime(2026, 11, 14, 13, 40))
    report = capture_provider_result_evidence([naive])
    assert report.observations[0].point_in_time_certifiable is False
    assert "RETRIEVED_AT_TIMESTAMP_UNTRUSTED" in report.observations[0].reason_codes


def test_source_timestamp_requires_explicit_basis_and_evidence_hash():
    report = capture_provider_result_evidence([capture(source_timestamp_basis="unknown")])
    evidence = report.observations[0]
    assert evidence.point_in_time_certifiable is False
    assert "SOURCE_TIMESTAMP_BASIS_UNTRUSTED" in evidence.reason_codes
