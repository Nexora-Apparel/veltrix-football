from scripts import phase5_collect_5dollar_shadow as capture


def test_admitted_prediction_tuple_is_normalized_before_staging(monkeypatch):
    admitted = (object(), object())
    observed = {}

    def fake_persist(dsn, predictions):
        observed["dsn"] = dsn
        observed["predictions"] = predictions
        return {"events_appended": len(predictions)}

    monkeypatch.setattr(
        capture, "_persist_paper_predictions_to_staging", fake_persist
    )

    result = capture._persist_admitted_predictions_to_staging(
        "postgresql://staging", admitted
    )

    assert observed["dsn"] == "postgresql://staging"
    assert isinstance(observed["predictions"], list)
    assert observed["predictions"] == list(admitted)
    assert result == {"events_appended": 2}


def test_fixtures_only_summary_never_executes_model_or_admits_predictions():
    summary = capture._build_fixtures_only_summary(
        requests_used=14,
        history_days=90,
        upcoming_days=14,
        max_fixtures=25,
        crosswalk_registry={"fixtures": 100, "teams": 40, "competitions": 7},
        captured_first_observed_rows=100,
        rejected_first_observed_rows=2,
        mapped_upcoming_targets=25,
        persisted_capture_pages=14,
    )
    assert summary["status"] == "FIXTURE_SNAPSHOT_CAPTURE_COMPLETE"
    assert summary["fixture_snapshot_only"] is True
    assert summary["model_execution"] is False
    assert summary["forecast_count"] == 0
    assert summary["admitted_shadow_predictions"] == 0
    assert summary["duplicate_predictions_skipped"] == 0
    assert summary["paper_ledger_persisted_to_staging"] is False
    assert summary["normalized_fixture_writes"] == 0
    assert summary["normalized_result_writes"] == 0
    assert summary["feature_writes"] == 0
    assert summary["prediction_writes"] == 0
    assert summary["odds_quote_writes"] == 0
    assert summary["settlement_status"] == "NOT_SETTLED"


def test_fixtures_only_summary_reports_empty_upcoming_window_without_fabricating_targets():
    summary = capture._build_fixtures_only_summary(
        requests_used=14,
        history_days=90,
        upcoming_days=14,
        max_fixtures=25,
        crosswalk_registry={"fixtures": 100, "teams": 40, "competitions": 7},
        captured_first_observed_rows=100,
        rejected_first_observed_rows=0,
        mapped_upcoming_targets=0,
        persisted_capture_pages=14,
    )
    assert summary["status"] == "NO_UPCOMING_FIXTURE_TARGETS"
    assert summary["mapped_upcoming_targets"] == 0
    assert summary["model_execution"] is False
