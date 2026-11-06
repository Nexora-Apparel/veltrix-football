"""Single authoritative forecast eligibility and publication guard."""
from __future__ import annotations

import math
from datetime import timezone

from .contracts import (
    EligibilityDecision,
    FixtureEligibilityInput,
    ForecastCandidate,
    ForecastStatus,
    HistoryState,
    IdentityState,
)

MIN_TEAM_MATCHES = 5


def _utc_aware(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def evaluate_fixture_eligibility(
    item: FixtureEligibilityInput,
    *,
    min_team_matches: int = MIN_TEAM_MATCHES,
) -> EligibilityDecision:
    """Return one deterministic eligibility decision for every market.

    No fallback probabilities are generated here. Any missing, failed or
    ambiguous evidence produces a withheld decision.
    """
    if not item.fixture_id.strip():
        raise ValueError("fixture_id is required")
    if min_team_matches < 1:
        raise ValueError("min_team_matches must be positive")

    kickoff = _utc_aware(item.kickoff_at_utc)
    evaluated = _utc_aware(item.evaluated_at_utc)

    def denied(status: ForecastStatus, reason: str) -> EligibilityDecision:
        return EligibilityDecision(
            fixture_id=item.fixture_id,
            status=status,
            reason_code=reason,
            publishable=False,
        )

    if kickoff <= evaluated:
        return denied(ForecastStatus.PAST_KICKOFF, "KICKOFF_NOT_IN_FUTURE")

    if not item.competition_supported:
        return denied(
            ForecastStatus.UNSUPPORTED_COMPETITION,
            "COMPETITION_NOT_SUPPORTED",
        )

    if item.identity_state is IdentityState.AMBIGUOUS:
        return denied(
            ForecastStatus.AMBIGUOUS_FIXTURE_IDENTITY,
            "FIXTURE_IDENTITY_AMBIGUOUS",
        )
    if item.identity_state is not IdentityState.VERIFIED:
        return denied(
            ForecastStatus.AMBIGUOUS_FIXTURE_IDENTITY,
            "FIXTURE_IDENTITY_UNRESOLVED",
        )

    history_states = (item.home_history.state, item.away_history.state)
    if HistoryState.QUERY_FAILED in history_states:
        return denied(ForecastStatus.HISTORY_QUERY_FAILED, "HISTORY_QUERY_FAILED")
    if HistoryState.IDENTITY_MISMATCH in history_states:
        return denied(
            ForecastStatus.HISTORY_IDENTITY_MISMATCH,
            "HISTORY_TEAM_IDENTITY_MISMATCH",
        )
    if HistoryState.NOT_FOUND in history_states:
        return denied(ForecastStatus.HISTORY_NOT_FOUND, "TEAM_HISTORY_NOT_FOUND")
    if HistoryState.INSUFFICIENT_COVERAGE in history_states:
        return denied(
            ForecastStatus.INSUFFICIENT_HISTORY,
            "HISTORY_COVERAGE_INSUFFICIENT",
        )

    if any(
        evidence.state is not HistoryState.FOUND
        or evidence.match_count < min_team_matches
        for evidence in (item.home_history, item.away_history)
    ):
        return denied(
            ForecastStatus.INSUFFICIENT_HISTORY,
            "MINIMUM_TEAM_HISTORY_NOT_MET",
        )

    evidence_ids = tuple(dict.fromkeys(
        item.home_history.evidence_ids + item.away_history.evidence_ids
    ))
    if not evidence_ids:
        return denied(
            ForecastStatus.INSUFFICIENT_HISTORY,
            "HISTORY_EVIDENCE_REFERENCES_MISSING",
        )

    return EligibilityDecision(
        fixture_id=item.fixture_id,
        status=ForecastStatus.ELIGIBLE,
        reason_code="ALL_ELIGIBILITY_CHECKS_PASSED",
        publishable=True,
        evidence_ids=evidence_ids,
    )


def validate_public_forecast(
    decision: EligibilityDecision,
    forecast: ForecastCandidate,
) -> None:
    """Raise ValueError unless the candidate is safe to enter a public report."""
    if not decision.publishable or decision.status is not ForecastStatus.ELIGIBLE:
        raise ValueError("forecast blocked: fixture is not eligible")
    if forecast.fixture_id != decision.fixture_id:
        raise ValueError("forecast fixture does not match eligibility decision")
    if forecast.origin != "fixture_specific":
        raise ValueError("non-fixture-specific forecast origins cannot be published")
    if not forecast.model_version.strip():
        raise ValueError("model_version is required")
    if not forecast.feature_snapshot_id.strip():
        raise ValueError("feature_snapshot_id is required")
    if not forecast.evidence_ids:
        raise ValueError("forecast evidence references are required")
    if not set(forecast.evidence_ids).issubset(set(decision.evidence_ids)):
        raise ValueError("forecast references evidence outside the eligibility decision")
    if forecast.generated_at_utc.tzinfo is None:
        raise ValueError("generated_at_utc must be timezone-aware")
    if not forecast.probabilities:
        raise ValueError("probabilities are required")
    values = tuple(forecast.probabilities.values())
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in values):
        raise ValueError("probabilities must be finite values between 0 and 1")
    if not math.isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("probabilities must sum to 1")
