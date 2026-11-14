from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, FixtureStatus, HistoricalFixture, SourceApproval
from veltrix_v2.data.provider_evidence_capture import (
    ProviderResultCapture,
    ResolvedFixtureCrosswalk,
    capture_provider_result_evidence,
    capture_fivedollar_page_evidence,
    certified_match_observations,
)

from veltrix_v2.data.fivedollar import ParsedFixturePage

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
    assert evidence.rights_approved is True
    assert evidence.rights_approval_id == "approval-5d-epl"
    assert evidence.rights_evidence_sha256 == approval().evidence_sha256
    assert evidence.rights_evaluated_at == evidence.recorded_at

    observations = certified_match_observations(report, [row])
    assert len(observations) == 1
    assert observations[0].fixture_id == "epl:fixture-100"
    assert observations[0].point_in_time_certifiable is True
    assert observations[0].payload_sha256 == evidence.raw_response_sha256
    assert observations[0].availability_basis == "provider_evidence_manifest_v1"
    assert observations[0].evidence_manifest_sha256 == report.manifest.manifest_sha256
    assert observations[0].capture_evidence_sha256 == report.manifest.item_evidence_sha256[0]


def test_missing_source_publication_time_is_not_replaced_by_retrieval_time():
    report = capture_provider_result_evidence([capture(source_published_at=None)])
    evidence = report.observations[0]

    assert evidence.point_in_time_certifiable is False
    assert "SOURCE_PUBLICATION_TIMESTAMP_MISSING" in evidence.reason_codes
    assert evidence.source_published_at is None
    assert certified_match_observations(report, [capture(source_published_at=None)]) == ()


def test_rights_approval_identity_mismatch_is_not_reported_as_approved():
    row = capture(rights_approval=replace(approval(), provider="different-provider"))
    report = capture_provider_result_evidence([row])
    evidence = report.observations[0]
    assert evidence.rights_approved is False
    assert evidence.point_in_time_certifiable is False
    assert evidence.rights_evaluated_at == evidence.recorded_at


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

    naive = capture(kickoff_at=datetime(2026, 11, 14, 11, 0))
    report = capture_provider_result_evidence([naive])
    assert report.observations[0].point_in_time_certifiable is False
    assert "KICKOFF_AT_TIMESTAMP_UNTRUSTED" in report.observations[0].reason_codes


def test_source_timestamp_requires_explicit_basis_and_evidence_hash():
    report = capture_provider_result_evidence([capture(source_timestamp_basis="unknown")])
    evidence = report.observations[0]
    assert evidence.point_in_time_certifiable is False
    assert "SOURCE_TIMESTAMP_BASIS_UNTRUSTED" in evidence.reason_codes


def test_manifest_rejects_mixed_request_clocks():
    first = capture()
    second = capture(
        provider_fixture_id="fx-101",
        provider_home_team_id="team-3",
        provider_away_team_id="team-4",
        requested_at=NOW - timedelta(minutes=22),
        crosswalk=ResolvedFixtureCrosswalk(
            provider="5dollarfootball",
            source_id="5dollarfootball",
            provider_fixture_id="fx-101",
            provider_competition_id="epl",
            provider_home_team_id="team-3",
            provider_away_team_id="team-4",
            canonical_fixture_id="epl:fixture-101",
            canonical_competition_id="5dollarfootball:epl",
            canonical_home_team_id="club-c",
            canonical_away_team_id="club-d",
            mapping_version=1,
            mapping_status="RESOLVED",
            valid_from=NOW - timedelta(days=1),
            evidence_sha256=HASH,
        ),
    )
    with pytest.raises(ValueError, match="MANIFEST_REQUEST_CLOCK_MISMATCH"):
        capture_provider_result_evidence([first, second])


def test_certified_conversion_rejects_payload_substitution():
    row = capture()
    report = capture_provider_result_evidence([row])
    substituted = capture(raw_response=b'{"fixture":"fx-100","score":[9,9]}')
    with pytest.raises(ValueError, match="CAPTURE_EVIDENCE_SOURCE_ROW_MISMATCH"):
        certified_match_observations(report, [substituted])


def test_certified_conversion_rejects_manifest_tampering():
    row = capture()
    report = capture_provider_result_evidence([row])
    altered_manifest = replace(report.manifest, certified_count=0)
    altered_report = replace(report, manifest=altered_manifest)
    with pytest.raises(ValueError, match="CAPTURE_EVIDENCE_MANIFEST_HASH_MISMATCH"):
        certified_match_observations(altered_report, [row])


