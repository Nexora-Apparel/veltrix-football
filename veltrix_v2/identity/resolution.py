"""End-to-end identity resolution from provider IDs to canonical fixture decision."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from veltrix_v2.domain.identity import (
    CanonicalFixtureIdentity,
    ReconciliationDecision,
    ReconciliationStatus,
    reconcile_provider_fixture,
)
from veltrix_v2.identity.registry import (
    IdentityMappingRepository,
    MappingResolutionStatus,
    ProviderFixtureSourceIdentity,
    ResolvedProviderFixture,
    resolve_provider_fixture,
)


class FixtureIdentityPipelineStatus:
    MAPPING_UNRESOLVED = "MAPPING_UNRESOLVED"
    MAPPING_AMBIGUOUS = "MAPPING_AMBIGUOUS"
    MAPPING_UNVERIFIED = "MAPPING_UNVERIFIED"
    SQUAD_CATEGORY_MISMATCH = "SQUAD_CATEGORY_MISMATCH"
    INVALID_MAPPING = "INVALID_MAPPING"
    NEW_CANONICAL_FIXTURE = "NEW_CANONICAL_FIXTURE"
    MATCHED_EXISTING = "MATCHED_EXISTING"
    FIXTURE_AMBIGUOUS = "FIXTURE_AMBIGUOUS"
    FIXTURE_UNRESOLVED = "FIXTURE_UNRESOLVED"


@dataclass(frozen=True, slots=True)
class FixtureIdentityPipelineDecision:
    status: str
    source_identity: ProviderFixtureSourceIdentity
    mapping: ResolvedProviderFixture
    reconciliation: ReconciliationDecision | None
    reason_code: str
    evidence_refs: tuple[str, ...]


def resolve_and_reconcile_fixture(
    source: ProviderFixtureSourceIdentity,
    mapping_repository: IdentityMappingRepository,
    existing_fixtures: Sequence[CanonicalFixtureIdentity],
    *,
    evaluated_at_utc: datetime,
) -> FixtureIdentityPipelineDecision:
    """Resolve explicit provider aliases, then reconcile canonical fixture identity."""
    mapping = resolve_provider_fixture(
        source, mapping_repository, evaluated_at_utc=evaluated_at_utc
    )
    if mapping.status is not MappingResolutionStatus.VERIFIED or mapping.canonical_identity is None:
        status_map = {
            MappingResolutionStatus.UNRESOLVED: FixtureIdentityPipelineStatus.MAPPING_UNRESOLVED,
            MappingResolutionStatus.AMBIGUOUS: FixtureIdentityPipelineStatus.MAPPING_AMBIGUOUS,
            MappingResolutionStatus.UNVERIFIED: FixtureIdentityPipelineStatus.MAPPING_UNVERIFIED,
            MappingResolutionStatus.SQUAD_CATEGORY_MISMATCH: FixtureIdentityPipelineStatus.SQUAD_CATEGORY_MISMATCH,
            MappingResolutionStatus.INVALID_MAPPING: FixtureIdentityPipelineStatus.INVALID_MAPPING,
        }
        return FixtureIdentityPipelineDecision(
            status=status_map[mapping.status],
            source_identity=source,
            mapping=mapping,
            reconciliation=None,
            reason_code=mapping.reason_code,
            evidence_refs=mapping.evidence_refs,
        )

    decision = reconcile_provider_fixture(
        mapping.canonical_identity,
        existing_fixtures,
    )
    if decision.status is ReconciliationStatus.MATCHED_EXISTING:
        status = FixtureIdentityPipelineStatus.MATCHED_EXISTING
    elif decision.status is ReconciliationStatus.NEW_CANONICAL_FIXTURE:
        status = FixtureIdentityPipelineStatus.NEW_CANONICAL_FIXTURE
    elif decision.status is ReconciliationStatus.AMBIGUOUS:
        status = FixtureIdentityPipelineStatus.FIXTURE_AMBIGUOUS
    else:
        status = FixtureIdentityPipelineStatus.FIXTURE_UNRESOLVED

    return FixtureIdentityPipelineDecision(
        status=status,
        source_identity=source,
        mapping=mapping,
        reconciliation=decision,
        reason_code=decision.status.value,
        evidence_refs=mapping.evidence_refs,
    )
