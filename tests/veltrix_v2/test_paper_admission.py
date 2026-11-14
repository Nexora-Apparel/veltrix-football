from dataclasses import replace
from datetime import datetime, timedelta, timezone

from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose, SourceApproval
from veltrix_v2.ledger.admission import admit_shadow_forecasts
from veltrix_v2.models.engine import BatchForecastReport, ForecastRecord, PredictionTarget
from veltrix_v2.models.poisson import MatchObservation, PoissonPrediction

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)
APPROVAL = SourceApproval(
    approval_id="approval-1", provider="TestProvider", source_id="testsrc",
    competition_scope="comp-1", data_type="fixtures_and_results",
    status=ApprovalStatus.APPROVED,
    permitted_uses=frozenset({
        DataUsePurpose.COLLECTION, DataUsePurpose.CACHE,
        DataUsePurpose.STORAGE, DataUsePurpose.MODEL_TRAINING,
    }),
    commercial_use_allowed=True, terms_url="https://example.test/terms",
    terms_version="v1", evidence_uri="https://example.test/evidence",
    evidence_sha256="a" * 64, rights_basis="WRITTEN_PERMISSION",
    reviewed_at_utc=NOW - timedelta(days=10), reviewer_id="reviewer",
    valid_from_utc=NOW - timedelta(days=10),
)


def _fixture_set(*, certifiable=True, target_rights="approval-1"):
    cutoff = NOW
    kickoff = NOW + timedelta(days=2)
    history = MatchObservation(
        fixture_id="history-1", competition_id="testsrc:comp-1",
        home_team_id="testsrc:team-a", away_team_id="testsrc:team-b",
        kickoff_at=NOW - timedelta(days=5),
        available_at=NOW - timedelta(days=4),
        recorded_at=NOW - timedelta(days=4),
        home_goals=2, away_goals=0,
        provider="TestProvider", source_id="testsrc",
        availability_basis="provider_timestamp",
        point_in_time_certifiable=certifiable,
        payload_sha256="b" * 64, rights_approval_id="approval-1",
    )
    target = PredictionTarget(
        fixture_id="testsrc:fixture-1", competition_id="testsrc:comp-1",
        home_team_id="testsrc:team-a", away_team_id="testsrc:team-b",
        kickoff_at=kickoff, provider="TestProvider", source_id="testsrc",
        source_fixture_id="fixture-1", retrieved_at=cutoff - timedelta(minutes=5),
        payload_sha256="c" * 64, rights_approval_id=target_rights,
    )
    model = PoissonPrediction(
        model_version="poisson-v1", cutoff_at=cutoff,
        expected_home_goals=1.5, expected_away_goals=0.8,
        home_win=0.5, draw=0.3, away_win=0.2,
        btts_yes=0.45, over_2_5=0.42,
        evidence_match_count=1, home_team_match_count=1,
        away_team_match_count=1, sample_floor_met=False,
        publishable=False, publication_reason="INSUFFICIENT_EVIDENCE_FOR_MODEL_REVIEW",
        recency_half_life_days=None, dixon_coles_rho=0.0,
    )
    forecast = ForecastRecord(
        fixture_id=target.fixture_id, competition_id=target.competition_id,
        kickoff_at=target.kickoff_at, cutoff_at=cutoff,
        provider=target.provider, source_id=target.source_id,
        home_team_name="A", away_team_name="B", model=model,
    )
    report = BatchForecastReport(
        cutoff_at=cutoff, requested_target_count=1, forecast_count=1,
        skipped_duplicate_target_ids=0, skipped_invalid_targets=0,
        skipped_targets_not_yet_known=0, skipped_no_history=0,
        skipped_capacity=0, forecasts=(forecast,),
    )
    return report, target, [history]


def test_admits_prospective_shadow_forecast_with_source_and_history_rights():
    report, target, history = _fixture_set()
    admitted = admit_shadow_forecasts(
        report, [target], history, source_approvals={"approval-1": APPROVAL},
        forecasted_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=2),
        model_artifact_sha256="d" * 64, feature_set_sha256="e" * 64,
    )
    assert len(admitted.admitted) == 1
    assert not admitted.rejected
    prediction = admitted.admitted[0]
    assert prediction.point_in_time_certifiable is True
    assert prediction.recorded_at < prediction.kickoff_at
    assert len(prediction.evidence_sha256) == 64


def test_rejects_non_certifiable_training_evidence():
    report, target, history = _fixture_set(certifiable=False)
    result = admit_shadow_forecasts(
        report, [target], history, source_approvals={"approval-1": APPROVAL},
        forecasted_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=2),
        model_artifact_sha256="d" * 64, feature_set_sha256="e" * 64,
    )
    assert not result.admitted
    assert result.rejected[0].reason_code == "MODEL_EVIDENCE_COUNT_MISMATCH"


def test_rejects_target_without_use_time_rights():
    report, target, history = _fixture_set(target_rights="missing")
    result = admit_shadow_forecasts(
        report, [target], history, source_approvals={"approval-1": APPROVAL},
        forecasted_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=2),
        model_artifact_sha256="d" * 64, feature_set_sha256="e" * 64,
    )
    assert not result.admitted
    assert result.rejected[0].reason_code == "SOURCE_APPROVAL_MISSING"


def test_rejects_late_recording_after_kickoff():
    report, target, history = _fixture_set()
    result = admit_shadow_forecasts(
        report, [target], history, source_approvals={"approval-1": APPROVAL},
        forecasted_at=target.kickoff_at + timedelta(minutes=1),
        recorded_at=target.kickoff_at + timedelta(minutes=2),
        model_artifact_sha256="d" * 64, feature_set_sha256="e" * 64,
    )
    assert not result.admitted
    assert result.rejected[0].reason_code == "TARGET_NOT_KNOWN_AND_FUTURE_AT_RECORDING"


def test_manifest_linked_observation_requires_both_capture_hashes():
    report, target, history = _fixture_set()
    manifest_only = replace(
        history[0],
        availability_basis="provider_evidence_manifest_v1",
        evidence_manifest_sha256="f" * 64,
        capture_evidence_sha256=None,
    )
    result = admit_shadow_forecasts(
        report, [target], [manifest_only],
        source_approvals={"approval-1": APPROVAL},
        forecasted_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=2),
        model_artifact_sha256="d" * 64, feature_set_sha256="e" * 64,
    )
    assert not result.admitted
    assert result.rejected[0].reason_code == "TRAINING_CAPTURE_EVIDENCE_HASH_MISSING"


def test_manifest_linked_observation_is_admitted_with_both_capture_hashes():
    report, target, history = _fixture_set()
    linked = replace(
        history[0],
        availability_basis="provider_evidence_manifest_v1",
        evidence_manifest_sha256="f" * 64,
        capture_evidence_sha256="a" * 64,
    )
    result = admit_shadow_forecasts(
        report, [target], [linked],
        source_approvals={"approval-1": APPROVAL},
        forecasted_at=NOW + timedelta(minutes=1),
        recorded_at=NOW + timedelta(minutes=2),
        model_artifact_sha256="d" * 64, feature_set_sha256="e" * 64,
    )
    assert len(result.admitted) == 1
    assert not result.rejected
