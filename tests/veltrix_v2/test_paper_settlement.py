from dataclasses import replace
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, FixtureStatus, HistoricalFixture, SourceApproval,
)
from veltrix_v2.ledger.paper_predictions import PaperPrediction, ProspectivePaperLedger
from veltrix_v2.ledger.settlement import settle_from_verified_fixture

UTC = timezone.utc
BASE = datetime(2026, 11, 14, 8, 0, tzinfo=UTC)


def approval(*, scope="comp-1", purposes=None):
    return SourceApproval(
        approval_id="approval-1", provider="TestProvider", source_id="testsrc",
        competition_scope=scope, data_type="fixtures_and_results",
        status=ApprovalStatus.APPROVED,
        permitted_uses=frozenset(purposes or {
            DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
            DataUsePurpose.BENCHMARKING,
        }),
        commercial_use_allowed=True, terms_url="https://example.test/terms",
        terms_version="v1", evidence_uri="https://example.test/evidence",
        evidence_sha256="a" * 64, rights_basis="WRITTEN_PERMISSION",
        reviewed_at_utc=BASE - timedelta(days=10), reviewer_id="reviewer",
        valid_from_utc=BASE - timedelta(days=10),
    )


def source_fixture(*, home_team="team-a"):
    kickoff = BASE + timedelta(days=2)
    available = kickoff + timedelta(hours=2)
    retrieved = kickoff + timedelta(hours=3)
    payload = {"status": "FINISHED", "home_score": 2, "away_score": 1}
    digest = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    return HistoricalFixture(
        provider="TestProvider", source_id="testsrc",
        provider_fixture_id="fixture-1", provider_competition_id="comp-1",
        provider_home_team_id=home_team, provider_away_team_id="team-b",
        competition_name="Test League", home_team_name="A", away_team_name="B",
        kickoff_at_utc=kickoff, season_key="2026",
        status=FixtureStatus.FINISHED, home_score=2, away_score=1,
        payload=payload, payload_sha256=digest, retrieved_at_utc=retrieved,
        source_event_time_utc=kickoff, available_at_utc=available,
        availability_basis="provider_timestamp", point_in_time_certifiable=True,
        rights_approval_id="approval-1",
    )


def ledger_with_prediction():
    ledger = ProspectivePaperLedger()
    kickoff = BASE + timedelta(days=2)
    ledger.append_prediction(PaperPrediction(
        fixture_id="testsrc:fixture-1", competition_id="testsrc:comp-1",
        home_team_id="testsrc:team-a", away_team_id="testsrc:team-b",
        kickoff_at=kickoff, prediction_cutoff_at=BASE - timedelta(minutes=5),
        forecasted_at=BASE - timedelta(minutes=4),
        recorded_at=BASE - timedelta(minutes=3), model_version="poisson-v1",
        home_probability=0.5, draw_probability=0.3, away_probability=0.2,
        evidence_sha256="b" * 64, point_in_time_certifiable=True,
    ))
    return ledger


def test_verified_settlement_appends_result_and_rights_provenance():
    ledger = ledger_with_prediction()
    fixture = source_fixture()
    event = settle_from_verified_fixture(
        ledger, fixture, approval(), recorded_at=fixture.retrieved_at_utc + timedelta(hours=1)
    )
    assert event.event_type == "SETTLEMENT"
    assert event.payload["home_goals"] == 2
    assert event.payload["away_goals"] == 1
    assert event.payload["result_payload_sha256"] == fixture.payload_sha256
    assert event.payload["rights_approval_id"] == "approval-1"
    assert ledger.verify_chain()


def test_rejects_settlement_outside_approved_competition():
    ledger = ledger_with_prediction()
    fixture = source_fixture()
    with pytest.raises(ValueError, match="SETTLEMENT_COMPETITION_OUTSIDE_APPROVAL_SCOPE"):
        settle_from_verified_fixture(
            ledger, fixture, approval(scope="other"), 
            recorded_at=fixture.retrieved_at_utc + timedelta(hours=1)
        )


def test_rejects_settlement_when_benchmarking_use_not_approved():
    ledger = ledger_with_prediction()
    fixture = source_fixture()
    with pytest.raises(ValueError, match="PURPOSE_NOT_PERMITTED"):
        settle_from_verified_fixture(
            ledger, fixture, approval(purposes={
                DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
            }), recorded_at=fixture.retrieved_at_utc + timedelta(hours=1)
        )


def test_rejects_settlement_for_different_fixture_identity():
    ledger = ledger_with_prediction()
    fixture = source_fixture(home_team="different-team")
    with pytest.raises(ValueError, match="SETTLEMENT_FIXTURE_IDENTITY_MISMATCH"):
        settle_from_verified_fixture(
            ledger, fixture, approval(),
            recorded_at=fixture.retrieved_at_utc + timedelta(hours=1)
        )


