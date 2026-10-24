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
    assert result["metrics_by_model"] == {}


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



def test_report_lookup_matches_saved_report_date_and_skips_current_run(monkeypatch):
    runs = [
        {"id": 99, "created_at": "2026-10-23T07:00:00Z"},
        {"id": 12, "created_at": "2026-10-23T07:00:00Z"},
    ]
    monkeypatch.setattr(
        tracking_runner, "artifact_for_run",
        lambda session, repo, run_id, name: {"archive_download_url": "report-zip"} if run_id == 12 and name == "veltrix-daily-predictions" else None,
    )
    monkeypatch.setattr(
        tracking_runner, "read_artifact_json",
        lambda session, url: {"as_of_date": "2026-10-23", "predictions": []},
    )
    report = tracking_runner.find_daily_report(object(), "owner/repo", runs, "2026-10-23", "99")
    assert report["as_of_date"] == "2026-10-23"


def test_latest_ledger_lookup_skips_current_run(monkeypatch):
    runs = [
        {"id": 99, "created_at": "2026-10-24T07:00:00Z"},
        {"id": 12, "created_at": "2026-10-23T07:00:00Z"},
    ]
    monkeypatch.setattr(
        tracking_runner, "artifact_for_run",
        lambda session, repo, run_id, name: {"archive_download_url": "ledger-zip"} if run_id == 12 and name == "veltrix-paper-ledger" else None,
    )
    monkeypatch.setattr(
        tracking_runner, "read_artifact_json",
        lambda session, url: {"evaluations": [{"report_date": "2026-10-22"}], "scored_matches": []},
    )
    ledger = tracking_runner.find_latest_ledger(object(), "owner/repo", runs, "99")
    assert ledger["evaluations"][0]["report_date"] == "2026-10-22"



def test_ledger_keeps_metrics_separate_when_model_versions_change():
    first_prediction = _prediction(11)
    first_prediction["model"] = "experimental_v1"
    first = evaluate_report(
        {"as_of_date": "2026-10-20", "predictions": [first_prediction]},
        {"response": [_result(11, 2, 0)]},
    )
    ledger = merge_paper_ledger({}, first)

    second_prediction = _prediction(12, probabilities={"H": 0.15, "D": 0.25, "A": 0.6})
    second_prediction["model"] = "experimental_v2"
    second = evaluate_report(
        {"as_of_date": "2026-10-21", "predictions": [second_prediction]},
        {"response": [_result(12, 0, 1)]},
    )
    ledger = merge_paper_ledger(ledger, second)
    assert ledger["cumulative_metrics"] is None
    assert ledger["cumulative_metrics_by_model"]["experimental_v1"]["matches"] == 1
    assert ledger["cumulative_metrics_by_model"]["experimental_v2"]["matches"] == 1
    assert ledger["model_versions"] == ["experimental_v1", "experimental_v2"]



def test_evaluator_accepts_actual_live_model_probability_field_names():
    report = {"as_of_date": "2026-10-23", "predictions": [{
        "fixture_id": 21,
        "model": "experimental_recent_goals_poisson",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "status": "EXPERIMENTAL_ONLY",
        "probabilities": {"home_win": 0.6, "draw": 0.25, "away_win": 0.15},
    }]}
    result = evaluate_report(report, {"response": [_result(21, 2, 0)]})
    assert result["completed_forecasts_scored"] == 1
    assert result["matches"][0]["probabilities"] == {"H": 0.6, "D": 0.25, "A": 0.15}



def test_latest_ledger_searches_past_45_daily_runs(monkeypatch):
    runs = [{"id": 1000 - index, "created_at": f"2026-10-{(index % 28) + 1:02d}T07:00:00Z"} for index in range(60)]
    found_id = runs[59]["id"]
    monkeypatch.setattr(
        tracking_runner, "artifact_for_run",
        lambda session, repo, run_id, name: {"archive_download_url": "ledger-zip"} if run_id == found_id and name == "veltrix-paper-ledger" else None,
    )
    monkeypatch.setattr(
        tracking_runner, "read_artifact_json",
        lambda session, url: {"evaluations": [{"report_date": "2026-08-01"}], "scored_matches": []},
    )
    ledger = tracking_runner.find_latest_ledger(object(), "owner/repo", runs, "9999")
    assert ledger["evaluations"][0]["report_date"] == "2026-08-01"



def test_evaluator_scores_poisson_and_elo_alternatives_separately():
    report = {"as_of_date": "2026-10-23", "predictions": [{
        "fixture_id": 31,
        "model": "experimental_recent_goals_poisson",
        "elo_model": "experimental_elo_by_competition",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "status": "EXPERIMENTAL_ONLY",
        "probabilities": {"home_win": 0.35, "draw": 0.30, "away_win": 0.35},
        "elo_probabilities": {"home_win": 0.60, "draw": 0.25, "away_win": 0.15},
    }]}
    result = evaluate_report(report, {"response": [_result(31, 2, 0)]})
    assert result["completed_forecasts_scored"] == 2
    assert result["fixtures_scored"] == 1
    assert {row["model"] for row in result["matches"]} == {
        "experimental_recent_goals_poisson",
        "experimental_elo_by_competition",
    }
    ledger = merge_paper_ledger({}, result)
    assert ledger["cumulative_metrics_by_model"]["experimental_recent_goals_poisson"]["matches"] == 1
    assert ledger["cumulative_metrics_by_model"]["experimental_elo_by_competition"]["matches"] == 1



