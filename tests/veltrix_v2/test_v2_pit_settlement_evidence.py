from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.ledger.paper_predictions import (
    PaperPrediction,
    ProspectivePaperLedger,
    V2_PIT_MODEL_VERSION,
)
from veltrix_v2.evaluation.prospective_settlement_metrics import evaluate_prospective_settlements

UTC=timezone.utc
NOW=datetime(2026,11,22,12,0,tzinfo=UTC)


def _ledger():
    ledger=ProspectivePaperLedger()
    ledger.append_prediction(PaperPrediction(
        fixture_id="5dollarfootballapi:fixture-1",
        competition_id="5dollarfootballapi:league-1",
        home_team_id="5dollarfootballapi:home-1",
        away_team_id="5dollarfootballapi:away-1",
        kickoff_at=NOW-timedelta(days=2),
        prediction_cutoff_at=NOW-timedelta(days=2,hours=3),
        forecasted_at=NOW-timedelta(days=2,hours=2),
        recorded_at=NOW-timedelta(days=2,hours=1),
        model_version=V2_PIT_MODEL_VERSION,
        home_probability=0.5,draw_probability=0.3,away_probability=0.2,
        evidence_sha256="a"*64,point_in_time_certifiable=True,
        evidence_class="PIT_CERTIFIED",
        target_provider="5DollarFootballAPI",
        target_source_id="5dollarfootballapi",
        target_source_fixture_id="fixture-1",
        target_provider_competition_id="league-1",
        market_probabilities={
            "1X2":{"home":0.5,"draw":0.3,"away":0.2},
            "BTTS":{"yes":0.6,"no":0.4},
            "TOTALS_2_5":{"over":0.55,"under":0.45},
        },
    ))
    event=ledger.events[-1]
    feature_link={
        "link_sha256":"b"*64,
        "prediction_event_sha256":event.event_sha256,
        "feature_snapshot_id":15,
        "eligibility_event_id":101,
        "feature_set_sha256":"c"*64,
        "eligibility_evidence_sha256":"d"*64,
        "forecast_evidence_sha256":"a"*64,
        "model_artifact_sha256":"e"*64,
        "feature_snapshot_cutoff_at":NOW-timedelta(days=2,hours=3),
        "forecast_cutoff_at":NOW-timedelta(days=2,hours=2),
        "recorded_at":NOW-timedelta(days=2,hours=1)+timedelta(seconds=1),
    }
    return ledger,event,feature_link


def _settle(ledger,link):
    kickoff=NOW-timedelta(days=2)
    available=kickoff+timedelta(hours=2)
    return ledger.append_settlement(
        fixture_id="5dollarfootballapi:fixture-1",
        model_version=V2_PIT_MODEL_VERSION,
        home_goals=2,away_goals=1,
        result_available_at=available,result_retrieved_at=available,
        recorded_at=available+timedelta(minutes=1),
        source_provider="5DollarFootballAPI",source_id="5dollarfootballapi",
        source_fixture_id="fixture-1",result_payload_sha256="f"*64,
        rights_approval_id="approval-5dollar-results",
        rights_evidence_sha256="0"*64,
        result_availability_basis="collector_first_observed_v1",
        settlement_delay_basis="collector_first_observed_v1",
        prediction_feature_link_sha256=link["link_sha256"],
        feature_snapshot_id=link["feature_snapshot_id"],
        eligibility_event_id=link["eligibility_event_id"],
        feature_set_sha256=link["feature_set_sha256"],
        eligibility_evidence_sha256=link["eligibility_evidence_sha256"],
        forecast_evidence_sha256=link["forecast_evidence_sha256"],
        model_artifact_sha256=link["model_artifact_sha256"],
    )


def test_v2_pit_predictions_require_feature_links_for_scoring():
    ledger,event,link=_ledger()
    with pytest.raises(ValueError,match="V2_FEATURE_EVIDENCE_LINK_MISSING"):
        evaluate_prospective_settlements(
            ledger,model_version=V2_PIT_MODEL_VERSION,prediction_feature_links={}
        )
    report=evaluate_prospective_settlements(
        ledger,model_version=V2_PIT_MODEL_VERSION,
        prediction_feature_links={event.event_sha256:link},
    )
    assert report.prediction_count==1
    assert report.settled_prediction_count==0
    assert report.unsettled_prediction_count==1
    assert report.certification_status=="NOT_CERTIFIED"


def test_v2_settlement_cannot_be_appended_without_feature_link():
    ledger,event,link=_ledger()
    kickoff=NOW-timedelta(days=2)
    available=kickoff+timedelta(hours=2)
    with pytest.raises(ValueError,match="V2_FEATURE_EVIDENCE_LINK_REQUIRED"):
        ledger.append_settlement(
            fixture_id=event.fixture_id,model_version=V2_PIT_MODEL_VERSION,
            home_goals=2,away_goals=1,
            result_available_at=available,result_retrieved_at=available,
            recorded_at=available+timedelta(minutes=1),
            source_provider="5DollarFootballAPI",source_id="5dollarfootballapi",
            source_fixture_id="fixture-1",result_payload_sha256="f"*64,
            rights_approval_id="approval-5dollar-results",
            rights_evidence_sha256="0"*64,
            result_availability_basis="collector_first_observed_v1",
        )


def test_v2_settlement_carries_exact_feature_link_and_scores_only_v2():
    ledger,event,link=_ledger()
    settlement=_settle(ledger,link)
    assert settlement.payload["prediction_feature_link_sha256"]==link["link_sha256"]
    assert settlement.payload["feature_snapshot_id"]==15
    assert settlement.payload["eligibility_event_id"]==101
    assert settlement.payload["forecast_evidence_sha256"]==event.payload["evidence_sha256"]
    assert ledger.verify_chain()
    report=evaluate_prospective_settlements(
        ledger,model_version=V2_PIT_MODEL_VERSION,
        prediction_feature_links={event.event_sha256:link},
    )
    assert report.prediction_count==1
    assert report.settled_prediction_count==1
    assert report.unsettled_prediction_count==0
    assert report.certification_status=="NOT_CERTIFIED"
    assert all(metric.roi is None and metric.clv is None for metric in report.markets)


def test_legacy_default_scorecard_does_not_mix_v2_predictions():
    ledger,event,link=_ledger()
    _settle(ledger,link)
    report=evaluate_prospective_settlements(ledger)
    assert report.prediction_count==0
    assert report.settled_prediction_count==0
