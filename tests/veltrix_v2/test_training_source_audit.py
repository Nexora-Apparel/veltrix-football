from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from veltrix_v2.contracts import ProviderObservation
from veltrix_v2.contracts.odds import OddsSnapshot
from veltrix_v2.evaluation.certification import (
    certify_prediction_publication,
    certify_release,
)
from veltrix_v2.evaluation.paper_ledger import PaperLedger, PaperSelection
from veltrix_v2.evaluation.settlement import MarketBet, MatchResult
from veltrix_v2.evaluation.certification_evidence import (
    TrainingObservationEvidence,
    audit_walk_forward_training_sources,
    audit_walk_forward_integrity,
    audit_odds_snapshot_sources,
    audit_paper_ledger_sources,
)
from veltrix_v2.evaluation.multi_competition_walk_forward import (
    run_multi_competition_walk_forward,
)
from veltrix_v2.evaluation.walk_forward import WalkForwardFold
from veltrix_v2.models.poisson_strength import TrainingMatch
from veltrix_v2.quality.eligibility import SourceApproval

UTC = timezone.utc


def _match(fixture_id, day, home, away, goals):
    kickoff = datetime(2026, 1, day, 15, tzinfo=UTC)
    return TrainingMatch(
        fixture_id=fixture_id,
        competition_key="league-a",
        season="2025-26",
        kickoff_utc=kickoff,
        available_at_utc=kickoff + timedelta(hours=2),
        home_team_id=home,
        away_team_id=away,
        home_goals=goals[0],
        away_goals=goals[1],
        source_observation_id=f"obs-{fixture_id}",
        availability_basis="source_timestamp",
        source_training_approved=True,
    )


def _observation(*, available_at, approval_id="approval-1", event_at=None, provider_entity_id="provider-match-1", entity_type="match_result", fixture_id=None):
    event_at = event_at or datetime(2026, 1, 1, 15, tzinfo=UTC)
    return ProviderObservation(
        provider="provider-a",
        endpoint="/matches/result",
        entity_type=entity_type,
        provider_entity_id=provider_entity_id,
        competition_key="league-a",
        season="2025-26",
        retrieved_at_utc=available_at + timedelta(minutes=1),
        source_event_time_utc=event_at,
        available_at_utc=available_at,
        payload_sha256="a" * 64,
        schema_version="1",
        rights_approval_id=approval_id,
        values={
            "home_goals": 2,
            "away_goals": 0,
            **({"fixture_id": fixture_id} if fixture_id else {}),
        },
    )


def _approval(*, permitted_uses=("collection", "storage", "model_training", "benchmarking", "public_display", "commercial_use"), data_type="match_result", approval_id="approval-result"):
    return SourceApproval(
        approval_id=approval_id,
        provider="provider-a",
        competition_key="league-a",
        data_type=data_type,
        status="approved",
        valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
        permitted_uses=permitted_uses,
    )


def _source_records(training_available_at=None):
    return (
        TrainingObservationEvidence(
            "obs-train-1",
            _observation(
                available_at=training_available_at or datetime(2026, 1, 1, 17, tzinfo=UTC),
                provider_entity_id="provider-training-result",
                approval_id="approval-result",
                fixture_id="train-1",
            ),
        ),
        TrainingObservationEvidence(
            "obs-test-1",
            _observation(
                available_at=datetime(2026, 1, 10, 17, tzinfo=UTC),
                event_at=datetime(2026, 1, 10, 15, tzinfo=UTC),
                provider_entity_id="provider-heldout-result",
                approval_id="approval-result",
                fixture_id="test-1",
            ),
        ),
        TrainingObservationEvidence(
            "obs-odds-1",
            _observation(
                available_at=datetime(2026, 1, 10, 14, 54, tzinfo=UTC),
                event_at=datetime(2026, 1, 10, 14, 54, tzinfo=UTC),
                provider_entity_id="provider-odds-feed",
                entity_type="odds_quote",
                approval_id="approval-odds",
                fixture_id="test-1",
            ),
        ),
    )


