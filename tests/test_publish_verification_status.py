from scripts.publish_verification_status import build_status


def test_verification_receipt_marks_live_pipeline_passed_only_after_visibility(tmp_path):
    import json
    report_path = tmp_path / "daily_predictions.json"
    report_path.write_text(json.dumps({
        "as_of_date": "2026-10-31",
        "same_day_only": True,
        "future_fixtures_considered": 1,
        "predictions": [{"home_team": "A", "away_team": "B", "status": "EXPERIMENTAL_ONLY", "probabilities": {"home_win": .5, "draw": .2, "away_win": .3}}],
        "fixture_visibility_validation": {"status": "PASSED"},
    }))
    status = build_status({
        "GITHUB_RUN_ID": "123",
        "GITHUB_SHA": "abc",
        "VELTRIX_REPORT_PATH": str(report_path),
        "VELTRIX_TELEGRAM_CONFIGURED": "true",
        "VELTRIX_STEP_UNIT_TESTS": "success",
        "VELTRIX_STEP_DASHBOARD_JS": "success",
        "VELTRIX_STEP_FIXTURE_GENERATION": "success",
        "VELTRIX_STEP_FIXTURE_VISIBILITY": "success",
        "VELTRIX_STEP_ODDS_ENRICHMENT": "success",
        "VELTRIX_STEP_VALUE_EVIDENCE_UPDATE": "success",
        "VELTRIX_STEP_VALUE_EVIDENCE_ARTIFACT": "success",
        "VELTRIX_STEP_VALUE_CERTIFICATE": "success",
        "VELTRIX_STEP_TELEGRAM_WEBHOOK": "success",
        "VELTRIX_STEP_TELEGRAM_DELIVERY": "success",
        "VELTRIX_STEP_DAILY_REPORT_ARTIFACT": "success",
        "VELTRIX_STEP_PAPER_LEDGER_ARTIFACT": "success",
        "VELTRIX_STEP_COMMAND_DATA_PUBLICATION": "success",
        "VELTRIX_STEP_PAPER_TRACKING": "success",
    })
    assert status["overall_status"] == "PASSED"
    assert status["release_status"] == "LOCKED_SHADOW_MODE"
    assert status["betting_alerts_enabled"] is False
    assert status["report_summary"]["fixture_rows"] == 1
    assert status["report_summary"]["fixture_status_counts"] == {"EXPERIMENTAL_ONLY": 1}


def test_verification_receipt_flags_failed_fixture_validation():
    status = build_status({
        "VELTRIX_STEP_UNIT_TESTS": "success",
        "VELTRIX_STEP_DASHBOARD_JS": "success",
        "VELTRIX_STEP_FIXTURE_GENERATION": "success",
        "VELTRIX_STEP_FIXTURE_VISIBILITY": "failure",
        "VELTRIX_STEP_COMMAND_DATA_PUBLICATION": "skipped",
    })
    assert status["overall_status"] == "NEEDS_REVIEW"


def test_verification_receipt_does_not_mislabel_failed_live_generation_as_tests_only():
    status = build_status({
        "VELTRIX_STEP_UNIT_TESTS": "success",
        "VELTRIX_STEP_DASHBOARD_JS": "success",
        "VELTRIX_STEP_FIXTURE_GENERATION": "failure",
    })
    assert status["overall_status"] == "NEEDS_REVIEW"
    assert status["validation_scope"] == "LIVE_PIPELINE"


def test_same_day_recovery_is_reported_as_degraded_not_fresh(tmp_path):
    import json
    report_path = tmp_path / "daily_predictions.json"
    report_path.write_text(json.dumps({
        "as_of_date": "2026-10-31",
        "publication_status": "REUSED_SNAPSHOT_NOT_REFRESHED",
        "future_fixtures_considered": 1,
        "predictions": [{"home_team": "A", "away_team": "B", "status": "INSUFFICIENT_HISTORY"}],
        "fixture_visibility_validation": {"status": "PASSED"},
    }))
    env = {
        "VELTRIX_REPORT_PATH": str(report_path),
        "VELTRIX_TELEGRAM_CONFIGURED": "true",
        "VELTRIX_STEP_UNIT_TESTS": "success",
        "VELTRIX_STEP_DASHBOARD_JS": "success",
        "VELTRIX_STEP_FIXTURE_GENERATION": "failure",
        "VELTRIX_STEP_REPORT_RECOVERY": "success",
        "VELTRIX_STEP_FIXTURE_VISIBILITY": "success",
        "VELTRIX_STEP_VALUE_EVIDENCE_UPDATE": "success",
        "VELTRIX_STEP_VALUE_EVIDENCE_ARTIFACT": "success",
        "VELTRIX_STEP_DAILY_REPORT_ARTIFACT": "success",
        "VELTRIX_STEP_PAPER_LEDGER_ARTIFACT": "success",
        "VELTRIX_STEP_COMMAND_DATA_PUBLICATION": "success",
        "VELTRIX_STEP_PAPER_TRACKING": "success",
        "VELTRIX_STEP_TELEGRAM_WEBHOOK": "success",
        "VELTRIX_STEP_TELEGRAM_DELIVERY": "success",
    }
    status = build_status(env)
    assert status["overall_status"] == "DEGRADED_REUSED_SNAPSHOT"
    assert status["validation_scope"] == "SAME_DAY_RECOVERY"
    assert status["report_summary"]["publication_status"] == "REUSED_SNAPSHOT_NOT_REFRESHED"


