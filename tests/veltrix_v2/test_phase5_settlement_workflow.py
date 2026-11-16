from pathlib import Path

from scripts.phase5_settle_5dollar_shadow import (
    _load_v2_feature_links,
    _public_summary,
    _targets,
)
from veltrix_v2.ledger.paper_predictions import PaperLedgerEvent, V2_PIT_MODEL_VERSION


def test_public_settlement_summary_excludes_row_level_fixture_identity():
    summary = _public_summary({
        "status": "SETTLEMENT_RECONCILIATION_COMPLETE",
        "shadow_targets": 25,
        "v2_pit_targets": 7,
        "v2_pit_feature_links_available": 7,
        "eligible_unsettled_targets": 3,
        "provider_requests": 2,
        "provider_pages_persisted": 2,
        "finished_rows_observed": 60,
        "settlements_appended": 3,
        "shadow_settlements_appended": 2,
        "v2_pit_settlements_appended": 1,
        "quarantined_rows": [{"fixture_id": "private-fixture", "reason": "mismatch"}],
        "ledger_events": 28,
        "ledger_chain_verified": True,
        "ledger_post_commit_verified": True,
        "prospective_scorecard": {"settled_predictions": 3, "certification_status": "NOT_CERTIFIED"},
    })
    rendered = repr(summary)
    assert summary["settlements_appended"] == 3
    assert summary["v2_pit_targets"] == 7
    assert summary["v2_pit_feature_links_available"] == 7
    assert summary["v2_pit_settlements_appended"] == 1
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


def _prediction_event(event_type="PREDICTION", model_version=V2_PIT_MODEL_VERSION):
    return PaperLedgerEvent(
        sequence=1,
        event_type=event_type,
        fixture_id="5dollarfootballapi:777",
        model_version=model_version,
        recorded_at="2026-11-15T20:00:00+00:00",
        payload={
            "evidence_class":"PIT_CERTIFIED" if event_type == "PREDICTION" else "PROSPECTIVE_OBSERVED_ONLY",
            "point_in_time_certifiable":True,
            "target_provider":"5DollarFootballAPI",
            "target_source_id":"5dollarfootballapi",
            "target_source_fixture_id":"777",
            "target_provider_competition_id":"101",
            "kickoff_at":"2026-11-20T20:00:00+00:00",
        },
        previous_event_sha256="0"*64,
        event_sha256="a"*64,
    )


def test_settlement_target_discovery_includes_only_v2_pit_and_observed_shadow():
    class Ledger:
        events = (
            _prediction_event(),
            _prediction_event("SHADOW_PREDICTION", "veltrix-observed-shadow-v1"),
            _prediction_event("PREDICTION", "legacy-model-v1"),
        )
    targets = _targets(Ledger())
    assert len(targets) == 2
    assert {event.model_version for event in targets} == {
        V2_PIT_MODEL_VERSION, "veltrix-observed-shadow-v1"
    }


def test_v2_feature_link_loader_does_not_touch_database_when_no_v2_targets():
    class NoQueryConnection:
        def execute(self, *_args, **_kwargs):
            raise AssertionError("database query must not run without V2 targets")
    assert _load_v2_feature_links(NoQueryConnection(), []) == ()


def test_v2_feature_link_loader_requires_exact_append_only_link_row():
    event = _prediction_event()
    row = (
        "a"*64,"b"*64,15,25,"c"*64,"d"*64,"e"*64,"f"*64,
        "2026-11-15T18:00:00+00:00","2026-11-15T17:00:00+00:00",
        "2026-11-15T20:01:00+00:00",1001,1002,1003,"101","11","22",
    )
    class Cursor:
        def __init__(self, row=None, rows=None):
            self._row=row
            self._rows=rows or []
        def fetchone(self):
            return self._row
        def fetchall(self):
            return self._rows
    class Connection:
        def execute(self, sql, _params=None):
            if "to_regclass" in sql:
                return Cursor((True,))
            return Cursor(rows=[row])
    links = _load_v2_feature_links(Connection(), [event])
    assert list(links) == ["a"*64]
    assert links["a"*64]["link_sha256"] == "b"*64
    assert links["a"*64]["feature_snapshot_id"] == 15
    assert links["a"*64]["canonical_competition_id"] == "1001"
    assert links["a"*64]["provider_home_team_id"] == "11"
