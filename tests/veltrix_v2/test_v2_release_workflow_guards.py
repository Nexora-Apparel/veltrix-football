from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_legacy_dashboard_refresh_cannot_publish_while_v2_bundle_is_unwired():
    source = _workflow("refresh-dashboard-snapshot.yml")
    assert "publish:" in source
    assert "if: false" in source
    assert "legacy report projection" in source
    assert "one verified immutable bundle" in source


def test_legacy_daily_prediction_pipeline_remains_paused():
    source = _workflow("daily-fixture-predictions.yml")
    assert "daily-predictions:" in source
    assert "# PAUSED by user request" in source
    assert "if: false" in source


def test_v2_telegram_bundle_dispatcher_remains_locked_without_schedule():
    source = _workflow("telegram-delivery-recovery.yml")
    assert "v2-telegram-delivery:" in source
    assert "if: false" in source
    assert "scripts/veltrix_v2/dispatch_public_telegram_bundle.py" in source
    assert "public-data/v2_report_bundle.json" in source
    dispatcher = (ROOT / "scripts" / "veltrix_v2" / "dispatch_public_telegram_bundle.py").read_text(encoding="utf-8")
    assert 'Path("command-data/public-data/v2_report_bundle.json")' in dispatcher
    assert 'parts[2] != "bundles"' not in dispatcher
    assert "send_telegram_report.py" not in source
    assert "daily_predictions.json" not in source
    assert "schedule:" not in source



def test_legacy_paper_tracking_recovery_cannot_republish_legacy_ledger():
    source = _workflow("paper-tracking-recovery.yml")
    assert "recover-paper-ledger:" in source
    assert "if: false" in source
    assert "legacy recovery job" in source
    assert "publish_command_data.py" in source



def test_exhausted_goal_api_and_strikerapi_probe_workflows_remain_paused():
    goal = _workflow("verify-goal-api.yml")
    striker = _workflow("verify-strikerapi.yml")
    assert "goal-api-readonly-probe:" in goal
    assert "if: false" in goal
    assert "next monthly credit reset" in goal
    assert "qualify:" in striker
    assert "if: false" in striker
    assert "next monthly credit reset" in striker



def test_legacy_historical_model_reconstruction_remains_paused():
    source = _workflow("historical-model-reconstruction.yml")
    assert "reconstruct-archived-reports:" in source
    assert "if: false" in source
    assert "excluded legacy model stack" in source



def test_legacy_prediction_backtests_and_report_watchdog_remain_paused():
    watchdog = _workflow("daily-report-watchdog.yml")
    historical = _workflow("historical-model-backtest.yml")
    womens = _workflow("womens-model-backtest.yml")
    assert "ensure-daily-report:" in watchdog and "if: false" in watchdog
    assert "backtest:" in historical and "if: false" in historical
    assert "womens-backtest:" in womens and "if: false" in womens



def test_historical_archive_seed_uses_archive_only_mode():
    source = _workflow("seed-oct31-report-archive.yml")
    assert "publish_command_data.py" in source
    assert "--archive-only" in source
    assert "public-data/daily_predictions.json" not in source


def test_manual_provider_capture_workflows_gate_staging_persistence_explicitly():
    fivedollar = _workflow("phase5-5dollar-shadow-capture.yml")
    odds = _workflow("phase5-odds-api-quota-capture.yml")
    assert "workflow_dispatch:" in fivedollar
    assert "--execute" in fivedollar
    assert "persist_staging:" in fivedollar
    assert "default: false" in fivedollar
    assert "${{ inputs.persist_staging && '--persist-staging' || '' }}" in fivedollar
    assert "FIVEDOLLARFOOTBALL_API_KEY" in fivedollar
    assert "VELTRIX_STAGING_DATABASE_URL" in fivedollar
    assert "workflow_dispatch:" in odds
    assert "phase5_capture_odds_api_quota --execute --persist-staging" in odds
    assert "THE_ODDS_API_KEY" in odds
    assert "VELTRIX_STAGING_DATABASE_URL" in odds
