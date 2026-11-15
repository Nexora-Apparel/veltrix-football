from pathlib import Path

from scripts.phase5_settle_5dollar_shadow import _public_summary


def test_public_settlement_summary_excludes_row_level_fixture_identity():
    summary = _public_summary({
        "status": "SETTLEMENT_RECONCILIATION_COMPLETE",
        "shadow_targets": 25,
        "eligible_unsettled_targets": 3,
        "provider_requests": 2,
        "provider_pages_persisted": 2,
        "finished_rows_observed": 60,
        "settlements_appended": 3,
        "quarantined_rows": [{"fixture_id": "private-fixture", "reason": "mismatch"}],
        "ledger_events": 28,
        "ledger_chain_verified": True,
        "ledger_post_commit_verified": True,
        "prospective_scorecard": {"settled_predictions": 3, "certification_status": "NOT_CERTIFIED"},
    })
    rendered = repr(summary)
    assert summary["settlements_appended"] == 3
    assert summary["ledger_post_commit_verified"] is True
    assert summary["quarantined_count"] == 1
    assert summary["publication"] is False
    assert summary["telegram"] is False
    assert summary["schedule"] is False
    assert summary["value_betting"] == "LOCKED"
    assert "private-fixture" not in rendered
    assert "fixture_id" not in rendered
    assert "event_sha256" not in rendered


def test_manual_settlement_workflow_is_bounded_and_has_no_schedule_or_publication():
    workflow = Path(".github/workflows/phase5-5dollar-shadow-settlement.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "FIVEDOLLARFOOTBALL_API_KEY" in workflow
    assert "VELTRIX_STAGING_DATABASE_URL" in workflow
    assert "settlement_public_summary.json" in workflow
    assert "telegram" not in workflow.lower()
    assert "publish" not in workflow.lower()