def test_evaluator_scores_poisson_and_elo_separately_for_same_fixture():
    prediction = _prediction(31)
    prediction["model"] = "experimental_recent_goals_poisson"
    prediction["elo_model"] = "experimental_elo_by_competition"
    prediction["elo_probabilities"] = {"home_win": 0.2, "draw": 0.3, "away_win": 0.5}
    evaluation = evaluate_report(
        {"as_of_date": "2026-10-24", "predictions": [prediction]},
        {"response": [_result(31, 0, 1)]},
    )
    assert evaluation["fixtures_scored"] == 1
    assert evaluation["completed_forecasts_scored"] == 2
    assert evaluation["metrics"] is None
    assert evaluation["metrics_by_model"]["experimental_recent_goals_poisson"]["matches"] == 1
    assert evaluation["metrics_by_model"]["experimental_elo_by_competition"]["matches"] == 1
    assert evaluation["metrics_by_model"]["experimental_elo_by_competition"]["result_accuracy"] == 1.0

    ledger = merge_paper_ledger({}, evaluation)
    assert ledger["cumulative_metrics_by_model"]["experimental_recent_goals_poisson"]["matches"] == 1
    assert ledger["cumulative_metrics_by_model"]["experimental_elo_by_competition"]["matches"] == 1
    assert len(ledger["scored_matches"]) == 2



def test_evaluator_normalizes_small_probability_rounding_drift():
    prediction = _prediction(41, probabilities={"H": 0.3333, "D": 0.3333, "A": 0.3333})
    result = evaluate_report(
        {"as_of_date": "2026-10-24", "predictions": [prediction]},
        {"response": [_result(41, 1, 1)]},
    )
    values = result["matches"][0]["probabilities"]
    assert abs(sum(values.values()) - 1.0) < 1e-12



def test_evaluator_scores_elo_primary_and_poisson_alternative():
    report = {"as_of_date": "2026-10-24", "predictions": [{
        "fixture_id": 41,
        "model": "experimental_elo_by_competition",
        "poisson_model": "experimental_recent_goals_poisson",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "status": "EXPERIMENTAL_ONLY",
        "probabilities": {"home_win": 0.6, "draw": 0.25, "away_win": 0.15},
        "poisson_probabilities": {"home_win": 0.35, "draw": 0.30, "away_win": 0.35},
    }]}
    evaluation = evaluate_report(report, {"response": [_result(41, 2, 0)]})
    assert evaluation["fixtures_scored"] == 1
    assert evaluation["completed_forecasts_scored"] == 2
    assert evaluation["metrics_by_model"]["experimental_elo_by_competition"]["result_accuracy"] == 1.0
    assert evaluation["metrics_by_model"]["experimental_recent_goals_poisson"]["result_accuracy"] == 1.0
    ledger = merge_paper_ledger({}, evaluation)
    assert ledger["cumulative_metrics_by_model"]["experimental_elo_by_competition"]["matches"] == 1
    assert ledger["cumulative_metrics_by_model"]["experimental_recent_goals_poisson"]["matches"] == 1



def test_evaluator_scores_poisson_alternative_when_competition_elo_is_primary():
    prediction = _prediction(51)
    prediction["model"] = "experimental_elo_by_competition"
    prediction["probabilities"] = {"home_win": 0.6, "draw": 0.25, "away_win": 0.15}
    prediction["poisson_model"] = "experimental_recent_goals_poisson"
    prediction["poisson_probabilities"] = {"home_win": 0.35, "draw": 0.3, "away_win": 0.35}
    evaluation = evaluate_report(
        {"as_of_date": "2026-10-24", "predictions": [prediction]},
        {"response": [_result(51, 2, 0)]},
    )
    assert evaluation["completed_forecasts_scored"] == 2
    assert evaluation["unique_fixtures_scored"] == 1
    assert evaluation["metrics_by_model"]["experimental_elo_by_competition"]["result_accuracy"] == 1.0
    assert evaluation["metrics_by_model"]["experimental_recent_goals_poisson"]["result_accuracy"] == 1.0
    assert len(evaluation["matches"]) == 2



