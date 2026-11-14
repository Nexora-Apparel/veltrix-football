from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
import sys
from types import SimpleNamespace

import pytest

from scripts.phase5_collect_5dollar_shadow import (
    _approval_from_rows,
    _approved_competition_ids,
    _request_page,
    _build_public_summary,
    run_capture,
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



def test_public_summary_is_an_explicit_aggregate_only_allowlist():
    summary = _build_public_summary({
        "status": "SHADOW_CAPTURE_COMPLETE",
        "provider": "5DollarFootballAPI",
        "requests_used": 4,
        "request_cap": 14,
        "crosswalk_registry": {
            "provider": "5DollarFootballAPI",
            "fixture_crosswalks": 100,
            "team_crosswalks": 20,
            "competition_crosswalks": 2,
            "validity": "VERIFIED_FROM_VERIFIED_AT_FORWARD_ONLY",
        },
        "captured_first_observed_rows": 100,
        "mapped_upcoming_targets": 25,
        "forecast_count": 20,
        "admitted_shadow_predictions": 15,
        "persisted_capture_pages": 2,
        "persisted_shadow_ledger_events": 15,
        "paper_ledger_persisted_to_staging": True,
        "paper_ledger_chain_verified": True,
        "duplicate_predictions_skipped": 3,
        "evidence_persisted_to_staging": True,
        "publication_status": "LOCKED",
        "settlement_status": "LOCKED",
        "database_writes": True,
        "fixture_ids": ["private-fixture"],
        "ledger_events": [{"fixture_id": "private-fixture", "event_sha256": "a" * 64}],
        "page_manifests": [{"raw_response_sha256": "b" * 64}],
        "odds": {"home": 2.0},
        "probabilities": {"home": 0.5},
        "api_key": "must-never-leak",
    })
    rendered = repr(summary)
    for forbidden in (
        "private-fixture", "event_sha256", "raw_response_sha256",
        "probabilities", "api_key", "must-never-leak", "odds",
    ):
        assert forbidden not in rendered
    assert summary["admitted_shadow_predictions"] == 15
    assert summary["persisted_shadow_ledger_events"] == 15
    assert summary["public_publication"] is False
    assert summary["paper_ledger_chain_verified"] is True
    assert summary["duplicate_predictions_skipped"] == 3



@pytest.mark.parametrize("persist_staging", [False, True])
def test_run_capture_orchestrates_mocked_pages_with_optional_staging_ledger(
    monkeypatch, tmp_path, persist_staging
):
    import scripts.phase5_collect_5dollar_shadow as capture

    approval = SimpleNamespace(
        approval_id="approval-test",
        permitted_uses=frozenset({DataUsePurpose.COLLECTION, DataUsePurpose.CACHE,
                                  DataUsePurpose.MODEL_TRAINING, DataUsePurpose.STORAGE}),
        attribution_required=True,
        attribution_text="Attribution",
        attribution_url="https://example.test",
        raw_redistribution_allowed=False,
    )
    registry = SimpleNamespace(summary=lambda: {
        "provider": "5DollarFootballAPI",
        "fixture_crosswalks": 1,
        "team_crosswalks": 2,
        "competition_crosswalks": 1,
        "validity": "VERIFIED_FROM_VERIFIED_AT_FORWARD_ONLY",
    })
    observation = SimpleNamespace(fixture_id="fixture-history")
    target = SimpleNamespace(
        fixture_id="fixture-target",
        kickoff_at=NOW + timedelta(days=2),
    )
    prediction = SimpleNamespace(
        fixture_id="fixture-target",
        model_version="poisson-results-v2",
    )
    forecast_report = SimpleNamespace(
        forecast_count=1,
        skipped_no_history=0,
        skipped_invalid_targets=0,
    )
    event = SimpleNamespace(
        event_type="SHADOW_PREDICTION",
        fixture_id="fixture-target",
        model_version="poisson-results-v2",
        event_sha256="c" * 64,
    )

    monkeypatch.setattr(capture, "_read_staging_context", lambda *a, **k: (approval, registry))
    monkeypatch.setattr(capture, "_approved_competition_ids", lambda *a: ["3118717965"])
    monkeypatch.setattr(capture, "_refresh_approval", lambda *a: (approval, NOW))
    monkeypatch.setattr(capture, "evaluate_source_use",
                        lambda *a, **k: SimpleNamespace(allowed=True, reason_code=None))
    monkeypatch.setattr(
        capture, "_request_page",
        lambda *a, **k: (b"{}", {}, NOW, NOW + timedelta(seconds=1), 200),
    )

    def fake_capture_page(raw, headers, *, status, **kwargs):
        return (
            [observation] if status == "finished" else [target],
            {
                "status_filter": status,
                "quota_remaining": 100,
                "persisted_to_staging": None,
            },
        )

    monkeypatch.setattr(capture, "_capture_page", fake_capture_page)
    monkeypatch.setattr(capture, "predict_batch", lambda *a, **k: forecast_report)
    monkeypatch.setattr(
        capture, "admit_prospective_observed_shadow_forecasts",
        lambda *a, **k: SimpleNamespace(admitted=[prediction], rejected=[]),
    )
    monkeypatch.setattr(capture, "_hash_files", lambda paths: "d" * 64)

    class LocalStore:
        def __init__(self, path):
            self.path = path

        def append_prediction(self, item):
            assert item is prediction
            return event

    monkeypatch.setattr(capture, "JsonlPaperLedgerStore", LocalStore)
    persistence_calls = []
    def fake_persist(dsn, predictions):
        persistence_calls.append((dsn, list(predictions)))
        return {
            "events_appended": 1,
            "duplicate_predictions_skipped": 0,
            "ledger_event_count": 1,
            "ledger_head_sha256": "e" * 64,
            "chain_verified": True,
        }

    monkeypatch.setattr(
        capture, "_persist_paper_predictions_to_staging",
        fake_persist if persist_staging else
        lambda *a, **k: pytest.fail("staging persistence must remain disabled"),
    )

    result = run_capture(
        api_key="mock-key",
        staging_dsn="mock-dsn",
        history_days=90,
        upcoming_days=14,
        max_fixtures=25,
        out_dir=tmp_path,
        persist_staging=persist_staging,
    )

    assert result["requests_used"] == 2
    assert result["forecast_count"] == 1
    assert result["admitted_shadow_predictions"] == 1
    assert result["persisted_shadow_ledger_events"] == (1 if persist_staging else 0)
    assert result["paper_ledger_persisted_to_staging"] is persist_staging
    assert result["database_writes"] is persist_staging
    assert len(persistence_calls) == (1 if persist_staging else 0)
    if persist_staging:
        assert persistence_calls[0][1] == [prediction]
    assert result["public_publication"] is False
    assert result["telegram_delivery"] is False
    assert result["schedule_activation"] is False
    assert (tmp_path / "public_summary.json").exists()
    public = (tmp_path / "public_summary.json").read_text()
    assert "fixture-target" not in public
    assert "event_sha256" not in public
