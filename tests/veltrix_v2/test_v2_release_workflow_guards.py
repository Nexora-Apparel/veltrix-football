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


def test_legacy_telegram_recovery_remains_paused():
    source = _workflow("telegram-delivery-recovery.yml")
    assert "deliver-published-report:" in source
    assert "if: false" in source



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
