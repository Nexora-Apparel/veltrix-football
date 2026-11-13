"""Provider-independent, fail-closed temporal eligibility rules for Phase 4.

This module is deliberately isolated from providers, prediction models, and persistence.
It validates evidence supplied by callers; it does not manufacture missing evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


TRUSTED_TIMESTAMP_BASES = frozenset({
    "provider_timestamp",
    "archival_snapshot_timestamp",
    "documented_guarantee",
})
STATE_AS_OF_CUTOFF = "state_as_of_cutoff"
FORECAST_FOR_FIXTURE = "forecast_for_fixture"


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reason_codes: tuple[str, ...]
    published_at: datetime | None = None
    cutoff_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "reason_codes": list(self.reason_codes),
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "cutoff_at": self.cutoff_at.isoformat() if self.cutoff_at else None,
        }


def parse_aware_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp only when an explicit UTC offset is present."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw or len(raw) == 10:  # date-only values are not instants
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _scope_matches(approval: Mapping[str, Any], observation: Mapping[str, Any]) -> bool:
    scope = approval.get("scope")
    if not isinstance(scope, Mapping):
        return False
    required = ("provider", "product", "endpoint", "field_family", "competition", "season")
    return all(
        scope.get(key) == observation.get(key)
        for key in required
        if key in observation
    ) and all(scope.get(key) not in (None, "", "*") for key in required)


def _rights_reason(
    approval: Mapping[str, Any] | None,
    observation: Mapping[str, Any],
    cutoff: datetime,
    required_use: str,
) -> str | None:
    if not isinstance(approval, Mapping):
        return "RIGHTS_NOT_APPROVED"
    if approval.get("status") != "APPROVED":
        return "RIGHTS_NOT_APPROVED"
    purposes = approval.get("permitted_purposes", ())
    if required_use not in purposes or not _scope_matches(approval, observation):
        return "RIGHTS_NOT_APPROVED"
    revoked_at = parse_aware_timestamp(approval.get("revoked_at"))
    if approval.get("revoked_at") is not None and revoked_at is None:
        return "RIGHTS_NOT_APPROVED"
    if revoked_at is not None and revoked_at <= cutoff:
        return "RIGHTS_NOT_APPROVED"
    starts = parse_aware_timestamp(approval.get("effective_from"))
    ends = parse_aware_timestamp(approval.get("expires_at"))
    if approval.get("effective_from") is not None and starts is None:
        return "RIGHTS_NOT_APPROVED"
    if approval.get("expires_at") is not None and ends is None:
        return "RIGHTS_NOT_APPROVED"
    if starts is not None and starts > cutoff:
        return "RIGHTS_NOT_APPROVED"
    if ends is not None and ends <= cutoff:
        return "RIGHTS_NOT_APPROVED"
    return None


def evaluate_observation(
    observation: Mapping[str, Any],
    prediction_cutoff_at: str | datetime,
    rights_approval: Mapping[str, Any] | None,
    *,
    required_use: str = "model_training",
    archive_proof_verified: bool = False,
) -> EligibilityDecision:
    """Evaluate one immutable observation against a frozen cutoff and rights scope."""
    cutoff = parse_aware_timestamp(prediction_cutoff_at)
    if cutoff is None:
        return EligibilityDecision(False, ("CUTOFF_TIMESTAMP_UNTRUSTED",))

    reasons: list[str] = []
    published = parse_aware_timestamp(observation.get("source_published_at"))
    if observation.get("source_published_at") is None:
        reasons.append("SOURCE_TIMESTAMP_MISSING")
    elif published is None:
        reasons.append("SOURCE_TIMESTAMP_UNTRUSTED")

    basis = observation.get("source_timestamp_basis")
    if basis not in TRUSTED_TIMESTAMP_BASES:
        reasons.append("SOURCE_TIMESTAMP_UNTRUSTED")

    if published is not None and published > cutoff:
        reasons.append("PUBLISHED_AFTER_CUTOFF")

    retrieved = parse_aware_timestamp(observation.get("retrieved_at"))
    if observation.get("retrieved_at") is None or retrieved is None:
        reasons.append("RETRIEVAL_TIMESTAMP_UNTRUSTED")
    elif retrieved > cutoff and not (
        basis == "archival_snapshot_timestamp" and archive_proof_verified
    ):
        reasons.append("RETRIEVED_AFTER_CUTOFF_WITHOUT_ARCHIVE_PROOF")

    effective_raw = observation.get("source_effective_at")
    effective = parse_aware_timestamp(effective_raw) if effective_raw is not None else None
    if effective_raw is not None and effective is None:
        reasons.append("SOURCE_EFFECTIVE_TIMESTAMP_UNTRUSTED")
    semantics = observation.get("temporal_semantics", STATE_AS_OF_CUTOFF)
    if semantics not in (STATE_AS_OF_CUTOFF, FORECAST_FOR_FIXTURE):
        reasons.append("FIELD_SEMANTICS_UNVERIFIED")
    elif effective is not None and effective > cutoff:
        if semantics != FORECAST_FOR_FIXTURE:
            reasons.append("FUTURE_EFFECTIVE_STATE")
        else:
            kickoff = parse_aware_timestamp(observation.get("fixture_kickoff_at"))
            if kickoff is None or effective > kickoff:
                reasons.append("FIELD_SEMANTICS_UNVERIFIED")

    if observation.get("revision_history_complete", True) is not True:
        reasons.append("REVISION_HISTORY_INCOMPLETE")

    rights_reason = _rights_reason(rights_approval, observation, cutoff, required_use)
    if rights_reason:
        reasons.append(rights_reason)

    # Stable ordering and de-duplication make decisions deterministic.
    ordered = tuple(dict.fromkeys(reasons))
    return EligibilityDecision(not ordered, ordered, published, cutoff)


def select_as_of(
    observations: Iterable[Mapping[str, Any]],
    prediction_cutoff_at: str | datetime,
    rights_approval: Mapping[str, Any] | None,
    *,
    required_use: str = "model_training",
    archive_proof_ids: frozenset[str] = frozenset(),
) -> Mapping[str, Any] | None:
    """Select the latest eligible version known by cutoff; never mutate input rows."""
    candidates: list[tuple[datetime, str, Mapping[str, Any]]] = []
    for row in observations:
        proof_id = row.get("archive_proof_id")
        decision = evaluate_observation(
            row,
            prediction_cutoff_at,
            rights_approval,
            required_use=required_use,
            archive_proof_verified=bool(proof_id and proof_id in archive_proof_ids),
        )
        if decision.eligible and decision.published_at is not None:
            candidates.append((
                decision.published_at,
                str(row.get("observation_id", "")),
                row,
            ))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[-1][2]


def feature_set_sha256(features: Mapping[str, Any]) -> str:
    """Hash canonical feature evidence; missing keys remain absent, never zero-filled."""
    canonical = json.dumps(
        features,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
