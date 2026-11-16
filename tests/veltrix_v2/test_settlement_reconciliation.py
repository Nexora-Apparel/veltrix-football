import hashlib
import json
from datetime import datetime, timedelta, timezone

from veltrix_v2.data.contracts import (
    ApprovalStatus, DataUsePurpose, FixtureStatus, HistoricalFixture, SourceApproval,
)
from veltrix_v2.ledger.paper_predictions import PaperPrediction, ProspectivePaperLedger
from veltrix_v2.ledger.settlement_reconciliation import (
    reconcile_finished_fixtures,
    reconcile_v2_finished_fixtures,
)

UTC = timezone.utc
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def make_approval():
    return SourceApproval(
        approval_id="approval-5dollar", provider="5DollarFootballAPI",
        source_id="5dollarfootballapi", competition_scope="101",
        data_type="fixtures_and_results", status=ApprovalStatus.APPROVED,
        permitted_uses=frozenset({
            DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
            DataUsePurpose.BENCHMARKING,
        }), commercial_use_allowed=False,
        terms_url="https://example.test/terms", terms_version="v1",
        evidence_uri="https://example.test/evidence", evidence_sha256="a" * 64,
        rights_basis="WRITTEN_PERMISSION", reviewed_at_utc=NOW - timedelta(days=2),
        reviewer_id="reviewer", valid_from_utc=NOW - timedelta(days=2),
    )


def make_fixture(*, provider_fixture_id="777", home_team="11", retrieved=None,
                 response_sha256=None, capture_manifest_sha256=None):
    kickoff = NOW - timedelta(days=1)
    retrieved = retrieved or NOW - timedelta(minutes=5)
    payload = {
        "id": int(provider_fixture_id), "status": "finished",
        "goals": {"home": 2, "away": 1},
    }
    digest = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    return HistoricalFixture(
        provider="5DollarFootballAPI", source_id="5dollarfootballapi",
        provider_fixture_id=provider_fixture_id, provider_competition_id="101",
        provider_home_team_id=home_team, provider_away_team_id="22",
        competition_name="League", home_team_name="Home", away_team_name="Away",
        kickoff_at_utc=kickoff, season_key="2026", status=FixtureStatus.FINISHED,
        home_score=2, away_score=1, payload=payload, payload_sha256=digest,
        retrieved_at_utc=retrieved, source_event_time_utc=kickoff,
        available_at_utc=kickoff + timedelta(days=4),
        availability_basis="provider_finished_status_conservative_4d",
        point_in_time_certifiable=False, rights_approval_id="approval-5dollar",
        response_sha256=response_sha256,
        capture_manifest_sha256=capture_manifest_sha256,
    )


def make_ledger():
    kickoff = NOW - timedelta(days=1)
    ledger = ProspectivePaperLedger()
    ledger.append_prediction(PaperPrediction(
        fixture_id="5dollarfootballapi:777",
        competition_id="5dollarfootballapi:101",
        home_team_id="5dollarfootballapi:11",
        away_team_id="5dollarfootballapi:22",
        kickoff_at=kickoff, prediction_cutoff_at=kickoff - timedelta(hours=2),
        forecasted_at=kickoff - timedelta(hours=1),
        recorded_at=kickoff - timedelta(minutes=30),
        model_version="veltrix-results-poisson-v1",
        home_probability=0.48, draw_probability=0.27, away_probability=0.25,
        evidence_sha256="b" * 64, point_in_time_certifiable=False,
        evidence_class="PROSPECTIVE_OBSERVED_ONLY",
        target_provider="5DollarFootballAPI",
        target_source_id="5dollarfootballapi",
        target_source_fixture_id="777",
        target_provider_competition_id="101",
        target_payload_sha256="c" * 64,
        target_response_sha256="d" * 64,
        target_capture_manifest_sha256="e" * 64,
    ))
    return ledger


def test_reconciles_exact_finished_result_using_first_observed_time():
    ledger = make_ledger()
    fixture = make_fixture(response_sha256="d" * 64, capture_manifest_sha256="e" * 64)
    appended, quarantined = reconcile_finished_fixtures(
        ledger, [fixture], make_approval(), recorded_at=NOW,
    )
    assert len(appended) == 1
    assert quarantined == ()
    settlement = appended[0]
    assert settlement.event_type == "SETTLEMENT"
    assert settlement.payload["result_availability_basis"] == "collector_first_observed_v1"
    assert settlement.payload["result_available_at"] == settlement.payload["result_retrieved_at"]
    assert settlement.payload["settlement_delay_basis"] == "collector_first_observed_v1"
    assert settlement.payload["home_goals"] == 2
    assert settlement.payload["result_response_sha256"] == "d" * 64
    assert settlement.payload["result_capture_manifest_sha256"] == "e" * 64
    assert ledger.verify_chain()


def test_quarantines_team_identity_mismatch():
    ledger = make_ledger()
    appended, quarantined = reconcile_finished_fixtures(
        ledger, [make_fixture(home_team="999")], make_approval(), recorded_at=NOW,
    )
    assert appended == ()
    assert quarantined == (("777", "SETTLEMENT_FIXTURE_IDENTITY_MISMATCH"),)
    assert len(ledger.events) == 1


