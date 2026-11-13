"""Offline-only, fail-closed Odds API capture preflight.

No HTTP, environment, secret-store, database, scheduling or prediction access.
This module emits deterministic manifests and preflight decisions only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Mapping

from .budget import CreditBudget, PlannedRequest, plan_request


@dataclass(frozen=True)
class FixtureBoundary:
    fixture_id: str
    provider_event_id: str
    prediction_cutoff_at: datetime
    kickoff_at: datetime


@dataclass(frozen=True)
class RightsEvidence:
    provider: str
    status: str
    accepted_terms_version: str
    terms_evidence_id: str
    approval_evidence_id: str
    effective_at: datetime
    recorded_at: datetime
    valid_until: datetime | None
    competitions: tuple[str, ...]
    markets: tuple[str, ...]
    regions: tuple[str, ...]
    permitted_uses: tuple[str, ...]


@dataclass(frozen=True)
class CaptureRequest:
    request_id: str
    run_id: str
    provider: str
    api_version: str
    endpoint_class: str
    sport_key: str
    competition_keys: tuple[str, ...]
    fixture_boundaries: tuple[FixtureBoundary, ...]
    markets: tuple[str, ...]
    regions: tuple[str, ...]
    prediction_use: str
    expected_terms_version: str
    rights_evaluated_at: datetime
    created_at: datetime
    max_attempts: int
    timeout_seconds: int


@dataclass(frozen=True)
class RequestManifest:
    request_id: str
    run_id: str
    provider: str
    api_version: str
    endpoint_class: str
    sport_key: str
    competition_keys: tuple[str, ...]
    fixture_ids: tuple[str, ...]
    provider_event_ids: tuple[str, ...]
    markets: tuple[str, ...]
    regions: tuple[str, ...]
    prediction_cutoffs: tuple[tuple[str, str], ...]
    rights_evaluated_at: str
    prediction_use: str
    expected_terms_version: str
    created_at: str
    max_attempts: int
    timeout_seconds: int
    request_fingerprint: str
    manifest_sha256: str


@dataclass(frozen=True)
class PreflightDecision:
    allowed: bool
    state: str
    reason_codes: tuple[str, ...]
    estimated_credits: int | None
    manifest_sha256: str


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value, "TIMESTAMP").isoformat().replace("+00:00", "Z")


def _canonical_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_manifest(request: CaptureRequest) -> RequestManifest:
    """Build a deterministic credential-free manifest; does not reserve or dispatch."""
    if not isinstance(request, CaptureRequest):
        raise TypeError("CAPTURE_REQUEST_TYPE_INVALID")
    for name in ("request_id", "run_id", "provider", "api_version", "endpoint_class", "sport_key", "prediction_use", "expected_terms_version"):
        value = getattr(request, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name.upper()}_REQUIRED")
    created = _utc(request.created_at, "CREATED_AT")
    rights_at = _utc(request.rights_evaluated_at, "RIGHTS_EVALUATED_AT")
    if not isinstance(request.max_attempts, int) or isinstance(request.max_attempts, bool) or not 1 <= request.max_attempts <= 3:
        raise ValueError("MAX_ATTEMPTS_OUT_OF_RANGE")
    if not isinstance(request.timeout_seconds, int) or isinstance(request.timeout_seconds, bool) or not 1 <= request.timeout_seconds <= 30:
        raise ValueError("TIMEOUT_OUT_OF_RANGE")
    if not request.fixture_boundaries:
        if request.endpoint_class not in {"sports_discovery", "events_discovery"}:
            raise ValueError("FIXTURE_BOUNDARIES_REQUIRED")
    if len(set(request.markets)) != len(request.markets) or any(not isinstance(x, str) or not x for x in request.markets):
        raise ValueError("MARKET_SCOPE_INVALID")
    if len(set(request.regions)) != len(request.regions) or any(not isinstance(x, str) or not x for x in request.regions):
        raise ValueError("REGION_SCOPE_INVALID")
    fixture_ids: list[str] = []
    event_ids: list[str] = []
    cutoffs: list[tuple[str, str]] = []
    for item in request.fixture_boundaries:
        if not isinstance(item, FixtureBoundary) or not item.fixture_id or not item.provider_event_id:
            raise ValueError("FIXTURE_IDENTITY_INVALID")
        cutoff, kickoff = _utc(item.prediction_cutoff_at, "PREDICTION_CUTOFF_AT"), _utc(item.kickoff_at, "KICKOFF_AT")
        if cutoff >= kickoff:
            raise ValueError("PREDICTION_CUTOFF_NOT_BEFORE_KICKOFF")
        fixture_ids.append(item.fixture_id)
        event_ids.append(item.provider_event_id)
        cutoffs.append((item.fixture_id, _iso(cutoff)))
    if len(set(fixture_ids)) != len(fixture_ids) or len(set(event_ids)) != len(event_ids):
        raise ValueError("FIXTURE_OR_EVENT_ID_DUPLICATE")
    if not request.competition_keys or any(not isinstance(x, str) or not x for x in request.competition_keys):
        raise ValueError("COMPETITION_SCOPE_INVALID")
    if len(set(request.competition_keys)) != len(request.competition_keys):
        raise ValueError("COMPETITION_SCOPE_DUPLICATE")
    identity = {
        "provider": request.provider, "api_version": request.api_version,
        "endpoint_class": request.endpoint_class, "sport_key": request.sport_key,
        "event_ids": event_ids, "markets": sorted(request.markets),
        "regions": sorted(request.regions),
    }
    fingerprint = _canonical_hash(identity)
    payload = {
        "request_id": request.request_id, "run_id": request.run_id,
        **identity, "competition_keys": sorted(request.competition_keys),
        "fixture_ids": fixture_ids, "prediction_cutoffs": cutoffs,
        "rights_evaluated_at": _iso(rights_at), "prediction_use": request.prediction_use,
        "expected_terms_version": request.expected_terms_version, "created_at": _iso(created),
        "max_attempts": request.max_attempts, "timeout_seconds": request.timeout_seconds,
        "request_fingerprint": fingerprint,
    }
    digest = _canonical_hash(payload)
    return RequestManifest(
        request.request_id, request.run_id, request.provider, request.api_version,
        request.endpoint_class, request.sport_key, tuple(sorted(request.competition_keys)),
        tuple(fixture_ids), tuple(event_ids), tuple(sorted(request.markets)),
        tuple(sorted(request.regions)), tuple(cutoffs), _iso(rights_at), request.prediction_use, request.expected_terms_version, _iso(created),
        request.max_attempts, request.timeout_seconds, fingerprint, digest,
    )


def evaluate_preflight(
    manifest: RequestManifest,
    rights: RightsEvidence | None,
    budget: CreditBudget,
    crosswalk: Mapping[str, str],
) -> PreflightDecision:
    """Evaluate offline rights, mapping and credit gates. Never performs reservation or I/O."""
    reasons: list[str] = []
    if not isinstance(manifest, RequestManifest):
        return PreflightDecision(False, "BLOCKED", ("MANIFEST_TYPE_INVALID",), None, "")
    if rights is None or not isinstance(rights, RightsEvidence):
        reasons.append("RIGHTS_EVIDENCE_MISSING")
    else:
        evaluated = datetime.fromisoformat(manifest.rights_evaluated_at.replace("Z", "+00:00"))
        try:
            effective = _utc(rights.effective_at, "RIGHTS_EFFECTIVE_AT")
            recorded = _utc(rights.recorded_at, "RIGHTS_RECORDED_AT")
            expiry = _utc(rights.valid_until, "RIGHTS_VALID_UNTIL") if rights.valid_until else None
        except ValueError:
            reasons.append("RIGHTS_TIMESTAMP_INVALID")
        else:
            if rights.provider != manifest.provider:
                reasons.append("RIGHTS_PROVIDER_MISMATCH")
            if rights.status != "APPROVED":
                reasons.append("RIGHTS_NOT_APPROVED")
            if not rights.accepted_terms_version or not rights.terms_evidence_id:
                reasons.append("ACCOUNT_TERMS_EVIDENCE_MISSING")
            elif rights.accepted_terms_version != manifest.expected_terms_version:
                reasons.append("ACCOUNT_TERMS_VERSION_MISMATCH")
            if not rights.approval_evidence_id:
                reasons.append("APPROVAL_EVIDENCE_ID_MISSING")
            if effective > evaluated or recorded > evaluated or (expiry is not None and expiry <= evaluated):
                reasons.append("RIGHTS_NOT_VALID_AT_EVALUATION")
            if not set(manifest.competition_keys).issubset(set(rights.competitions)):
                reasons.append("COMPETITION_SCOPE_NOT_APPROVED")
            if not set(manifest.markets).issubset(set(rights.markets)):
                reasons.append("MARKET_SCOPE_NOT_APPROVED")
            if not set(manifest.regions).issubset(set(rights.regions)):
                reasons.append("REGION_SCOPE_NOT_APPROVED")
            if manifest.endpoint_class in {"bulk_odds", "event_odds"} and manifest.prediction_use not in rights.permitted_uses:
                reasons.append("PREDICTION_USE_NOT_APPROVED")
    if not isinstance(crosswalk, Mapping):
        reasons.append("CROSSWALK_INVALID")
    else:
        for fixture_id, event_id in zip(manifest.fixture_ids, manifest.provider_event_ids):
            if crosswalk.get(fixture_id) != event_id:
                reasons.append("EVENT_CROSSWALK_MISMATCH")
                break
    planned = PlannedRequest(
        endpoint_class=manifest.endpoint_class,
        regions=max(1, len(manifest.regions)),
        markets=manifest.markets,
        sport_key=manifest.sport_key,
    )
    budget_result = plan_request(planned, budget)
    if not budget_result.allowed:
        reasons.append(budget_result.reason_code)
    unique_reasons = tuple(dict.fromkeys(reasons))
    return PreflightDecision(
        not unique_reasons,
        "PREFLIGHT_APPROVED" if not unique_reasons else "BLOCKED",
        unique_reasons,
        budget_result.estimated_credits,
        manifest.manifest_sha256,
    )