def test_tracking_runner_evaluates_saved_report_and_writes_per_model_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_RUN_ID", "999")
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-api-key")
    monkeypatch.setattr(tracking_runner, "get_settings", lambda: object())
    monkeypatch.setattr(
        tracking_runner, "list_relevant_runs",
        lambda session, repo: [{"id": 123, "created_at": "2026-10-23T07:00:00Z"}],
    )
    monkeypatch.setattr(
        tracking_runner, "find_latest_ledger",
        lambda session, repo, runs, current_run_id: {
            "product": "Veltrix Football", "model_status": "PAPER_TRACKING_ONLY",
            "evaluations": [], "scored_matches": [],
        },
    )
    monkeypatch.setattr(
        tracking_runner, "find_daily_report",
        lambda session, repo, runs, report_date, current_run_id: {
            "as_of_date": report_date,
            "predictions": [{
                "fixture_id": 61,
                "status": "EXPERIMENTAL_ONLY",
                "model": "experimental_elo_by_competition",
                "probabilities": {"home_win": 0.6, "draw": 0.25, "away_win": 0.15},
                "poisson_model": "experimental_recent_goals_poisson",
                "poisson_probabilities": {"home_win": 0.35, "draw": 0.3, "away_win": 0.35},
            }],
        },
    )

    class FakeFootballAPI:
        def __init__(self, settings):
            pass
        def fixtures(self, date, timezone):
            return {"response": [_result(61, 2, 0)]}

    monkeypatch.setattr(tracking_runner, "FootballAPI", FakeFootballAPI)
    output = tmp_path / "paper_ledger.json"
    ledger = tracking_runner.run(date(2026, 10, 23), str(output))
    assert ledger["last_attempt"]["status"] == "EVALUATED"
    assert ledger["last_attempt"]["completed_forecasts_scored"] == 2
    assert set(ledger["last_attempt"]["metrics_by_model"]) == {
        "experimental_elo_by_competition", "experimental_recent_goals_poisson"
    }
    assert ledger["cumulative_metrics_by_model"]["experimental_elo_by_competition"]["matches"] == 1
    assert ledger["cumulative_metrics_by_model"]["experimental_recent_goals_poisson"]["matches"] == 1
    assert output.exists()



def test_pending_report_date_is_updated_as_more_fixtures_finish():
    report = {
        "as_of_date": "2026-10-22",
        "predictions": [_prediction(71), _prediction(72)],
    }
    first = evaluate_report(
        report,
        {"response": [_result(71, 1, 0), _result(72, None, None, status="NS")]},
    )
    ledger = merge_paper_ledger({}, first)
    assert ledger["evaluations"][0]["awaiting_result_or_match"] == 1
    assert ledger["evaluations"][0]["completed_forecasts_scored"] == 1

    second = evaluate_report(
        report,
        {"response": [_result(71, 1, 0), _result(72, 0, 2)]},
    )
    ledger = merge_paper_ledger(ledger, second)
    assert ledger["evaluations"][0]["awaiting_result_or_match"] == 0
    assert ledger["evaluations"][0]["completed_forecasts_scored"] == 2
    assert ledger["evaluations"][0]["metrics"]["matches"] == 2
    assert ledger["cumulative_metrics_by_model"]["unknown"]["matches"] == 2
    assert len(ledger["scored_matches"]) == 2

    # A replay after completion must remain idempotent.
    replay = merge_paper_ledger(ledger, second)
    assert replay["evaluations"][0]["completed_forecasts_scored"] == 2
    assert len(replay["scored_matches"]) == 2



def test_tracking_runner_retries_report_already_in_ledger_when_fixtures_are_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_RUN_ID", "999")
    monkeypatch.setenv("API_FOOTBALL_KEY", "test-api-key")
    monkeypatch.setattr(tracking_runner, "get_settings", lambda: object())
    monkeypatch.setattr(tracking_runner, "list_relevant_runs", lambda session, repo: [])
    monkeypatch.setattr(
        tracking_runner, "find_latest_ledger",
        lambda session, repo, runs, current_run_id: {
            "product": "Veltrix Football",
            "model_status": "PAPER_TRACKING_ONLY",
            "evaluations": [{
                "report_date": "2026-10-23",
                "completed_forecasts_scored": 0,
                "awaiting_result_or_match": 1,
                "withheld_or_invalid_forecasts": 0,
                "metrics": {},
            }],
            "scored_matches": [],
        },
    )
    monkeypatch.setattr(
        tracking_runner, "find_daily_report",
        lambda session, repo, runs, report_date, current_run_id: {
            "as_of_date": report_date,
            "predictions": [_prediction(81)],
        },
    )

    class FakeFootballAPI:
        def __init__(self, settings):
            pass
        def fixtures(self, date, timezone):
            return {"response": [_result(81, 2, 0)]}

    monkeypatch.setattr(tracking_runner, "FootballAPI", FakeFootballAPI)
    ledger = tracking_runner.run(date(2026, 10, 23), str(tmp_path / "ledger.json"))
    assert ledger["last_attempt"]["status"] == "EVALUATED"
    assert ledger["evaluations"][0]["awaiting_result_or_match"] == 0
    assert ledger["evaluations"][0]["completed_forecasts_scored"] == 1
