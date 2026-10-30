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


def test_evaluator_falls_back_to_unique_local_date_and_team_identity():
    report = {
        "timezone": "Africa/Lagos",
        "as_of_date": "2026-10-23",
        "predictions": [{
            **_prediction(999),
            "kickoff_local": "2026-10-23T18:00:00+01:00",
        }],
    }
    result_payload = {"response": [{
        "fixture": {"id": 1, "date": "2026-10-23", "status": {"short": "FT"}},
        "teams": {"home": {"name": "Alpha FC"}, "away": {"name": "Beta FC"}},
        "goals": {"home": 2, "away": 0},
    }]}
    result = evaluate_report(report, result_payload)
    assert result["completed_forecasts_scored"] == 1
    assert result["matches"][0]["fixture_id"] == 999
    assert result["matches"][0]["actual"] == "H"


def test_evaluator_does_not_use_ambiguous_identity_fallback():
    report = {
        "timezone": "Africa/Lagos",
        "predictions": [{**_prediction(999), "kickoff_local": "2026-10-23T18:00:00+01:00"}],
    }
    repeated = {
        "fixture": {"date": "2026-10-23", "status": {"short": "FT"}},
        "teams": {"home": {"name": "Alpha FC"}, "away": {"name": "Beta FC"}},
        "goals": {"home": 2, "away": 0},
    }
    first = {**repeated, "fixture": {**repeated["fixture"], "id": 1}}
    second = {**repeated, "fixture": {**repeated["fixture"], "id": 2}, "goals": {"home": 0, "away": 2}}
    result = evaluate_report(report, {"response": [first, second]})
    assert result["completed_forecasts_scored"] == 0
    assert result["awaiting_result_or_match"] == 1


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
    monkeypatch.delenv("API_FOOTBALL_KEY", raising=False)
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

    monkeypatch.setattr(
        tracking_runner, "load_cached_results_payload",
        lambda repo: ({"response": [_result(61, 2, 0)]}, "CACHE_AVAILABLE"),
    )
    output = tmp_path / "paper_ledger.json"
    ledger = tracking_runner.run(date(2026, 10, 23), str(output))
    assert ledger["last_attempt"]["status"] == "EVALUATED"
    attempt = ledger["last_attempt"]["attempts"][0]
    assert attempt["status"] == "EVALUATED"
    assert attempt["completed_forecasts_scored"] == 2
    assert set(attempt["metrics_by_model"]) == {
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

    monkeypatch.setattr(
        tracking_runner, "load_cached_results_payload",
        lambda repo: ({"response": [_result(81, 2, 0)]}, "CACHE_AVAILABLE"),
    )
    ledger = tracking_runner.run(date(2026, 10, 23), str(tmp_path / "ledger.json"))
    assert ledger["last_attempt"]["status"] == "EVALUATED"
    assert ledger["last_attempt"]["attempts"][0]["status"] == "EVALUATED"
    assert ledger["evaluations"][0]["awaiting_result_or_match"] == 0
    assert ledger["evaluations"][0]["completed_forecasts_scored"] == 1



def test_pending_report_date_is_updated_when_delayed_fixture_finishes():
    report = {"as_of_date": "2026-10-22", "predictions": [_prediction(51)]}
    pending = evaluate_report(report, {"response": []})
    ledger = merge_paper_ledger({}, pending)
    assert ledger["evaluations"][0]["awaiting_result_or_match"] == 1
    assert ledger["scored_matches"] == []

    completed = evaluate_report(report, {"response": [_result(51, 2, 0)]})
    updated = merge_paper_ledger(ledger, completed)
    assert updated["evaluations"][0]["awaiting_result_or_match"] == 0
    assert updated["evaluations"][0]["completed_forecasts_scored"] == 1
    assert len(updated["scored_matches"]) == 1
    # Replaying the now-complete report remains idempotent.
    replay = merge_paper_ledger(updated, completed)
    assert len(replay["scored_matches"]) == 1
    assert replay["evaluations"][0]["completed_forecasts_scored"] == 1


def test_report_lookup_prefers_same_day_snapshot_with_more_forecasts(monkeypatch):
    runs = [
        {"id": 30, "created_at": "2026-10-23T18:00:00Z"},
        {"id": 20, "created_at": "2026-10-23T05:00:00Z"},
        {"id": 10, "created_at": "2026-10-23T04:00:00Z"},
    ]
    artifacts = {
        30: {"archive_download_url": "late"},
        20: {"archive_download_url": "rich"},
        10: {"archive_download_url": "empty"},
    }
    reports = {
        "late": {"as_of_date": "2026-10-23", "predictions": [_prediction(1)]},
        "rich": {"as_of_date": "2026-10-23", "predictions": [_prediction(1), _prediction(2)]},
        "empty": {"as_of_date": "2026-10-23", "predictions": []},
    }
    monkeypatch.setattr(
        tracking_runner, "artifact_for_run",
        lambda session, repo, run_id, name: artifacts.get(run_id),
    )
    monkeypatch.setattr(tracking_runner, "read_artifact_json", lambda session, url: reports[url])
    selected = tracking_runner.find_daily_report(object(), "owner/repo", runs, "2026-10-23", "999")
    assert len(selected["predictions"]) == 2


def test_empty_previous_evaluation_can_be_replaced_when_forecasts_become_scoreable():
    empty = evaluate_report({"as_of_date": "2026-10-22", "predictions": []}, {"response": []})
    ledger = merge_paper_ledger({}, empty)
    assert ledger["evaluations"][0]["completed_forecasts_scored"] == 0

    corrected = evaluate_report(
        {"as_of_date": "2026-10-22", "predictions": [_prediction(77)]},
        {"response": [_result(77, 1, 0)]},
    )
    updated = merge_paper_ledger(ledger, corrected)
    assert updated["evaluations"][0]["completed_forecasts_scored"] == 1
    assert updated["cumulative_metrics_by_model"]["unknown"]["matches"] == 1


def test_runner_skips_provider_call_when_saved_report_has_no_scoreable_forecasts(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_RUN_ID", "999")
    monkeypatch.setattr(tracking_runner, "list_relevant_runs", lambda session, repo: [])
    monkeypatch.setattr(tracking_runner, "find_latest_ledger", lambda *args: {
        "product": "Veltrix Football", "model_status": "PAPER_TRACKING_ONLY",
        "evaluations": [], "scored_matches": [],
    })
    monkeypatch.setattr(tracking_runner, "find_daily_report", lambda *args: {
        "as_of_date": "2026-10-23", "predictions": [],
    })

    monkeypatch.setattr(
        tracking_runner, "load_cached_results_payload",
        lambda repo: ({"response": []}, "CACHE_AVAILABLE"),
    )
    output = tmp_path / "ledger.json"
    ledger = tracking_runner.run(date(2026, 10, 23), str(output))
    assert ledger["last_attempt"]["status"] == "NO_FORECASTS_TO_SCORE"


def test_old_empty_evaluation_is_retried_and_marked_without_provider_call(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_RUN_ID", "999")
    monkeypatch.setattr(tracking_runner, "list_relevant_runs", lambda session, repo: [])
    monkeypatch.setattr(tracking_runner, "find_latest_ledger", lambda *args: {
        "product": "Veltrix Football", "model_status": "PAPER_TRACKING_ONLY",
        "evaluations": [{
            "report_date": "2026-10-22", "fixtures_scored": 0,
            "completed_forecasts_scored": 0, "awaiting_result_or_match": 0,
            "withheld_or_invalid_forecasts": 0, "model_versions": [],
        }],
        "scored_matches": [],
    })
    monkeypatch.setattr(tracking_runner, "find_daily_report", lambda *args: {
        "as_of_date": "2026-10-22", "predictions": [],
    })

    monkeypatch.setattr(
        tracking_runner, "load_cached_results_payload",
        lambda repo: ({"response": []}, "CACHE_AVAILABLE"),
    )
    output = tmp_path / "ledger.json"
    ledger = tracking_runner.run(date(2026, 10, 23), str(output))
    assert ledger["evaluations"][0]["tracking_state"] == "NO_FORECASTS_TO_SCORE"
    assert ledger["last_attempt"]["status"] == "NO_FORECASTS_TO_SCORE"

def test_paper_tracking_never_calls_live_provider_when_result_cache_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_RUN_ID", "999")
    monkeypatch.setattr(tracking_runner, "list_relevant_runs", lambda session, repo: [])
    monkeypatch.setattr(tracking_runner, "find_latest_ledger", lambda *args: {
        "product": "Veltrix Football", "model_status": "PAPER_TRACKING_ONLY",
        "evaluations": [], "scored_matches": [],
    })
    monkeypatch.setattr(tracking_runner, "find_daily_report", lambda *args: {
        "as_of_date": "2026-10-23", "predictions": [_prediction(88)],
    })
    monkeypatch.setattr(
        tracking_runner, "load_cached_results_payload",
        lambda repo: ({"response": []}, "CACHE_UNAVAILABLE"),
    )
    output = tmp_path / "ledger.json"
    ledger = tracking_runner.run(date(2026, 10, 23), str(output))
    attempt = ledger["last_attempt"]["attempts"][0]
    assert ledger["last_attempt"]["status"] == "EVALUATED"
    assert attempt["status"] == "EVALUATED"
    assert attempt["completed_forecasts_scored"] == 0
    assert attempt["awaiting_result_or_match"] == 1
    assert "no live football-provider request was made" in attempt["detail"]



def test_goal_market_paper_tracking_uses_only_pre_kickoff_odds_and_settles_flat_stakes():
    report = {
        "as_of_date": "2026-10-23",
        "predictions": [{
            **_prediction(55),
            "kickoff_local": "2026-10-23T18:00:00+01:00",
            "goal_market_calibration": {
                "status": "APPLIED_PROSPECTIVELY",
                "model_version": "goal-platt-test-v1",
                "markets": ["btts_yes", "over_2_5"],
            },
            "btts_yes": 0.62,
            "over_2_5": 0.57,
            "goal_markets_model": "experimental_recent_goals_poisson",
            "the_odds_api_market_odds": {
                "provider": "The Odds API",
                "commence_time": "2026-10-23T17:00:00Z",
                "fetched_at": "2026-10-23T16:00:00Z",
                "markets": {
                    "btts": [{
                        "bookmaker": "Book A",
                        "last_update": "2026-10-23T15:00:00Z",
                        "outcomes": [{"name": "Yes", "price": 1.85}, {"name": "No", "price": 2.0}],
                    }],
                    "totals": [{
                        "bookmaker": "Book A",
                        "last_update": "2026-10-23T15:00:00Z",
                        "outcomes": [
                            {"name": "Over", "point": 2.5, "price": 1.9},
                            {"name": "Under", "point": 2.5, "price": 1.95},
                            {"name": "Over", "point": 3.5, "price": 3.0},
                            {"name": "Under", "point": 3.5, "price": 1.3},
                        ],
                    }],
                },
            },
        }],
    }
    result = evaluate_report(report, {"response": [_result(55, 2, 1)]})
    assert len(result["goal_market_matches"]) == 2
    assert result["goal_market_metrics"]["settled_selections"] == 2
    assert {row["market"] for row in result["goal_market_matches"]} == {"btts", "over_2_5"}
    assert {row["selection"] for row in result["goal_market_matches"]} == {"yes", "over"}
    over_row = next(row for row in result["goal_market_matches"] if row["market"] == "over_2_5")
    assert over_row["decimal_odds"] == 1.9
    assert over_row["unit_profit"] == 0.9
    assert over_row["devigged_market_probability"] < over_row["model_probability"]


def test_goal_market_paper_tracking_rejects_post_kickoff_odds():
    report = {
        "as_of_date": "2026-10-23",
        "predictions": [{
            **_prediction(56),
            "kickoff_local": "2026-10-23T18:00:00+01:00",
            "btts_yes": 0.62,
            "over_2_5": 0.57,
            "the_odds_api_market_odds": {
                "commence_time": "2026-10-23T17:00:00Z",
                "fetched_at": "2026-10-23T18:01:00Z",
                "markets": {
                    "btts": [{"bookmaker": "Book A", "outcomes": [{"name": "Yes", "price": 1.9}, {"name": "No", "price": 1.9}]}],
                    "totals": [{"bookmaker": "Book A", "outcomes": [{"name": "Over", "point": 2.5, "price": 1.9}, {"name": "Under", "point": 2.5, "price": 1.9}]}],
                },
            },
        }],
    }
    result = evaluate_report(report, {"response": [_result(56, 2, 1)]})
    assert result["goal_market_matches"] == []
    assert result["goal_market_metrics"]["settled_selections"] == 0



def test_goal_market_ledger_preserves_non_numeric_provider_fixture_ids():
    evaluation = {
        "report_date": "2026-10-28",
        "fixtures_scored": 0,
        "completed_forecasts_scored": 0,
        "awaiting_result_or_match": 0,
        "withheld_or_invalid_forecasts": 0,
        "matches": [],
        "goal_market_matches": [{
            "fixture_id": "odds-event-abc123",
            "market": "btts",
            "selection": "yes",
            "actual_outcome": True,
            "unit_stake": 1.0,
            "unit_profit": 0.8,
            "settlement": "WON",
        }],
        "goal_market_metrics": {"settled_selections": 1},
    }
    ledger = merge_paper_ledger({}, evaluation)
    assert len(ledger["goal_market_scored"]) == 1
    assert ledger["goal_market_scored"][0]["fixture_id"] == "odds-event-abc123"
    assert ledger["goal_market_metrics"]["settled_selections"] == 1
