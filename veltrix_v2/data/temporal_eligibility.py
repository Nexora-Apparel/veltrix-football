"""Provider-independent, fail-closed temporal eligibility rules for Phase 4.

This module is deliberately isolated from providers, prediction models, and persistence.
It validates evidence supplied by callers; it does not manufacture missing evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Iterable, Mapping


TRUSTED_TIMESTAMP_BASES = frozenset({
    "provider_timestamp",
    "archival_snapshot_timestamp",
    "documented_guarantee",
})
STATE_AS_OF_CUTOFF = "state_as_of_cutoff"
FORECAST_FOR_FIXTURE = "forecast_for_fixture"
REQUIRED_RIGHTS_SCOPE = (
    "provider", "product", "endpoint", "field_family", "competition", "season"
)


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
        if not raw or len(raw) == 10:
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
    # Both sides must explicitly identify every dimension. Missing scope must
    # never become an implicit wildcard.
    return all(
        key in observation
        and observation.get(key) not in (None, "")
        and scope.get(key) == observation.get(key)
        and scope.get(key) not in (None, "", "*")
        for key in REQUIRED_RIGHTS_SCOPE
    )


def _rights_reason(
    approval: Mapping[str, Any] | None,
    observation: Mapping[str, Any],
    rights_evaluated_at: datetime | None,
    required_use: str,
) -> str | None:
    if rights_evaluated_at is None or not isinstance(approval, Mapping):
        return "RIGHTS_NOT_APPROVED"
    if approval.get("status") != "APPROVED":
        return "RIGHTS_NOT_APPROVED"
    purposes = approval.get("permitted_purposes", ())
    if not isinstance(purposes, (list, tuple, set, frozenset)):
        return "RIGHTS_NOT_APPROVED"
    if required_use not in purposes or not _scope_matches(approval, observation):
        return "RIGHTS_NOT_APPROVED"

    starts = parse_aware_timestamp(approval.get("effective_from"))
    ends = parse_aware_timestamp(approval.get("expires_at"))
    revoked = parse_aware_timestamp(approval.get("revoked_at"))
    if approval.get("effective_from") is not None and starts is None:
        return "RIGHTS_NOT_APPROVED"
    if approval.get("expires_at") is not None and ends is None:
        return "RIGHTS_NOT_APPROVED"
    if approval.get("revoked_at") is not None and revoked is None:
        return "RIGHTS_NOT_APPROVED"

    # Rights are checked at the time of the downstream use, not at the
    # historical prediction cutoff. A later revocation blocks new use now.
    if starts is not None and starts > rights_evaluated_at:
        return "RIGHTS_NOT_APPROVED"
    if ends is not None and ends <= rights_evaluated_at:
        return "RIGHTS_NOT_APPROVED"
    if revoked is not None and revoked <= rights_evaluated_at:
        return "RIGHTS_NOT_APPROVED"
    return None


def evaluate_observation(
    observation: Mapping[str, Any],
    prediction_cutoff_at: str | datetime,
    rights_approval: Mapping[str, Any] | None,
    *,
    rights_evaluated_at: str | datetime | None = None,
    required_use: str = "model_training",
    archive_proof_verified: bool = False,
) -> EligibilityDecision:
    """Evaluate evidence as-of a frozen prediction cutoff and current rights state."""
    cutoff = parse_aware_timestamp(prediction_cutoff_at)
    if cutoff is None:
        return EligibilityDecision(False, ("CUTOFF_TIMESTAMP_UNTRUSTED",))
    rights_time = parse_aware_timestamp(rights_evaluated_at)

    reasons: list[str] = []
    published = parse_aware_timestamp(observation.get("source_published_at"))
    if observation.get("source_published_at") is None:
        reasons.append("SOURCE_TIMESTAMP_MISSING")
    elif published is None:
        reasons.append("SOURCE_TIMESTAMP_UNTRUSTED")

    basis = observation.get("source_timestamp_basis")
    if basis not in TRUSTED_TIMESTAMP_BASES:
        reasons.append("SOURCE_TIMESTAMP_UNTRUSTED")
    elif basis == "documented_guarantee":
        evidence_id = observation.get("timestamp_guarantee_evidence_id")
        evidence_hash = observation.get("timestamp_guarantee_evidence_sha256")
        if not evidence_id or not isinstance(evidence_hash, str) or len(evidence_hash) != 64:
            reasons.append("SOURCE_TIMESTAMP_UNTRUSTED")
        else:
            try:
                int(evidence_hash, 16)
            except ValueError:
                reasons.append("SOURCE_TIMESTAMP_UNTRUSTED")

    if published is not None and published > cutoff:
        reasons.append("PUBLISHED_AFTER_CUTOFF")

    retrieved = parse_aware_timestamp(observation.get("retrieved_at"))
    if retrieved is None:
        reasons.append("RETRIEVAL_TIMESTAMP_UNTRUSTED")
    elif retrieved > cutoff and not (
        basis == "archival_snapshot_timestamp"
        and archive_proof_verified
        and bool(observation.get("archive_proof_id"))
    ):
        reasons.append("RETRIEVED_AFTER_CUTOFF_WITHOUT_ARCHIVE_PROOF")

    effective_raw = observation.get("source_effective_at")
    effective = parse_aware_timestamp(effective_raw) if effective_raw is not None else None
    if effective_raw is not None and effective is None:
        reasons.append("SOURCE_EFFECTIVE_TIMESTAMP_UNTRUSTED")

    semantics = observation.get("temporal_semantics")
    if semantics not in (STATE_AS_OF_CUTOFF, FORECAST_FOR_FIXTURE):
        reasons.append("FIELD_SEMANTICS_UNVERIFIED")
    elif effective is not None and effective > cutoff:
        if semantics == STATE_AS_OF_CUTOFF:
            reasons.append("FUTURE_EFFECTIVE_STATE")
        else:
            kickoff = parse_aware_timestamp(observation.get("fixture_kickoff_at"))
            if kickoff is None or effective > kickoff:
                reasons.append("FIELD_SEMANTICS_UNVERIFIED")

    if observation.get("revision_history_complete") is not True:
        reasons.append("REVISION_HISTORY_INCOMPLETE")

    if rights_time is None:
        reasons.append("RIGHTS_EVALUATION_TIMESTAMP_UNTRUSTED")
    rights_reason = _rights_reason(rights_approval, observation, rights_time, required_use)
    if rights_reason:
        reasons.append(rights_reason)

    ordered = tuple(dict.fromkeys(reasons))
    return EligibilityDecision(not ordered, ordered, published, cutoff)


def select_as_of(
    observations: Iterable[Mapping[str, Any]],
    prediction_cutoff_at: str | datetime,
    rights_approval: Mapping[str, Any] | None,
    *,
    rights_evaluated_at: str | datetime | None = None,
    required_use: str = "model_training",
    archive_proof_ids: frozenset[str] = frozenset(),
) -> Mapping[str, Any] | None:
    """Select latest eligible source version; ambiguous equal-time versions fail closed."""
    candidates: list[tuple[datetime, Mapping[str, Any]]] = []
    for row in observations:
        proof_id = row.get("archive_proof_id")
        decision = evaluate_observation(
            row,
            prediction_cutoff_at,
            rights_approval,
            rights_evaluated_at=rights_evaluated_at,
            required_use=required_use,
            archive_proof_verified=bool(proof_id and proof_id in archive_proof_ids),
        )
        if decision.eligible and decision.published_at is not None:
            candidates.append((decision.published_at, row))

    if not candidates:
        return None

    latest_published_at = max(item[0] for item in candidates)
    latest = [row for published_at, row in candidates if published_at == latest_published_at]
    if len(latest) == 1:
        return latest[0]

    # Publication-time ties require an explicit source revision order. Random
    # IDs, insertion order and database return order are not recency evidence.
    revision_orders = [row.get("source_revision_order") for row in latest]
    if any(
        isinstance(order, bool) or not isinstance(order, int) or order < 0
        for order in revision_orders
    ):
        return None
    if len(set(revision_orders)) != len(revision_orders):
        return None
    return max(latest, key=lambda row: row["source_revision_order"])


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