def test_quarantines_duplicate_provider_fixture_in_same_batch():
    ledger = make_ledger()
    fixture = make_fixture()
    appended, quarantined = reconcile_finished_fixtures(
        ledger, [fixture, fixture], make_approval(), recorded_at=NOW,
    )
    assert len(appended) == 1
    assert quarantined == (("777", "DUPLICATE_PROVIDER_FIXTURE_IN_BATCH"),)
    assert ledger.verify_chain()


def test_quarantines_result_retrieved_after_database_recording_time():
    ledger = make_ledger()
    fixture = make_fixture(retrieved=NOW + timedelta(minutes=1))
    appended, quarantined = reconcile_finished_fixtures(
        ledger, [fixture], make_approval(), recorded_at=NOW,
    )
    assert appended == ()
    assert quarantined == (("777", "SETTLEMENT_FIRST_OBSERVED_CLOCK_INVALID"),)
    assert len(ledger.events) == 1


def test_ignores_unrelated_finished_provider_rows():
    ledger = make_ledger()
    appended, quarantined = reconcile_finished_fixtures(
        ledger, [make_fixture(provider_fixture_id="999")],
        make_approval(), recorded_at=NOW,
    )
    assert appended == ()
    assert quarantined == ()
    assert len(ledger.events) == 1


def make_v2_ledger():
    kickoff = NOW - timedelta(days=1)
    ledger = ProspectivePaperLedger()
    ledger.append_prediction(PaperPrediction(
        fixture_id="5dollarfootballapi:777",
        competition_id="1001",
        home_team_id="1002",
        away_team_id="1003",
        kickoff_at=kickoff,
        prediction_cutoff_at=kickoff - timedelta(hours=2),
        forecasted_at=kickoff - timedelta(hours=1),
        recorded_at=kickoff - timedelta(minutes=30),
        model_version="veltrix-openplay-xg-poisson-v1",
        home_probability=0.48, draw_probability=0.27, away_probability=0.25,
        evidence_sha256="b" * 64,
        point_in_time_certifiable=True,
        evidence_class="PIT_CERTIFIED",
        target_provider="5DollarFootballAPI",
        target_source_id="5dollarfootballapi",
        target_source_fixture_id="777",
        target_provider_competition_id="101",
        target_payload_sha256="c" * 64,
        target_response_sha256="d" * 64,
        target_capture_manifest_sha256="e" * 64,
    ))
    prediction = ledger.events[0]
    link = {
        "prediction_event_sha256": prediction.event_sha256,
        "link_sha256": "f" * 64,
        "feature_snapshot_id": 15,
        "eligibility_event_id": 25,
        "feature_set_sha256": "1" * 64,
        "eligibility_evidence_sha256": "2" * 64,
        "forecast_evidence_sha256": prediction.payload["evidence_sha256"],
        "model_artifact_sha256": "3" * 64,
        "forecast_cutoff_at": kickoff - timedelta(hours=2),
        "feature_snapshot_cutoff_at": kickoff - timedelta(hours=3),
        "recorded_at": kickoff - timedelta(minutes=20),
        "canonical_competition_id": "1001",
        "canonical_home_team_id": "1002",
        "canonical_away_team_id": "1003",
        "provider_competition_id": "101",
        "provider_home_team_id": "11",
        "provider_away_team_id": "22",
    }
    return ledger, {prediction.event_sha256: link}


def test_reconciles_v2_pit_prediction_only_with_exact_immutable_feature_link():
    ledger, links = make_v2_ledger()
    fixture = make_fixture(response_sha256="d" * 64, capture_manifest_sha256="e" * 64)
    appended, quarantined = reconcile_v2_finished_fixtures(
        ledger, [fixture], make_approval(),
        v2_feature_links=links, recorded_at=NOW,
    )
    assert len(appended) == 1
    assert quarantined == ()
    settlement = appended[0]
    assert settlement.event_type == "SETTLEMENT"
    assert settlement.model_version == "veltrix-openplay-xg-poisson-v1"
    assert settlement.payload["prediction_feature_link_sha256"] == "f" * 64
    assert settlement.payload["feature_snapshot_id"] == 15
    assert settlement.payload["eligibility_event_id"] == 25
    assert settlement.payload["canonical_competition_id"] == "1001"
    assert settlement.payload["provider_competition_id"] == "101"
    assert settlement.payload["result_availability_basis"] == "collector_first_observed_v1"
    assert ledger.verify_chain()


def test_quarantines_v2_pit_prediction_when_feature_link_is_missing():
    ledger, _ = make_v2_ledger()
    fixture = make_fixture()
    appended, quarantined = reconcile_v2_finished_fixtures(
        ledger, [fixture], make_approval(), v2_feature_links={}, recorded_at=NOW,
    )
    assert appended == ()
    assert quarantined == (("777", "V2_SETTLEMENT_FEATURE_EVIDENCE_LINK_MISSING_OR_MISMATCHED"),)
    assert len(ledger.events) == 1


def test_quarantines_v2_pit_prediction_when_provider_identity_disagrees_with_link():
    ledger, links = make_v2_ledger()
    event_hash = next(iter(links))
    links[event_hash]["provider_home_team_id"] = "wrong-team"
    fixture = make_fixture()
    appended, quarantined = reconcile_v2_finished_fixtures(
        ledger, [fixture], make_approval(), v2_feature_links=links, recorded_at=NOW,
    )
    assert appended == ()
    assert quarantined == (("777", "SETTLEMENT_FIXTURE_IDENTITY_MISMATCH"),)
    assert len(ledger.events) == 1
