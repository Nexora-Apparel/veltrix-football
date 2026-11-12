from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.contracts import ProviderObservation
from veltrix_v2.evaluation.certification_evidence import (
    TrainingObservationEvidence,
    audit_walk_forward_training_sources,
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


def _observation(*, available_at, approval_id="approval-1", event_at=None, provider_entity_id="provider-match-1"):
    event_at = event_at or datetime(2026, 1, 1, 15, tzinfo=UTC)
    return ProviderObservation(
        provider="provider-a",
        endpoint="/matches/result",
        entity_type="match_result",
        provider_entity_id=provider_entity_id,
        competition_key="league-a",
        season="2025-26",
        retrieved_at_utc=available_at + timedelta(minutes=1),
        source_event_time_utc=event_at,
        available_at_utc=available_at,
        payload_sha256="a" * 64,
        schema_version="1",
        rights_approval_id=approval_id,
        values={"home_goals": 2, "away_goals": 0},
    )


def _approval(*, permitted_uses=("collection", "storage", "model_training", "benchmarking")):
    return SourceApproval(
        approval_id="approval-1",
        provider="provider-a",
        competition_key="league-a",
        data_type="match_result",
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
            ),
        ),
        TrainingObservationEvidence(
            "obs-test-1",
            _observation(
                available_at=datetime(2026, 1, 10, 17, tzinfo=UTC),
                event_at=datetime(2026, 1, 10, 15, tzinfo=UTC),
                provider_entity_id="provider-heldout-result",
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