def _walk_forward(monkeypatch):
    rows = [
        _match("train-1", 1, "A", "B", (2, 0)),
        _match("test-1", 10, "A", "B", (1, 1)),
    ]

    class FakeModel:
        converged = True
        objective = 1.0
        training_availability_bases = ("source_timestamp",)
        training_fixture_ids = ("train-1",)
        training_observation_ids = ("obs-train-1",)

        def expected_goals(self, home_team_id, away_team_id):
            return (1.4, 1.1)

    def fake_folds(fixtures, **kwargs):
        return (WalkForwardFold(
            fold_number=1,
            train_fixture_ids=("train-1",),
            test_fixture_ids=("test-1",),
            test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
            test_end_utc=datetime(2026, 1, 17, tzinfo=UTC),
            training_label_cutoff_utc=datetime(2026, 1, 9, tzinfo=UTC),
        ),)

    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.build_expanding_walk_forward_folds",
        fake_folds,
    )
    monkeypatch.setattr(
        "veltrix_v2.evaluation.multi_market_walk_forward.fit_poisson_strength_model",
        lambda *args, **kwargs: FakeModel(),
    )
    return run_multi_competition_walk_forward(
        rows,
        competition_seasons=(("league-a", "2025-26"),),
        first_test_start_utc=datetime(2026, 1, 10, tzinfo=UTC),
        test_window=timedelta(days=7),
        n_splits=1,
        minimum_training_matches=1,
    )


def test_training_source_audit_uses_recorded_fold_cutoff_and_rights(monkeypatch):
    report = _walk_forward(monkeypatch)
    observation = _observation(
        available_at=datetime(2026, 1, 1, 17, tzinfo=UTC)
    )
    audit = audit_walk_forward_training_sources(
        report,
        _source_records(),
        (_approval(),),
    )
    assert audit.passed
    assert audit.observation_count == 2
    assert audit.approved_observation_ids == ("obs-test-1", "obs-train-1")
    assert audit.rejected_observations == ()


def test_training_source_audit_rejects_observation_available_after_fold_cutoff(monkeypatch):
    report = _walk_forward(monkeypatch)
    observation = _observation(
        available_at=datetime(2026, 1, 10, 17, tzinfo=UTC)
    )
    audit = audit_walk_forward_training_sources(
        report,
        _source_records(datetime(2026, 1, 10, 17, tzinfo=UTC)),
        (_approval(),),
    )
    assert not audit.passed
    assert "observation_not_available_at_forecast_cutoff" in {
        reason for _, reason in audit.rejected_observations
    }


def test_training_source_audit_rejects_missing_model_training_rights(monkeypatch):
    report = _walk_forward(monkeypatch)
    observation = _observation(
        available_at=datetime(2026, 1, 1, 17, tzinfo=UTC)
    )
    audit = audit_walk_forward_training_sources(
        report,
        _source_records(),
        (_approval(permitted_uses=("collection", "storage", "benchmarking")),),
    )
    assert not audit.passed
    assert any("model_training" in reason for _, reason in audit.rejected_observations)


def test_training_source_audit_rejects_missing_observation_record(monkeypatch):
    report = _walk_forward(monkeypatch)
    audit = audit_walk_forward_training_sources(report, _source_records()[1:], (_approval(),))
    assert not audit.passed
    assert ("obs-train-1", "training_observation_missing") in audit.rejected_observations


def test_walk_forward_integrity_audits_temporal_windows_and_identity_isolation(monkeypatch):
    report = _walk_forward(monkeypatch)
    audit = audit_walk_forward_integrity(report)
    assert audit.passed
    assert audit.fold_count == 1
    assert audit.held_out_fixture_ids == ("test-1",)


def test_walk_forward_integrity_rejects_training_cutoff_at_test_start(monkeypatch):
    report = _walk_forward(monkeypatch)
    scope = report.scope_reports[0]
    fold = scope.folds[0]
    invalid_fold = replace(fold, training_label_cutoff_utc=fold.test_start_utc)
    invalid_scope = replace(scope, folds=(invalid_fold,))
    invalid_report = replace(report, scope_reports=(invalid_scope,))
    audit = audit_walk_forward_integrity(invalid_report)
    assert not audit.passed
    assert "TRAINING_CUTOFF_OR_TEST_WINDOW_ORDER_INVALID" in audit.failures


def test_walk_forward_integrity_rejects_unbound_heldout_result_observation(monkeypatch):
    report = _walk_forward(monkeypatch)
    scope = report.scope_reports[0]
    fold = scope.folds[0]
    invalid_fold = replace(fold, test_fixture_kickoffs=())
    invalid_report = replace(report, scope_reports=(replace(scope, folds=(invalid_fold,)),))
    audit = audit_walk_forward_integrity(invalid_report)
    assert not audit.passed
    assert "HELD_OUT_RESULT_PROVENANCE_INVALID" in audit.failures



def test_prediction_publication_certification_derives_samples_and_quality_from_reports(monkeypatch):
    report = _walk_forward(monkeypatch)
    certification = certify_prediction_publication(
        report,
        _source_records(),
        (_approval(),),
    )
    assert not certification.passed
    failures = {row.market: row.failed_gates for row in certification.markets}
    for market in ("1X2", "BTTS", "TOTALS"):
        assert "PREDICTION_WALK_FORWARD_SAMPLE_BELOW_1000" in failures[market]
        assert "PREDICTION_CALIBRATION_NOT_PASSED" in failures[market]


