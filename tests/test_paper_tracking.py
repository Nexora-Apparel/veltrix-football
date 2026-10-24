from app.paper_tracking import evaluate_report


def _prediction(fixture_id, status="EXPERIMENTAL_ONLY", probabilities=None):
    row = {
        "fixture_id": fixture_id,
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "status": status,
    }
    if probabilities is not None:
        row["probabilities"] = probabilities
    elif status == "EXPERIMENTAL_ONLY":
        row["probabilities"] = {"H": 0.6, "D": 0.25, "A": 0.15}
    return row


def _result(fixture_id, home, away, status="FT"):
    return {
        "fixture": {"id": fixture_id, "status": {"short": status}},
        "goals": {"home": home, "away": away},
    }


def test_evaluator_scores_completed_forecast_with_proper_metrics():
    report = {"product": "Veltrix Football", "as_of_date": "2026-10-23",
              "predictions": [_prediction(1)]}
    result = evaluate_report(report, {"response": [_result(1, 2, 0)]})
    assert result["completed_forecasts_scored"] == 1
    assert result["metrics"]["result_accuracy"] == 1.0
    assert result["metrics"]["brier_score"] is not None
    assert result["metrics"]["log_loss"] is not None
    assert result["matches"][0]["actual"] == "H"
    assert result["model_status"] == "PAPER_TRACKING_ONLY"


def test_evaluator_does_not_score_unfinished_or_withheld_fixtures():
    report = {"predictions": [
        _prediction(1),
        _prediction(2),
        _prediction(3, status="INSUFFICIENT_HISTORY"),
    ]}
    result = evaluate_report(report, {"response": [
        _result(1, 1, 0, status="NS"),
        _result(2, 0, 0, status="FT"),
    ]})
    assert result["completed_forecasts_scored"] == 1
    assert result["awaiting_result_or_match"] == 1
    assert result["withheld_or_invalid_forecasts"] == 1


def test_evaluator_rejects_invalid_probability_vectors():
    report = {"predictions": [
        _prediction(1, probabilities={"H": 0.8, "D": 0.8, "A": -0.6}),
    ]}
    result = evaluate_report(report, {"response": [_result(1, 1, 0)]})
    assert result["completed_forecasts_scored"] == 0
    assert result["withheld_or_invalid_forecasts"] == 1
    assert result["metrics"]["log_loss"] is None


def test_evaluator_reports_unmatched_and_missing_fixture_ids():
    report = {"predictions": [
        _prediction(1),
        _prediction(None),
    ]}
    result = evaluate_report(report, {"response": []})
    assert result["awaiting_result_or_match"] == 1
    assert result["forecasts_missing_fixture_id"] == 1
