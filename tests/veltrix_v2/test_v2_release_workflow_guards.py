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
