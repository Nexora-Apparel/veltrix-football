from scripts.publish_verification_status import build_status


def test_verification_receipt_marks_live_pipeline_passed_only_after_visibility():
    status = build_status({
        "GITHUB_RUN_ID": "123",
        "GITHUB_SHA": "abc",
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