def test_prediction_publication_certification_fails_when_source_rights_are_missing(monkeypatch):
    report = _walk_forward(monkeypatch)
    certification = certify_prediction_publication(
        report,
        _source_records(),
        (_approval(permitted_uses=("collection", "storage", "benchmarking")),),
    )
    assert not certification.passed
    assert all(
        "PREDICTION_SOURCE_NOT_APPROVED" in row.failed_gates
        for row in certification.markets
    )



def _odds_snapshot(source_observation_id="obs-odds-1", source_id="provider-a"):
    kickoff = datetime(2026, 1, 10, 15, tzinfo=UTC)
    captured = kickoff - timedelta(minutes=5)
    return OddsSnapshot(
        snapshot_id="odds-test-1",
        fixture_id="test-1",
        source_id=source_id,
        bookmaker_id="bookmaker-a",
        market="1X2",
        selection="HOME",
        decimal_odds=Decimal("2.5"),
        captured_at=captured,
        kickoff_at=kickoff,
        provider_quote_at=captured - timedelta(seconds=1),
        source_observation_id=source_observation_id,
    )


def test_odds_source_audit_requires_quote_source_record_and_benchmark_rights(monkeypatch):
    report = _walk_forward(monkeypatch)
    audit = audit_odds_snapshot_sources(
        report,
        (_odds_snapshot(),),
        _source_records(),
        (_approval(data_type="odds_quote", approval_id="approval-odds"),),
    )
    assert audit.passed
    assert audit.approved_snapshot_ids == ("odds-test-1",)


def test_odds_source_audit_rejects_missing_source_observation_binding(monkeypatch):
    report = _walk_forward(monkeypatch)
    audit = audit_odds_snapshot_sources(
        report,
        (_odds_snapshot(source_observation_id=None),),
        _source_records(),
        (_approval(data_type="odds_quote", approval_id="approval-odds"),),
    )
    assert not audit.passed
    assert "odds_source_observation_id_missing" in {
        reason for _, reason in audit.rejected_snapshots
    }


def test_odds_source_audit_rejects_provider_mismatch(monkeypatch):
    report = _walk_forward(monkeypatch)
    audit = audit_odds_snapshot_sources(
        report,
        (_odds_snapshot(source_id="other-provider"),),
        _source_records(),
        (_approval(data_type="odds_quote", approval_id="approval-odds"),),
    )
    assert not audit.passed
    assert "odds_source_provider_mismatch" in {
        reason for _, reason in audit.rejected_snapshots
    }



def _ledger_source_record(observation_id, entity_type, available_at, *, approval_id):
    return TrainingObservationEvidence(
        observation_id,
        ProviderObservation(
            provider="provider-a",
            endpoint=f"/{entity_type}",
            entity_type=entity_type,
            provider_entity_id=f"provider-{observation_id}",
            competition_key="league-a",
            season="2025-26",
            retrieved_at_utc=available_at + timedelta(seconds=10),
            source_event_time_utc=available_at,
            available_at_utc=available_at,
            payload_sha256="b" * 64,
            schema_version="1",
            rights_approval_id=approval_id,
            values={"fixture_id": "test-1"},
        ),
    )


