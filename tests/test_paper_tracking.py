from datetime import date

from app.paper_tracking import evaluate_report, merge_paper_ledger
from scripts import run_paper_tracking as tracking_runner


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



def test_ledger_accumulates_metrics_and_deduplicates_report_dates():
    report = {"as_of_date": "2026-10-22", "predictions": [_prediction(1)]}
    first = evaluate_report(report, {"response": [_result(1, 2, 0)]})
    ledger = merge_paper_ledger({}, first)
    assert ledger["cumulative_metrics"]["matches"] == 1
    assert ledger["evaluated_report_dates"] == 1

    # Replaying the same report date must not double-count the same match.
    replay = merge_paper_ledger(ledger, first)
    assert replay["cumulative_metrics"]["matches"] == 1
    assert replay["evaluated_report_dates"] == 1

    second_report = {"as_of_date": "2026-10-23", "predictions": [_prediction(2, probabilities={"H": 0.15, "D": 0.25, "A": 0.6})]}
    second = evaluate_report(second_report, {"response": [_result(2, 0, 1)]})
    updated = merge_paper_ledger(replay, second)
    assert updated["cumulative_metrics"]["matches"] == 2
    assert updated["evaluated_report_dates"] == 2
    assert updated["cumulative_metrics"]["result_accuracy"] == 1.0



def test_automation_writes_safe_ledger_when_github_credentials_are_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    output = tmp_path / "ledger.json"
    ledger = tracking_runner.run(date(2026, 10, 23), str(output))
    assert output.exists()
    assert ledger["model_status"] == "PAPER_TRACKING_ONLY"
    assert ledger["last_attempt"]["status"] == "TRACKING_ERROR"
    assert ledger["evaluations"] == []



def test_run_discovery_queries_schedule_and_dispatch_separately(monkeypatch):
    calls = []
    def fake_github_get(session, url):
        calls.append(url)
        if "event=schedule" in url:
            return {"workflow_runs": [{"id": 1, "event": "schedule", "created_at": "2026-10-23T07:00:00Z"}]}
        return {"workflow_runs": [{"id": 2, "event": "workflow_dispatch", "created_at": "2026-10-24T07:00:00Z"}]}
    monkeypatch.setattr(tracking_runner, "github_get", fake_github_get)
    runs = tracking_runner.list_relevant_runs(object(), "owner/repo")
    assert len(calls) == 2
    assert [run["id"] for run in runs] == [2, 1]
