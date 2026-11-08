"""Immutable PostgreSQL persistence for verified provider identity mappings."""
from __future__ import annotations

from typing import Callable, Sequence

from veltrix_v2.domain.identity import SquadCategory
from veltrix_v2.identity.registry import (
    IdentityMappingRepository, MappingVerificationState,
    ProviderCompetitionMapping, ProviderTeamMapping,
)


class PostgresIdentityMappingRepository(IdentityMappingRepository):
    def __init__(self, connection_factory: Callable[[], object]):
        self._connect = connection_factory

    def add_competition_mapping(self, mapping: ProviderCompetitionMapping) -> None:
        self._insert_immutable(
            """INSERT INTO v2_competition_mappings
            (provider,source_id,provider_competition_id,canonical_competition_id,squad_category,
             verification_state,mapping_version,evidence_ref,valid_from_utc,valid_to_utc,verified_at_utc)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING""",
            (mapping.provider,mapping.source_id,mapping.provider_competition_id,
             mapping.canonical_competition_id,mapping.squad_category.value,mapping.state.value,
             mapping.mapping_version,mapping.evidence_ref,mapping.valid_from_utc,
             mapping.valid_to_utc,mapping.verified_at_utc),
        )

    def add_team_mapping(self, mapping: ProviderTeamMapping) -> None:
        self._insert_immutable(
            """INSERT INTO v2_team_mappings
            (provider,source_id,provider_team_id,canonical_team_id,squad_category,
             verification_state,mapping_version,evidence_ref,valid_from_utc,valid_to_utc,verified_at_utc)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING""",
            (mapping.provider,mapping.source_id,mapping.provider_team_id,
             mapping.canonical_team_id,mapping.squad_category.value,mapping.state.value,
             mapping.mapping_version,mapping.evidence_ref,mapping.valid_from_utc,
             mapping.valid_to_utc,mapping.verified_at_utc),
        )

    def _insert_immutable(self, sql: str, params: tuple) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_competition_mappings(self, *, provider: str, source_id: str,
                                 provider_competition_id: str) -> Sequence[ProviderCompetitionMapping]:
        return self._read(
            """SELECT provider,source_id,provider_competition_id,canonical_competition_id,
            squad_category,verification_state,mapping_version,evidence_ref,valid_from_utc,
            valid_to_utc,verified_at_utc FROM v2_competition_mappings
            WHERE provider=%s AND source_id=%s AND provider_competition_id=%s""",
            (provider,source_id,provider_competition_id), ProviderCompetitionMapping,
        )

    def get_team_mappings(self, *, provider: str, source_id: str,
                          provider_team_id: str) -> Sequence[ProviderTeamMapping]:
        return self._read(
            """SELECT provider,source_id,provider_team_id,canonical_team_id,squad_category,
            verification_state,mapping_version,evidence_ref,valid_from_utc,valid_to_utc,
            verified_at_utc FROM v2_team_mappings
            WHERE provider=%s AND source_id=%s AND provider_team_id=%s""",
            (provider,source_id,provider_team_id), ProviderTeamMapping,
        )

    def _read(self, sql: str, params: tuple, factory):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            return tuple(factory(
                provider=row[0], source_id=row[1],
                **({"provider_competition_id": row[2], "canonical_competition_id": row[3]}
                   if factory is ProviderCompetitionMapping else
                   {"provider_team_id": row[2], "canonical_team_id": row[3]}),
                squad_category=SquadCategory(row[4]),
                state=MappingVerificationState(row[5]), mapping_version=row[6],
                evidence_ref=row[7], valid_from_utc=row[8], valid_to_utc=row[9],
                verified_at_utc=row[10],
            ) for row in rows)
        finally:
            conn.close()