def _paper_ledger_and_records():
    kickoff = datetime(2026, 1, 10, 15, tzinfo=UTC)
    forecast_at = datetime(2026, 1, 10, 14, tzinfo=UTC)
    selected_at = datetime(2026, 1, 10, 14, 56, tzinfo=UTC)
    odds_captured = datetime(2026, 1, 10, 14, 55, tzinfo=UTC)
    odds = OddsSnapshot(
        snapshot_id="ledger-odds-1",
        fixture_id="test-1",
        source_id="provider-a",
        bookmaker_id="bookmaker-a",
        market="1X2",
        selection="HOME",
        decimal_odds=Decimal("2.5"),
        captured_at=odds_captured,
        kickoff_at=kickoff,
        provider_quote_at=odds_captured - timedelta(seconds=1),
        source_observation_id="obs-ledger-odds",
    )
    selection = PaperSelection(
        selection_id="selection-1",
        report_id="report-1",
        forecast_id="forecast-1",
        prediction_certification_id="prediction-cert-1",
        bet=MarketBet(
            fixture_id="test-1",
            market="1X2",
            selection="HOME",
            decimal_odds=Decimal("2.5"),
            stake=Decimal("1"),
        ),
        odds_snapshot=odds,
        model_probability=Decimal("0.6"),
        model_version="v2-test",
        forecast_generated_at_utc=forecast_at,
        selected_at_utc=selected_at,
        forecast_source_observation_ids=("obs-ledger-feature",),
    )
    ledger = PaperLedger().record_selection(selection)
    result = MatchResult(
        fixture_id="test-1",
        status="COMPLETED",
        home_goals_regulation=2,
        away_goals_regulation=0,
        match_date=datetime(2026, 1, 10).date(),
        match_date_source_observation_id="obs-ledger-result",
    )
    ledger = ledger.settle_selection(
        "selection-1",
        result,
        event_id="settlement-event-1",
        result_observed_at_utc=datetime(2026, 1, 10, 17, 5, tzinfo=UTC),
        result_source_observation_id="obs-ledger-result",
        settled_at_utc=datetime(2026, 1, 10, 17, 6, tzinfo=UTC),
    )
    records = (
        _ledger_source_record(
            "obs-ledger-feature", "team_stats",
            datetime(2026, 1, 10, 13, 30, tzinfo=UTC),
            approval_id="approval-team",
        ),
        _ledger_source_record(
            "obs-ledger-odds", "odds_quote",
            datetime(2026, 1, 10, 14, 54, tzinfo=UTC),
            approval_id="approval-odds",
        ),
        _ledger_source_record(
            "obs-ledger-result", "match_result",
            datetime(2026, 1, 10, 17, 0, tzinfo=UTC),
            approval_id="approval-result",
        ),
    )
    approvals = (
        SourceApproval(
            "approval-team", "provider-a", "league-a", "team_stats", "approved",
            datetime(2025, 1, 1, tzinfo=UTC),
            ("collection", "storage", "model_training", "public_display", "commercial_use"),
        ),
        SourceApproval(
            "approval-odds", "provider-a", "league-a", "odds_quote", "approved",
            datetime(2025, 1, 1, tzinfo=UTC),
            ("collection", "storage", "benchmarking", "commercial_use"),
        ),
        SourceApproval(
            "approval-result", "provider-a", "league-a", "match_result", "approved",
            datetime(2025, 1, 1, tzinfo=UTC),
            ("collection", "storage", "benchmarking", "model_training", "public_display", "commercial_use"),
        ),
    )
    return ledger, records, approvals


def test_paper_ledger_source_audit_checks_forecast_odds_and_result_records(monkeypatch):
    report = _walk_forward(monkeypatch)
    ledger, records, approvals = _paper_ledger_and_records()
    audit = audit_paper_ledger_sources(report, ledger, records, approvals)
    assert audit.passed
    assert audit.selection_count == 1
    assert audit.settlement_count == 1
    assert set(audit.approved_observation_ids) == {
        "obs-ledger-feature", "obs-ledger-odds", "obs-ledger-result"
    }


def test_paper_ledger_source_audit_rejects_missing_training_rights(monkeypatch):
    report = _walk_forward(monkeypatch)
    ledger, records, approvals = _paper_ledger_and_records()
    approvals = tuple(
        replace(row, permitted_uses=("collection", "storage", "benchmarking"))
        if row.approval_id == "approval-team" else row
        for row in approvals
    )
    audit = audit_paper_ledger_sources(report, ledger, records, approvals)
    assert not audit.passed
    assert any("model_training" in reason for _, reason in audit.rejected_observations)



def _complete_benchmark_odds():
    kickoff = datetime(2026, 1, 10, 15, tzinfo=UTC)
    captured = kickoff - timedelta(minutes=5)
    return tuple(
        OddsSnapshot(
            snapshot_id=f"benchmark-{selection.lower()}",
            fixture_id="test-1",
            source_id="provider-a",
            bookmaker_id="bookmaker-a",
            market="1X2",
            selection=selection,
            decimal_odds=Decimal("2.5"),
            captured_at=captured,
            kickoff_at=kickoff,
            provider_quote_at=captured - timedelta(seconds=1),
            source_observation_id="obs-odds-1",
        )
        for selection in ("HOME", "DRAW", "AWAY")
    )


def test_value_bet_certification_derives_metrics_and_benchmark_from_records(monkeypatch):
    report = _walk_forward(monkeypatch)
    ledger, ledger_records, ledger_approvals = _paper_ledger_and_records()
    observations = _source_records() + ledger_records
    result = certify_release(
        report,
        ledger,
        _complete_benchmark_odds(),
        observations,
        ledger_approvals,
        benchmark_source_id="provider-a",
        benchmark_bookmaker_id="bookmaker-a",
    )
    assert not result.passed
    assert all(
        "WALK_FORWARD_SAMPLE_BELOW_1000" in market.failed_gates
        for market in result.markets
    )
    assert "SOURCE_NOT_APPROVED" not in result.markets[0].failed_gates
    assert "TIMESTAMPED_ODDS_COVERAGE_BELOW_98_PERCENT" in result.markets[1].failed_gates
    assert result.evidence[0].timestamped_odds_coverage == Decimal("1")