def test_fivedollar_page_adapter_preserves_non_certifiable_timestamp_gap():
    payload = {
        "id": "fx-5d-1",
        "league": {"id": "4160026622"},
        "teams": {"home": {"id": "101"}, "away": {"id": "102"}},
        "goals": {"home": 1, "away": 0},
    }
    row_hash = sha256(__import__("json").dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    fixture = HistoricalFixture(
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        provider_fixture_id="fx-5d-1",
        provider_competition_id="4160026622",
        provider_home_team_id="101",
        provider_away_team_id="102",
        competition_name="England Premier League",
        home_team_name="Home",
        away_team_name="Away",
        kickoff_at_utc=NOW - timedelta(hours=3),
        season_key="2026",
        status=FixtureStatus.FINISHED,
        home_score=1,
        away_score=0,
        payload=payload,
        payload_sha256=row_hash,
        retrieved_at_utc=NOW - timedelta(minutes=20),
        source_event_time_utc=NOW - timedelta(hours=3),
        available_at_utc=NOW + timedelta(days=1),
        availability_basis="provider_finished_status_conservative_4d",
        point_in_time_certifiable=False,
        rights_approval_id="approval-5d-epl",
    )
    raw = b'{"success":1,"data":[{"id":"fx-5d-1"}]}'
    page = ParsedFixturePage(
        fixtures=(fixture,), page=1, per_page=1, has_more=False,
        response_sha256=sha256(raw).hexdigest(),
        quota_limit=60, quota_remaining=59, quota_reset=None,
    )
    five_dollar_approval = SourceApproval(
        approval_id="approval-5d-epl",
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        competition_scope="4160026622",
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
    crosswalk = ResolvedFixtureCrosswalk(
        provider="5DollarFootballAPI",
        source_id="5dollarfootballapi",
        provider_fixture_id="fx-5d-1",
        provider_competition_id="4160026622",
        provider_home_team_id="101",
        provider_away_team_id="102",
        canonical_fixture_id="epl:fx-5d-1",
        canonical_competition_id="5dollarfootballapi:4160026622",
        canonical_home_team_id="club-a",
        canonical_away_team_id="club-b",
        mapping_version=1,
        mapping_status="RESOLVED",
        valid_from=NOW - timedelta(days=1),
        evidence_sha256=HASH,
    )
    report = capture_fivedollar_page_evidence(
        raw, page,
        endpoint="/api/fixtures",
        request_id="5d-page-1",
        requested_at=NOW - timedelta(minutes=21),
        recorded_at=NOW - timedelta(minutes=19),
        crosswalks={"fx-5d-1": crosswalk},
        rights_approval=five_dollar_approval,
    )
    evidence = report.observations[0]
    assert report.manifest.item_count == 1
    assert report.manifest.certified_count == 0
    assert evidence.available_at is None
    assert evidence.source_published_at is None
    assert "SOURCE_PUBLICATION_TIMESTAMP_MISSING" in evidence.reason_codes
    assert "RESULT_AVAILABILITY_TIMESTAMP_MISSING" in evidence.reason_codes
    assert "REVISION_HISTORY_INCOMPLETE" in evidence.reason_codes

    observed_report = capture_fivedollar_page_evidence(
        raw, page,
        endpoint="/api/fixtures",
        request_id="5d-page-1-observed",
        requested_at=NOW - timedelta(minutes=21),
        recorded_at=NOW - timedelta(minutes=19),
        crosswalks={"fx-5d-1": crosswalk},
        rights_approval=five_dollar_approval,
        prospective_observed=True,
    )
    observed_evidence = observed_report.observations[0]
    assert observed_evidence.point_in_time_certifiable is False
    assert observed_evidence.source_published_at is None
    assert observed_evidence.available_at == observed_evidence.retrieved_at
    assert observed_evidence.availability_timestamp_basis == "collector_first_observed_v1"
    assert observed_evidence.raw_response_sha256 == sha256(raw).hexdigest()
    observed = observed_evidence.to_first_observed_match_observation(
        manifest_sha256=observed_report.manifest.manifest_sha256,
        evidence_sha256=observed_report.manifest.item_evidence_sha256[0],
    )
    assert observed.point_in_time_certifiable is False
    assert observed.availability_basis == "collector_first_observed_v1"
    assert observed.available_at.isoformat() == observed_evidence.retrieved_at
    assert observed.payload_sha256 == sha256(raw).hexdigest()
    assert len(observed.evidence_manifest_sha256) == 64
    assert len(observed.capture_evidence_sha256) == 64


def test_fivedollar_page_adapter_rejects_raw_response_hash_mismatch():
    with pytest.raises(ValueError, match="FIVEDOLLAR_RAW_RESPONSE_HASH_MISMATCH"):
        capture_fivedollar_page_evidence(
            b"wrong", ParsedFixturePage(
                fixtures=(), page=1, per_page=1, has_more=False,
                response_sha256=HASH, quota_limit=60, quota_remaining=59, quota_reset=None,
            ),
            endpoint="/api/fixtures",
            request_id="req",
            requested_at=NOW - timedelta(minutes=1),
            recorded_at=NOW,
            crosswalks={},
            rights_approval=approval(),
        )