def test_recovery_without_telegram_configuration_is_not_marked_complete(tmp_path):
    import json
    report_path = tmp_path / "daily_predictions.json"
    report_path.write_text(json.dumps({
        "as_of_date": "2026-10-31",
        "future_fixtures_considered": 0,
        "predictions": [],
        "fixture_visibility_validation": {"status": "PASSED"},
    }))
    env = {
        "VELTRIX_REPORT_PATH": str(report_path),
        "VELTRIX_STEP_UNIT_TESTS": "success",
        "VELTRIX_STEP_DASHBOARD_JS": "success",
        "VELTRIX_STEP_FIXTURE_GENERATION": "failure",
        "VELTRIX_STEP_REPORT_RECOVERY": "success",
        "VELTRIX_STEP_FIXTURE_VISIBILITY": "success",
        "VELTRIX_STEP_VALUE_EVIDENCE_UPDATE": "success",
        "VELTRIX_STEP_VALUE_EVIDENCE_ARTIFACT": "success",
        "VELTRIX_STEP_DAILY_REPORT_ARTIFACT": "success",
        "VELTRIX_STEP_PAPER_LEDGER_ARTIFACT": "success",
        "VELTRIX_STEP_COMMAND_DATA_PUBLICATION": "success",
        "VELTRIX_STEP_PAPER_TRACKING": "success",
        "VELTRIX_STEP_TELEGRAM_WEBHOOK": "success",
        "VELTRIX_STEP_TELEGRAM_DELIVERY": "skipped",
    }
    assert build_status(env)["overall_status"] == "NEEDS_REVIEW"


def test_test_only_receipt_preserves_last_full_telegram_delivery_status():
    from scripts.publish_verification_status import merge_test_only_status

    previous = {
        "run_id": "live-123",
        "overall_status": "DEGRADED_REUSED_SNAPSHOT",
        "validation_scope": "SAME_DAY_RECOVERY",
        "telegram_configured": True,
        "steps": {"telegram_delivery": "success", "command_data_publication": "success"},
        "report_summary": {"as_of_date": "2026-11-02", "fixture_rows": 23},
    }
    current = {
        "run_id": "tests-456",
        "commit_sha": "abc123",
        "recorded_at_utc": "2026-11-02T10:40:00+00:00",
        "overall_status": "TESTS_PASSED",
        "validation_scope": "TESTS_ONLY",
        "telegram_configured": False,
        "steps": {"unit_tests": "success", "dashboard_js": "success"},
    }

    merged = merge_test_only_status(previous, current)
    assert merged["run_id"] == "live-123"
    assert merged["validation_scope"] == "SAME_DAY_RECOVERY"
    assert merged["telegram_configured"] is True
    assert merged["steps"]["telegram_delivery"] == "success"
    assert merged["latest_test_status"] == "TESTS_PASSED"
    assert merged["latest_test_run"]["run_id"] == "tests-456"


def test_failed_test_only_receipt_marks_review_without_erasing_last_live_run():
    from scripts.publish_verification_status import merge_test_only_status

    previous = {
        "run_id": "live-123",
        "overall_status": "PASSED",
        "validation_scope": "LIVE_PIPELINE",
        "telegram_configured": True,
        "steps": {"telegram_delivery": "success"},
    }
    current = {
        "run_id": "tests-789",
        "overall_status": "NEEDS_REVIEW",
        "validation_scope": "TESTS_ONLY",
        "steps": {"unit_tests": "failure", "dashboard_js": "success"},
    }
    merged = merge_test_only_status(previous, current)
    assert merged["overall_status"] == "NEEDS_REVIEW"
    assert merged["last_full_pipeline_status"] == "PASSED"
    assert merged["run_id"] == "live-123"
    assert merged["telegram_configured"] is True
