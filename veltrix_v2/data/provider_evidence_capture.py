"""Provider-neutral, immutable evidence capture for prospective Phase 5 data.

This adapter accepts already-retrieved raw provider bytes. It performs no network
I/O, does not infer source timestamps, and never persists to production. A row
is certifiable only when raw-byte integrity, temporal ordering, exact identity
crosswalk, complete revision history, and use-time rights all pass.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Iterable, Mapping

from veltrix_v2.data.contracts import DataUsePurpose, SourceApproval
from veltrix_v2.data.rights import evaluate_source_use
from veltrix_v2.models.poisson import MatchObservation


_HASH = re.compile(r"^[0-9a-f]{64}$")


def _aware(value: datetime | None) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf-8")
    return sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class ResolvedFixtureCrosswalk:
    """Exact, reviewed provider-to-canonical fixture/team/competition mapping."""

    provider: str
    source_id: str
    provider_fixture_id: str
    provider_competition_id: str
    provider_home_team_id: str
    provider_away_team_id: str
    canonical_fixture_id: str
    canonical_competition_id: str
    canonical_home_team_id: str
    canonical_away_team_id: str
    mapping_version: int
    mapping_status: str
    valid_from: datetime
    valid_until: datetime | None = None
    evidence_sha256: str = ""

    def validate(self, *, at: datetime, provider: str, source_id: str,
                 provider_fixture_id: str, provider_competition_id: str,
                 provider_home_team_id: str, provider_away_team_id: str) -> None:
        values = (
            self.provider, self.source_id, self.provider_fixture_id,
            self.provider_competition_id, self.provider_home_team_id,
            self.provider_away_team_id, self.canonical_fixture_id,
            self.canonical_competition_id, self.canonical_home_team_id,
            self.canonical_away_team_id,
        )
        if any(not isinstance(x, str) or not x.strip() for x in values):
            raise ValueError("CROSSWALK_IDENTITY_INCOMPLETE")
        if self.mapping_status != "RESOLVED":
            raise ValueError("CROSSWALK_NOT_RESOLVED")
        if type(self.mapping_version) is not int or self.mapping_version < 1:
            raise ValueError("CROSSWALK_VERSION_INVALID")
        if not _aware(self.valid_from) or (self.valid_until is not None and not _aware(self.valid_until)):
            raise ValueError("CROSSWALK_VALIDITY_TIMESTAMP_UNTRUSTED")
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("CROSSWALK_VALIDITY_INTERVAL_INVALID")
        if self.valid_from > at or (self.valid_until is not None and at >= self.valid_until):
            raise ValueError("CROSSWALK_NOT_VALID_AT_CAPTURE")
        if (self.provider, self.source_id, self.provider_fixture_id,
            self.provider_competition_id, self.provider_home_team_id,
            self.provider_away_team_id) != (
            provider, source_id, provider_fixture_id, provider_competition_id,
            provider_home_team_id, provider_away_team_id
        ):
            raise ValueError("CROSSWALK_PROVIDER_IDENTITY_MISMATCH")
        if self.canonical_home_team_id == self.canonical_away_team_id:
            raise ValueError("CROSSWALK_CANONICAL_TEAM_COLLISION")
        if not _HASH.fullmatch(self.evidence_sha256):
            raise ValueError("CROSSWALK_EVIDENCE_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class ProviderResultCapture:
    """One finished fixture result with independently supplied source timestamps."""

    provider: str
    source_id: str
    endpoint: str
    request_id: str
    provider_fixture_id: str
    provider_competition_id: str
    provider_home_team_id: str
    provider_away_team_id: str
    kickoff_at: datetime
    home_goals: int
    away_goals: int
    raw_response: bytes
    source_published_at: datetime | None
    source_effective_at: datetime | None
    available_at: datetime | None
    retrieved_at: datetime
    recorded_at: datetime
    requested_at: datetime
    revision_history_complete: bool
    crosswalk: ResolvedFixtureCrosswalk
    rights_approval: SourceApproval


@dataclass(frozen=True, slots=True)
class CapturedResultEvidence:
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    provider: str
    source_id: str
    provider_fixture_id: str
    source_published_at: str | None
    source_effective_at: str | None
    kickoff_at: str
    available_at: str | None
    retrieved_at: str
    recorded_at: str
    requested_at: str
    raw_response_sha256: str
    rights_approval_id: str
    rights_evidence_sha256: str
    crosswalk_version: int
    crosswalk_evidence_sha256: str
    point_in_time_certifiable: bool
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result

    def to_match_observation(self, *, home_goals: int, away_goals: int) -> MatchObservation:
        if not self.point_in_time_certifiable:
            raise ValueError("UNCERTIFIED_EVIDENCE_CANNOT_ENTER_MODEL")
        return MatchObservation(
            fixture_id=self.fixture_id,
            competition_id=self.competition_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            kickoff_at=datetime.fromisoformat(self.kickoff_at),
            available_at=datetime.fromisoformat(self.available_at or ""),
            recorded_at=datetime.fromisoformat(self.recorded_at),
            home_goals=home_goals,
            away_goals=away_goals,
            provider=self.provider,
            source_id=self.source_id,
            availability_basis="provider_timestamp",
            point_in_time_certifiable=True,
            payload_sha256=self.raw_response_sha256,
            rights_approval_id=self.rights_approval_id,
        )


@dataclass(frozen=True, slots=True)
class ProviderEvidenceManifest:
    manifest_version: str
    provider: str
    source_id: str
    endpoint: str
    request_id: str
    requested_at: str
    retrieved_at: str
    recorded_at: str
    item_count: int
    certified_count: int
    rejected_count: int
    item_evidence_sha256: tuple[str, ...]
    manifest_sha256: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProviderEvidenceCaptureReport:
    manifest: ProviderEvidenceManifest
    observations: tuple[CapturedResultEvidence, ...]


def _capture_one(row: ProviderResultCapture) -> CapturedResultEvidence:
    reasons: list[str] = []
    required_text = (
        row.provider, row.source_id, row.endpoint, row.request_id,
        row.provider_fixture_id, row.provider_competition_id,
        row.provider_home_team_id, row.provider_away_team_id,
    )
    if any(not isinstance(value, str) or not value.strip() for value in required_text):
        reasons.append("SOURCE_IDENTITY_INCOMPLETE")
    if not isinstance(row.raw_response, bytes) or not row.raw_response:
        reasons.append("RAW_RESPONSE_BYTES_MISSING")
        raw_hash = ""
    else:
        raw_hash = sha256(row.raw_response).hexdigest()

    timestamps = {
        "requested_at": row.requested_at,
        "retrieved_at": row.retrieved_at,
        "recorded_at": row.recorded_at,
        "kickoff_at": row.kickoff_at,
    }
    if row.source_published_at is None:
        reasons.append("SOURCE_PUBLICATION_TIMESTAMP_MISSING")
    elif not _aware(row.source_published_at):
        reasons.append("SOURCE_PUBLICATION_TIMESTAMP_UNTRUSTED")
    if row.available_at is None:
        reasons.append("RESULT_AVAILABILITY_TIMESTAMP_MISSING")
    elif not _aware(row.available_at):
        reasons.append("RESULT_AVAILABILITY_TIMESTAMP_UNTRUSTED")
    if row.source_effective_at is not None and not _aware(row.source_effective_at):
        reasons.append("SOURCE_EFFECTIVE_TIMESTAMP_UNTRUSTED")
    for name, value in timestamps.items():
        if not _aware(value):
            reasons.append(f"{name.upper()}_TIMESTAMP_UNTRUSTED")

    if all(_aware(value) for value in (
        row.requested_at, row.retrieved_at, row.recorded_at,
        row.kickoff_at, row.source_published_at, row.available_at,
    )):
        if not (row.requested_at <= row.retrieved_at <= row.recorded_at):
            reasons.append("CAPTURE_TIMESTAMP_ORDER_INVALID")
        if row.source_published_at > row.retrieved_at:
            reasons.append("SOURCE_PUBLISHED_AFTER_RETRIEVAL")
        if row.available_at < row.kickoff_at:
            reasons.append("RESULT_AVAILABLE_BEFORE_KICKOFF")
        if row.available_at > row.retrieved_at:
            reasons.append("RESULT_AVAILABLE_AFTER_RETRIEVAL")
        if row.source_effective_at is not None and row.source_effective_at > row.retrieved_at:
            reasons.append("SOURCE_EFFECTIVE_AFTER_RETRIEVAL")

    if type(row.home_goals) is not int or type(row.away_goals) is not int or min(
        row.home_goals if type(row.home_goals) is int else -1,
        row.away_goals if type(row.away_goals) is int else -1,
    ) < 0:
        reasons.append("RESULT_SCORE_INVALID")
    if row.revision_history_complete is not True:
        reasons.append("REVISION_HISTORY_INCOMPLETE")

    approval = row.rights_approval
    if not isinstance(approval, SourceApproval):
        reasons.append("SOURCE_APPROVAL_MISSING")
    else:
        if approval.provider != row.provider or approval.source_id != row.source_id:
            reasons.append("SOURCE_APPROVAL_IDENTITY_MISMATCH")
        if approval.evidence_sha256 is None or not _HASH.fullmatch(approval.evidence_sha256):
            reasons.append("SOURCE_APPROVAL_EVIDENCE_HASH_INVALID")
        if row.crosswalk.canonical_competition_id not in {
            item.strip() for item in approval.competition_scope.split(",")
        }:
            reasons.append("SOURCE_APPROVAL_COMPETITION_SCOPE_MISMATCH")
        if _aware(row.recorded_at):
            for purpose in (
                DataUsePurpose.COLLECTION, DataUsePurpose.STORAGE,
                DataUsePurpose.MODEL_TRAINING,
            ):
                try:
                    decision = evaluate_source_use(
                        approval, purpose, at_utc=row.recorded_at, commercial=True
                    )
                except (TypeError, ValueError):
                    reasons.append("SOURCE_RIGHTS_EVALUATION_FAILED")
                    break
                if not decision.allowed:
                    reasons.append(f"SOURCE_RIGHTS_{purpose.value}_{decision.reason_code}")

    try:
        row.crosswalk.validate(
            at=row.recorded_at, provider=row.provider, source_id=row.source_id,
            provider_fixture_id=row.provider_fixture_id,
            provider_competition_id=row.provider_competition_id,
            provider_home_team_id=row.provider_home_team_id,
            provider_away_team_id=row.provider_away_team_id,
        )
    except (TypeError, ValueError, AttributeError) as exc:
        reasons.append(str(exc) or "CROSSWALK_INVALID")

    if not _HASH.fullmatch(raw_hash):
        reasons.append("RAW_RESPONSE_HASH_INVALID")

    reasons = list(dict.fromkeys(reasons))
    crosswalk = row.crosswalk
    return CapturedResultEvidence(
        fixture_id=crosswalk.canonical_fixture_id,
        competition_id=crosswalk.canonical_competition_id,
        home_team_id=crosswalk.canonical_home_team_id,
        away_team_id=crosswalk.canonical_away_team_id,
        provider=row.provider,
        source_id=row.source_id,
        provider_fixture_id=row.provider_fixture_id,
        source_published_at=_utc(row.source_published_at) if _aware(row.source_published_at) else None,
        source_effective_at=_utc(row.source_effective_at) if _aware(row.source_effective_at) else None,
        kickoff_at=_utc(row.kickoff_at) if _aware(row.kickoff_at) else "",
        available_at=_utc(row.available_at) if _aware(row.available_at) else None,
        retrieved_at=_utc(row.retrieved_at) if _aware(row.retrieved_at) else "",
        recorded_at=_utc(row.recorded_at) if _aware(row.recorded_at) else "",
        requested_at=_utc(row.requested_at) if _aware(row.requested_at) else "",
        raw_response_sha256=raw_hash,
        rights_approval_id=approval.approval_id if isinstance(approval, SourceApproval) else "",
        rights_evidence_sha256=approval.evidence_sha256 or "" if isinstance(approval, SourceApproval) else "",
        crosswalk_version=crosswalk.mapping_version,
        crosswalk_evidence_sha256=crosswalk.evidence_sha256,
        point_in_time_certifiable=not reasons,
        reason_codes=tuple(reasons),
    )


def capture_provider_result_evidence(
    captures: Iterable[ProviderResultCapture],
) -> ProviderEvidenceCaptureReport:
    """Build a deterministic manifest from supplied raw snapshots; never performs I/O."""
    rows = tuple(captures)
    if not rows:
        raise ValueError("EMPTY_PROVIDER_EVIDENCE_CAPTURE")
    identity = {(r.provider, r.source_id, r.endpoint, r.request_id) for r in rows}
    if len(identity) != 1:
        raise ValueError("CAPTURE_BATCH_REQUEST_IDENTITY_MISMATCH")
    fixture_ids = [r.crosswalk.canonical_fixture_id for r in rows]
    provider_ids = [(r.provider, r.source_id, r.provider_fixture_id) for r in rows]
    duplicates = {x for x in fixture_ids if fixture_ids.count(x) > 1}
    duplicate_provider_ids = {x for x in provider_ids if provider_ids.count(x) > 1}
    evidence = []
    for row in rows:
        item = _capture_one(row)
        if item.fixture_id in duplicates or (row.provider, row.source_id, row.provider_fixture_id) in duplicate_provider_ids:
            item = replace(item, reason_codes=tuple(dict.fromkeys((*item.reason_codes, "DUPLICATE_FIXTURE_IDENTITY"))), point_in_time_certifiable=False)
        evidence.append(item)

    first = rows[0]
    if not all(_aware(x) for x in (first.requested_at, first.retrieved_at, first.recorded_at)):
        raise ValueError("MANIFEST_CAPTURE_TIMESTAMPS_UNTRUSTED")
    item_hashes = tuple(_digest(item.as_dict()) for item in evidence)
    manifest_body = {
        "manifest_version": "veltrix-provider-evidence-v1",
        "provider": first.provider, "source_id": first.source_id,
        "endpoint": first.endpoint, "request_id": first.request_id,
        "requested_at": _utc(first.requested_at),
        "retrieved_at": _utc(first.retrieved_at),
        "recorded_at": _utc(first.recorded_at),
        "item_count": len(evidence),
        "certified_count": sum(item.point_in_time_certifiable for item in evidence),
        "rejected_count": sum(not item.point_in_time_certifiable for item in evidence),
        "item_evidence_sha256": item_hashes,
    }
    manifest = ProviderEvidenceManifest(
        **manifest_body, manifest_sha256=_digest(manifest_body)
    )
    return ProviderEvidenceCaptureReport(manifest, tuple(evidence))


def certified_match_observations(
    report: ProviderEvidenceCaptureReport,
    captures: Iterable[ProviderResultCapture],
) -> tuple[MatchObservation, ...]:
    """Pair evidence with original score values; reject any uncertified row."""
    rows = tuple(captures)
    if len(rows) != len(report.observations):
        raise ValueError("CAPTURE_EVIDENCE_ROW_COUNT_MISMATCH")
    observations = []
    for evidence, source in zip(report.observations, rows):
        if not evidence.point_in_time_certifiable:
            continue
        observations.append(evidence.to_match_observation(
            home_goals=source.home_goals, away_goals=source.away_goals
        ))
    return tuple(observations)