def ledger_with_observed_prediction():
    ledger = ProspectivePaperLedger()
    kickoff = BASE + timedelta(days=2)
    ledger.append_prediction(PaperPrediction(
        fixture_id="testsrc:fixture-1", competition_id="testsrc:comp-1",
        home_team_id="testsrc:team-a", away_team_id="testsrc:team-b",
        kickoff_at=kickoff, prediction_cutoff_at=BASE - timedelta(minutes=5),
        forecasted_at=BASE - timedelta(minutes=4),
        recorded_at=BASE - timedelta(minutes=3), model_version="poisson-observed-v1",
        home_probability=0.5, draw_probability=0.3, away_probability=0.2,
        evidence_sha256="f" * 64, point_in_time_certifiable=False,
        evidence_class="PROSPECTIVE_OBSERVED_ONLY",
    ))
    return ledger


def test_observed_shadow_settlement_uses_collector_first_seen_not_provider_proxy():
    ledger = ledger_with_observed_prediction()
    fixture = source_fixture()
    event = settle_from_verified_fixture(
        ledger, fixture, approval(), recorded_at=fixture.retrieved_at_utc + timedelta(hours=1)
    )
    assert event.event_type == "SETTLEMENT"
    assert event.payload["prediction_event_type"] == "SHADOW_PREDICTION"
    assert event.payload["prediction_evidence_class"] == "PROSPECTIVE_OBSERVED_ONLY"
    assert event.payload["result_availability_basis"] == "collector_first_observed_v1"
    assert event.payload["result_available_at"] == fixture.retrieved_at_utc.isoformat()
    assert event.payload["result_retrieved_at"] == fixture.retrieved_at_utc.isoformat()
    assert event.payload["settlement_delay_basis"] == fixture.availability_basis
    assert ledger.verify_chain()


def test_observed_shadow_settlement_still_requires_explicit_benchmarking_rights():
    ledger = ledger_with_observed_prediction()
    fixture = source_fixture()
    restricted = approval(purposes={DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE})
    with pytest.raises(ValueError, match="PURPOSE_NOT_PERMITTED"):
        settle_from_verified_fixture(
            ledger, fixture, restricted,
            recorded_at=fixture.retrieved_at_utc + timedelta(hours=1)
        )


def test_observed_shadow_settlement_waits_for_conservative_delay_boundary():
    ledger = ledger_with_observed_prediction()
    fixture = source_fixture()
    fixture = replace(
        fixture,
        available_at_utc=fixture.retrieved_at_utc + timedelta(days=1),
        availability_basis="provider_finished_status_conservative_4d",
        point_in_time_certifiable=False,
    )
    with pytest.raises(ValueError, match="SETTLEMENT_FIRST_OBSERVED_TEMPORAL_ORDER_INVALID"):
        settle_from_verified_fixture(
            ledger, fixture, approval(),
            recorded_at=fixture.retrieved_at_utc + timedelta(hours=1)
        )


def test_settlement_requires_model_version_when_fixture_has_multiple_predictions():
    ledger = ledger_with_prediction()
    kickoff = BASE + timedelta(days=2)
    ledger.append_prediction(PaperPrediction(
        fixture_id="testsrc:fixture-1", competition_id="testsrc:comp-1",
        home_team_id="testsrc:team-a", away_team_id="testsrc:team-b",
        kickoff_at=kickoff, prediction_cutoff_at=BASE - timedelta(minutes=5),
        forecasted_at=BASE - timedelta(minutes=4), recorded_at=BASE - timedelta(minutes=2),
        model_version="poisson-v2", home_probability=0.4, draw_probability=0.3,
        away_probability=0.3, evidence_sha256="c" * 64, point_in_time_certifiable=True,
    ))
    fixture = source_fixture()
    with pytest.raises(ValueError, match="PAPER_SETTLEMENT_PREDICTION_NOT_UNIQUE"):
        settle_from_verified_fixture(
            ledger, fixture, approval(),
            recorded_at=fixture.retrieved_at_utc + timedelta(hours=1)
        )
    settled = settle_from_verified_fixture(
        ledger, fixture, approval(),
        recorded_at=fixture.retrieved_at_utc + timedelta(hours=1),
        model_version="poisson-v1",
    )
    assert settled.model_version == "poisson-v1"


def test_duplicate_or_corrected_result_cannot_overwrite_an_existing_settlement():
    ledger = ledger_with_prediction()
    fixture = source_fixture()
    recorded_at = fixture.retrieved_at_utc + timedelta(hours=1)
    first = settle_from_verified_fixture(
        ledger, fixture, approval(), recorded_at=recorded_at
    )
    corrected_payload = {"status": "FINISHED", "home_score": 3, "away_score": 1}
    corrected_digest = hashlib.sha256(json.dumps(
        corrected_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    corrected = replace(
        fixture,
        home_score=3,
        payload=corrected_payload,
        payload_sha256=corrected_digest,
    )
    with pytest.raises(ValueError, match="PAPER_SETTLEMENT_DUPLICATE"):
        settle_from_verified_fixture(
            ledger, corrected, approval(), recorded_at=recorded_at + timedelta(minutes=1)
        )
    assert len([event for event in ledger.events if event.event_type == "SETTLEMENT"]) == 1
    assert ledger.events[-1].event_sha256 == first.event_sha256
    assert ledger.verify_chain()
