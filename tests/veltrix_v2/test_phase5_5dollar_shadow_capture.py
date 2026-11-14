from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
import sys
from types import SimpleNamespace

import pytest

from scripts.phase5_collect_5dollar_shadow import (
    _approval_from_rows,
    _approved_competition_ids,
    _request_page,
    main,
)
from veltrix_v2.data.contracts import ApprovalStatus, DataUsePurpose

UTC = timezone.utc
NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def approval_row():
    return {
        "approval_id": "approval-5dollar-community-fixture-result-2026-11",
        "provider": "5DollarFootballAPI",
        "source_id": "5dollarfootballapi",
        "competition_scope": "3118717965,4160026622",
        "data_type": "fixture_result",
        "status": "APPROVED",
        "permitted_uses": ["CACHE", "COLLECTION", "MODEL_TRAINING", "STORAGE"],
        "commercial_use_allowed": True,
        "terms_url": "https://5dollarfootballapi.com/terms",
        "terms_version": "October 2026",
        "evidence_uri": "https://example.test/approval",
        "evidence_sha256": "a" * 64,
        "rights_basis": "TERMS",
        "reviewed_at": NOW - timedelta(days=2),
        "reviewer_id": "VELTRIX_PHASE2_REVIEW",
        "valid_from": NOW - timedelta(days=2),
        "valid_until": None,
        "attribution_required": True,
        "attribution_text": "Football data by 5DollarFootballAPI",
        "attribution_url": "https://5dollarfootballapi.com",
        "raw_redistribution_allowed": False,
    }


def approval_event(status="APPROVED", event_id=1):
    return {
        "event_id": event_id,
        "approval_id": "approval-5dollar-community-fixture-result-2026-11",
        "status": status,
        "evidence_uri": "https://example.test/approval-event",
        "evidence_sha256": "b" * 64,
        "effective_at": NOW - timedelta(days=2),
        "recorded_at": NOW - timedelta(days=2),
        "reason_code": "INITIAL_APPROVAL" if status == "APPROVED" else "REVOKED",
    }


def test_approval_loader_resolves_append_only_status_events_and_uses():
    approval = _approval_from_rows(
        approval_row(), [approval_event()], rights_evaluated_at=NOW
    )
    assert approval.status is ApprovalStatus.APPROVED
    assert DataUsePurpose.COLLECTION in approval.permitted_uses
    assert DataUsePurpose.MODEL_TRAINING in approval.permitted_uses
    assert DataUsePurpose.BENCHMARKING not in approval.permitted_uses


def test_approval_loader_fails_closed_on_revocation():
    with pytest.raises(PermissionError, match="FIVEDOLLAR_SOURCE_NOT_APPROVED_AT_USE_TIME"):
        _approval_from_rows(
            approval_row(),
            [approval_event(), approval_event("REVOKED", 2)],
            rights_evaluated_at=NOW,
        )


def test_approval_loader_fails_closed_on_malformed_status_history():
    event = approval_event()
    event["evidence_sha256"] = "bad"
    with pytest.raises(PermissionError):
        _approval_from_rows(approval_row(), [event], rights_evaluated_at=NOW)


def test_competition_selection_intersects_approval_scope_with_verified_crosswalks():
    approval = _approval_from_rows(
        approval_row(), [approval_event()], rights_evaluated_at=NOW
    )
    registry = SimpleNamespace(competition_crosswalks={
        "3118717965": object(), "4160026622": object(), "999": object()
    })
    assert _approved_competition_ids(approval, registry) == ["3118717965", "4160026622"]


def test_manual_cli_defaults_to_dry_run_without_secrets_or_side_effects(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["phase5_collect_5dollar_shadow"])
    assert main() == 0
    output = capsys.readouterr().out
    assert '"mode": "DRY_RUN"' in output
    assert '"would_connect_to_database": false' in output
    assert '"would_call_provider": false' in output


def test_403_competition_response_is_not_retried_and_still_advances_pacer(monkeypatch):
    import scripts.phase5_collect_5dollar_shadow as capture

    def denied(*args, **kwargs):
        raise HTTPError("https://example.test", 403, "Forbidden", {}, None)

    monkeypatch.setattr(capture, "urlopen", denied)
    pacing = {"last_started": None}
    with pytest.raises(PermissionError, match="FIVEDOLLAR_COMPETITION_NOT_ENTITLED"):
        _request_page(
            "not-a-real-key",
            competition_id="3118717965",
            status="finished",
            start_at=NOW - timedelta(days=90),
            end_at=NOW,
            page=1,
            pacing_state=pacing,
            before_request=lambda: NOW,
        )
    assert isinstance(pacing["last_started"], float)


def test_staging_persistence_flag_does_not_execute_without_execute(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "phase5_collect_5dollar_shadow", "--persist-staging"
    ])
    assert main() == 0
    output = capsys.readouterr().out
    assert '"mode": "DRY_RUN"' in output
    assert '"persist_staging": true' in output
