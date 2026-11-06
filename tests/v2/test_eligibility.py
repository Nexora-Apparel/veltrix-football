from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.domain.contracts import (
    FixtureEligibilityInput,
    ForecastCandidate,
    ForecastStatus,
    HistoryState,
    IdentityState,
    TeamHistoryEvidence,
)
from veltrix_v2.domain.eligibility import (
    evaluate_fixture_eligibility,
    validate_public_forecast,
)


NOW = datetime(2026, 11, 6, 8, 0, tzinfo=timezone.utc)
KICKOFF = NOW + timedelta(hours=4)


def evidence(count=8, *ids):
    return TeamHistoryEvidence(HistoryState.FOUND, count, tuple(ids))


def fixture(**overrides):
    values = dict(
        fixture_id="fixture-001",
        competition_supported=True,
        identity_state=IdentityState.VERIFIED,
        home_history=evidence(8, "hist-home-1", "hist-home-2"),
        away_history=evidence(7, "hist-away-1", "hist-away-2"),
        kickoff_at_utc=KICKOFF,
        evaluated_at_utc=NOW,
    )
    values.update(overrides)
    return FixtureEligibilityInput(**values)


def candidate(decision, *, origin="fixture_specific", probs=None):
    return ForecastCandidate(
        fixture_id=decision.fixture_id,
        market="1X2",
        probabilities=probs or {"home": 0.48, "draw": 0.23, "away": 0.29},
        model_version="v2-test.1",
        feature_snapshot_id="features-001",
        generated_at_utc=NOW,
        evidence_ids=decision.evidence_ids,
        origin=origin,
    )


def test_verified_fixture_with_sufficient_history_is_eligible():
    decision = evaluate_fixture_eligibility(fixture())
    assert decision.status is ForecastStatus.ELIGIBLE
    assert decision.publishable is True
    assert len(decision.evidence_ids) == 4


@pytest.mark.parametrize(
    ("home", "away", "expected"),
    [
        (
            TeamHistoryEvidence(HistoryState.NOT_FOUND, 0),
            evidence(8, "away-1"),
            ForecastStatus.HISTORY_NOT_FOUND,
        ),
        (
            TeamHistoryEvidence(HistoryState.QUERY_FAILED, 0),
            evidence(8, "away-1"),
            ForecastStatus.HISTORY_QUERY_FAILED,
        ),
        (
            TeamHistoryEvidence(HistoryState.IDENTITY_MISMATCH, 0),
            evidence(8, "away-1"),
            ForecastStatus.HISTORY_IDENTITY_MISMATCH,
        ),
        (
            evidence(2, "home-1"),
            evidence(8, "away-1"),
            ForecastStatus.INSUFFICIENT_HISTORY,
        ),
    ],
)
def test_missing_failed_or_insufficient_history_is_withheld(home, away, expected):
    decision = evaluate_fixture_eligibility(
        fixture(home_history=home, away_history=away)
    )
    assert decision.status is expected
    assert decision.publishable is False


def test_unsupported_competition_is_withheld():
    decision = evaluate_fixture_eligibility(fixture(competition_supported=False))
    assert decision.status is ForecastStatus.UNSUPPORTED_COMPETITION
    assert not decision.publishable


@pytest.mark.parametrize("identity", [IdentityState.AMBIGUOUS, IdentityState.UNRESOLVED])
def test_unverified_identity_is_withheld(identity):
    decision = evaluate_fixture_eligibility(fixture(identity_state=identity))
    assert decision.status is ForecastStatus.AMBIGUOUS_FIXTURE_IDENTITY
    assert not decision.publishable


def test_past_or_live_kickoff_is_withheld():
    decision = evaluate_fixture_eligibility(
        fixture(kickoff_at_utc=NOW - timedelta(minutes=1))
    )
    assert decision.status is ForecastStatus.PAST_KICKOFF
    assert not decision.publishable


def test_generic_global_prior_cannot_be_published_even_with_valid_probabilities():
    decision = evaluate_fixture_eligibility(fixture())
    generic = candidate(decision, origin="global_prior")
    with pytest.raises(ValueError, match="non-fixture-specific"):
        validate_public_forecast(decision, generic)


def test_forecast_cannot_be_published_when_eligibility_failed():
    decision = evaluate_fixture_eligibility(
        fixture(home_history=TeamHistoryEvidence(HistoryState.NOT_FOUND, 0))
    )
    with pytest.raises(ValueError, match="not eligible"):
        validate_public_forecast(decision, candidate(decision))


@pytest.mark.parametrize(
    "probabilities",
    [
        {"home": 0.48, "draw": 0.23, "away": 0.28},
        {"home": float("nan"), "draw": 0.2, "away": 0.8},
        {"home": -0.1, "draw": 0.3, "away": 0.8},
    ],
)
def test_invalid_probability_vectors_are_rejected(probabilities):
    decision = evaluate_fixture_eligibility(fixture())
    with pytest.raises(ValueError):
        validate_public_forecast(decision, candidate(decision, probs=probabilities))


def test_identical_global_prior_vectors_are_never_public_forecasts():
    first = evaluate_fixture_eligibility(fixture(fixture_id="fixture-home-a"))
    second = evaluate_fixture_eligibility(fixture(fixture_id="fixture-home-b"))
    # The same neutral-prior vector must not be published for unrelated fixtures.
    first_candidate = candidate(first, origin="global_prior")
    second_candidate = candidate(second, origin="global_prior")
    assert first_candidate.probabilities == second_candidate.probabilities
    with pytest.raises(ValueError, match="non-fixture-specific"):
        validate_public_forecast(first, first_candidate)
    with pytest.raises(ValueError, match="non-fixture-specific"):
        validate_public_forecast(second, second_candidate)
