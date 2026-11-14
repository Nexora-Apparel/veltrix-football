"""Deterministic merge of certified observations from multiple providers.

No provider I/O, fuzzy identity matching, result averaging, or eligibility
promotion occurs here. Conflicting records for one canonical fixture are
quarantined as a group; identical corroborating records count only once.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterable, Mapping

from veltrix_v2.models.poisson import MatchObservation


@dataclass(frozen=True, slots=True)
class MergedObservationReport:
    observations: tuple[MatchObservation, ...]
    duplicate_observation_count: int
    rejected_uncertified_count: int
    conflicting_fixture_ids: tuple[str, ...]
    source_evidence_by_fixture: tuple[tuple[str, tuple[str, ...]], ...]


def _valid_hash(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def _kickoff_key(row: MatchObservation) -> tuple[str, str]:
    if row.kickoff_at is not None:
        if row.kickoff_at.tzinfo is None or row.kickoff_at.utcoffset() is None:
            return ("invalid", "")
        return ("instant", row.kickoff_at.astimezone(timezone.utc).isoformat())
    if row.kickoff_date is not None:
        return ("date", row.kickoff_date.isoformat())
    return ("missing", "")


def _result_identity(row: MatchObservation) -> tuple[object, ...]:
    return (
        row.fixture_id, row.competition_id, row.home_team_id, row.away_team_id,
        _kickoff_key(row), row.home_goals, row.away_goals,
    )


def merge_certified_observations(
    observations: Iterable[MatchObservation],
    *,
    source_priority: Mapping[str, int] | None = None,
) -> MergedObservationReport:
    """Deduplicate identical certified results and quarantine conflicting groups.

    Lower explicit priority values win. Unlisted providers share a stable
    fallback priority; then earliest valid availability/recording timestamps
    and lexical source identity break ties.
    """
    priorities = dict(source_priority or {})
    if any(not isinstance(key, str) or not key.strip() or type(value) is not int
           for key, value in priorities.items()):
        raise ValueError("SOURCE_PRIORITY_MAP_INVALID")

    groups: dict[str, list[MatchObservation]] = {}
    rejected = 0
    for row in observations:
        if not isinstance(row, MatchObservation):
            rejected += 1
            continue
        if (
            not row.point_in_time_certifiable
            or not row.fixture_id.strip()
            or not row.provider.strip()
            or not row.source_id.strip()
            or not row.rights_approval_id
            or not _valid_hash(row.payload_sha256)
            or (row.availability_basis == "provider_evidence_manifest_v1" and (
                not _valid_hash(row.evidence_manifest_sha256)
                or not _valid_hash(row.capture_evidence_sha256)
            ))
            or row.available_at.tzinfo is None or row.available_at.utcoffset() is None
            or row.recorded_at.tzinfo is None or row.recorded_at.utcoffset() is None
        ):
            rejected += 1
            continue
        groups.setdefault(row.fixture_id, []).append(row)

    selected: list[MatchObservation] = []
    duplicates = 0
    conflicts: list[str] = []
    source_evidence: list[tuple[str, tuple[str, ...]]] = []

    for fixture_id in sorted(groups):
        rows = groups[fixture_id]
        identities = {_result_identity(row) for row in rows}
        if len(identities) != 1:
            conflicts.append(fixture_id)
            continue

        def rank(row: MatchObservation) -> tuple[object, ...]:
            return (
                priorities.get(row.provider, 10_000),
                row.available_at.astimezone(timezone.utc),
                row.recorded_at.astimezone(timezone.utc),
                row.provider,
                row.source_id,
                row.payload_sha256 or "",
            )

        ordered = sorted(rows, key=rank)
        selected.append(ordered[0])
        duplicates += len(rows) - 1
        source_evidence.append((fixture_id, tuple(sorted({
            f"{row.provider}:{row.source_id}:{row.payload_sha256}" for row in rows
        }))))

    return MergedObservationReport(
        observations=tuple(selected),
        duplicate_observation_count=duplicates,
        rejected_uncertified_count=rejected,
        conflicting_fixture_ids=tuple(conflicts),
        source_evidence_by_fixture=tuple(source_evidence),
    )
