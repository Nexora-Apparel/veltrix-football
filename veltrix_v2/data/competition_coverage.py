"""Competition-level, point-in-time data coverage auditing.

Pure offline audit: no provider calls, rights inference, or eligibility promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from veltrix_v2.data.provider_registry import DataDomain


@dataclass(frozen=True, slots=True)
class CoverageFixture:
    fixture_id: str
    competition_id: str
    kickoff_at: datetime


@dataclass(frozen=True, slots=True)
class DomainEvidence:
    fixture_id: str
    competition_id: str
    domain: DataDomain
    provider: str
    source_id: str
    available_at: datetime
    recorded_at: datetime
    payload_sha256: str
    rights_approved: bool
    point_in_time_certifiable: bool


@dataclass(frozen=True, slots=True)
class DomainCoverage:
    competition_id: str
    domain: DataDomain
    target_fixture_count: int
    eligible_fixture_count: int
    missing_fixture_ids: tuple[str, ...]
    rejected_evidence_count: int
    contributing_providers: tuple[str, ...]
    coverage_ratio: float


@dataclass(frozen=True, slots=True)
class CompetitionCoverageReport:
    domains: tuple[DomainCoverage, ...]

    def for_domain(self, competition_id: str, domain: DataDomain) -> DomainCoverage:
        matches = tuple(
            item for item in self.domains
            if item.competition_id == competition_id and item.domain is domain
        )
        if len(matches) != 1:
            raise KeyError(f"COVERAGE_DOMAIN_NOT_UNIQUE:{competition_id}:{domain.value}")
        return matches[0]


def _aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _valid_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def audit_competition_coverage(
    fixtures: Iterable[CoverageFixture],
    evidence: Iterable[DomainEvidence],
    *,
    domains: Iterable[DataDomain] = tuple(DataDomain),
    as_of: datetime,
) -> CompetitionCoverageReport:
    """Measure eligible evidence per target fixture, competition, and domain.

    Eligibility requires exact fixture identity, matching competition,
    timezone-aware availability/recording timestamps no later than as_of,
    evidence availability before kickoff, explicit rights and temporal
    certification, and a valid payload SHA-256. Coverage is not model or
    publication certification.
    """
    if not _aware(as_of):
        raise ValueError("COVERAGE_AS_OF_MUST_BE_TIMEZONE_AWARE")

    fixture_rows = tuple(fixtures)
    domain_rows = tuple(domains)
    if any(not isinstance(item, DataDomain) for item in domain_rows):
        raise ValueError("COVERAGE_DOMAIN_INVALID")

    fixture_by_id: dict[str, CoverageFixture] = {}
    for fixture in fixture_rows:
        if (
            not isinstance(fixture, CoverageFixture)
            or not isinstance(fixture.fixture_id, str) or not fixture.fixture_id.strip()
            or not isinstance(fixture.competition_id, str) or not fixture.competition_id.strip()
            or not _aware(fixture.kickoff_at)
        ):
            raise ValueError("COVERAGE_FIXTURE_INVALID")
        if fixture.fixture_id in fixture_by_id:
            raise ValueError("COVERAGE_FIXTURE_ID_DUPLICATE")
        fixture_by_id[fixture.fixture_id] = fixture

    valid_by_key: dict[tuple[str, DataDomain], set[str]] = {}
    providers_by_key: dict[tuple[str, DataDomain], set[str]] = {}
    rejected_by_key: dict[tuple[str, DataDomain], int] = {}

    for row in tuple(evidence):
        if not isinstance(row, DomainEvidence):
            continue
        key = (row.competition_id, row.domain)
        fixture = fixture_by_id.get(row.fixture_id)
        valid_identity = (
            fixture is not None and fixture.competition_id == row.competition_id
            and isinstance(row.provider, str) and bool(row.provider.strip())
            and isinstance(row.source_id, str) and bool(row.source_id.strip())
        )
        valid_clock = (
            _aware(row.available_at) and _aware(row.recorded_at)
            and row.recorded_at >= row.available_at
            and row.available_at <= as_of and row.recorded_at <= as_of
            and fixture is not None
            and (
                (row.domain is DataDomain.RESULTS and row.available_at >= fixture.kickoff_at)
                or (row.domain is not DataDomain.RESULTS and row.available_at < fixture.kickoff_at)
            )
        )
        eligible = (
            valid_identity and valid_clock
            and row.rights_approved is True
            and row.point_in_time_certifiable is True
            and _valid_sha256(row.payload_sha256)
        )
        if not eligible:
            if isinstance(row.competition_id, str) and isinstance(row.domain, DataDomain):
                rejected_by_key[key] = rejected_by_key.get(key, 0) + 1
            continue
        valid_by_key.setdefault(key, set()).add(row.fixture_id)
        providers_by_key.setdefault(key, set()).add(row.provider)

    competitions = sorted({item.competition_id for item in fixture_rows})
    reports: list[DomainCoverage] = []
    for competition_id in competitions:
        scoped = {
            item.fixture_id for item in fixture_rows
            if item.competition_id == competition_id
        }
        for domain in domain_rows:
            key = (competition_id, domain)
            covered = valid_by_key.get(key, set()) & scoped
            missing = tuple(sorted(scoped - covered))
            reports.append(DomainCoverage(
                competition_id=competition_id,
                domain=domain,
                target_fixture_count=len(scoped),
                eligible_fixture_count=len(covered),
                missing_fixture_ids=missing,
                rejected_evidence_count=rejected_by_key.get(key, 0),
                contributing_providers=tuple(sorted(providers_by_key.get(key, set()))),
                coverage_ratio=len(covered) / len(scoped) if scoped else 0.0,
            ))
    return CompetitionCoverageReport(domains=tuple(reports))
