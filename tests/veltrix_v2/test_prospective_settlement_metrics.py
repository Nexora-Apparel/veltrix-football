from datetime import datetime, timedelta, timezone

from veltrix_v2.ledger.paper_predictions import PaperPrediction, ProspectivePaperLedger
from veltrix_v2.evaluation.prospective_settlement_metrics import evaluate_prospective_settlements

UTC = timezone.utc
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def ledger_with_predictions():
    ledger = ProspectivePaperLedger()
    for index, kickoff in enumerate((NOW - timedelta(days=2), NOW - timedelta(days=1)), start=1):
        ledger.append_prediction(PaperPrediction(
            fixture_id=f"source:fixture-{index}", competition_id="source:league",
            home_team_id="source:home", away_team_id="source:away",
            kickoff_at=kickoff, prediction_cutoff_at=kickoff - timedelta(hours=2),
            forecasted_at=kickoff - timedelta(hours=1),
            recorded_at=kickoff - timedelta(minutes=30),
            model_version="results-poisson-v1",
            home_probability=0.5, draw_probability=0.3, away_probability=0.2,
            evidence_sha256="a" * 64, point_in_time_certifiable=False,
            evidence_class="PROSPECTIVE_OBSERVED_ONLY",
            market_probabilities={
                "1X2": {"home": 0.5, "draw": 0.3, "away": 0.2},
                "BTTS": {"yes": 0.6, "no": 0.4},
                "TOTALS_2_5": {"over": 0.55, "under": 0.45},
            },
        ))
    return ledger


def append_result(ledger, fixture_id, home_goals, away_goals, model_version="results-poisson-v1"):
    kickoff = NOW - timedelta(days=2 if fixture_id.endswith("1") else 1)
    available = kickoff + timedelta(hours=2)
    ledger.append_settlement(
        fixture_id=fixture_id, model_version=model_version,
        home_goals=home_goals, away_goals=away_goals,
        result_available_at=available, result_retrieved_at=available,
        recorded_at=available + timedelta(minutes=1),
        source_provider="TestProvider", source_id="source",
        source_fixture_id=fixture_id.split(":")[-1],
        result_payload_sha256="b" * 64, rights_approval_id="approval",
        rights_evidence_sha256="c" * 64,
        result_availability_basis="collector_first_observed_v1",
    )


def test_scorecard_scores_only_settled_predictions_and_keeps_roi_locked():
    ledger = ledger_with_predictions()
    append_result(ledger, "source:fixture-1", 2, 1)
    report = evaluate_prospective_settlements(ledger)
    assert report.prediction_count == 2
    assert report.settled_prediction_count == 1
    assert report.unsettled_prediction_count == 1
    assert report.certification_status == "NOT_CERTIFIED"
    one_x_two, btts, totals = report.markets
    assert one_x_two.sample_count == btts.sample_count == totals.sample_count == 1
    assert one_x_two.distinct_dates == 1
    assert one_x_two.brier_score is not None
    assert one_x_two.log_loss is not None
    assert one_x_two.roi is None
    assert one_x_two.odds_covered_selections == 0
    assert one_x_two.roi_status == "LOCKED_NO_VERIFIED_SELECTION_AND_PREKICKOFF_ODDS"
    assert btts.sample_count == totals.sample_count == 1
    assert ledger.verify_chain()


def test_empty_settlement_ledger_reports_zero_samples_without_fabricating_metrics():
    report = evaluate_prospective_settlements(ledger_with_predictions())
    assert report.settled_prediction_count == 0
    assert report.unsettled_prediction_count == 2
    assert all(metric.sample_count == 0 and metric.brier_score is None
               for metric in report.markets)
    assert all(metric.roi is None and metric.clv is None for metric in report.markets)
