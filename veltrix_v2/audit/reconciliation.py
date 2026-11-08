"""Read-only PostgreSQL reconciliation diagnostics for V2 historical data."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class ReconciliationFinding:
    category: str
    count: int
    sample_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationAudit:
    findings: tuple[ReconciliationFinding, ...]

    @property
    def is_clean(self) -> bool:
        return all(item.count == 0 for item in self.findings)

    @property
    def total_issues(self) -> int:
        return sum(item.count for item in self.findings)


# Deliberately read-only. The checks use source IDs and immutable provider
# identities; they never update, repair, merge or delete records.
_AUDIT_SQL = """
WITH categories(category) AS (
    VALUES
      ('orphaned_source_records'),
      ('unresolved_competition_mappings'),
      ('unresolved_home_team_mappings'),
      ('unresolved_away_team_mappings'),
      ('provenance_gaps'),
      ('duplicate_canonical_fixtures')
),
findings(category, record_id) AS (
    SELECT 'orphaned_source_records', s.source_record_id
    FROM v2_source_records s
    WHERE s.data_class = 'fixtures'
      AND s.provider_fixture_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM v2_fixture_sources f
        WHERE f.source_record_id = s.source_record_id
      )

    UNION ALL

    SELECT 'unresolved_competition_mappings', s.source_record_id
    FROM v2_source_records s
    WHERE s.provider_competition_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM v2_competition_mappings m
        WHERE m.provider=s.provider AND m.source_id=s.source_id
          AND m.provider_competition_id=s.provider_competition_id
          AND m.verification_state='VERIFIED'
          AND m.valid_from_utc <= s.fetched_at_utc
          AND (m.valid_to_utc IS NULL OR m.valid_to_utc > s.fetched_at_utc)
      )

    UNION ALL

    SELECT 'unresolved_home_team_mappings', s.source_record_id
    FROM v2_source_records s
    WHERE s.provider_home_team_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM v2_team_mappings m
        WHERE m.provider=s.provider AND m.source_id=s.source_id
          AND m.provider_team_id=s.provider_home_team_id
          AND m.verification_state='VERIFIED'
          AND m.valid_from_utc <= s.fetched_at_utc
          AND (m.valid_to_utc IS NULL OR m.valid_to_utc > s.fetched_at_utc)
      )

    UNION ALL

    SELECT 'unresolved_away_team_mappings', s.source_record_id
    FROM v2_source_records s
    WHERE s.provider_away_team_id IS NOT NULL
      AND NOT EXISTS (
        SELECT 1 FROM v2_team_mappings m
        WHERE m.provider=s.provider AND m.source_id=s.source_id
          AND m.provider_team_id=s.provider_away_team_id
          AND m.verification_state='VERIFIED'
          AND m.valid_from_utc <= s.fetched_at_utc
          AND (m.valid_to_utc IS NULL OR m.valid_to_utc > s.fetched_at_utc)
      )

    UNION ALL

    SELECT 'provenance_gaps', h.historical_match_id
    FROM v2_historical_matches h
    WHERE NOT EXISTS (
      SELECT 1 FROM v2_historical_match_sources hs
      WHERE hs.historical_match_id=h.historical_match_id
    )

    UNION ALL

    SELECT 'provenance_gaps', f.source_record_id
    FROM v2_fixture_sources f
    JOIN v2_source_records s ON s.source_record_id=f.source_record_id
    WHERE (f.provider, f.source_id, f.provider_fixture_id)
       IS DISTINCT FROM
          (s.provider, s.source_id, s.provider_fixture_id)

    UNION ALL

    SELECT 'duplicate_canonical_fixtures',
           string_agg(f.canonical_fixture_id, ',' ORDER BY f.canonical_fixture_id)
    FROM v2_canonical_fixtures f
    GROUP BY f.canonical_competition_id, f.squad_category,
             f.canonical_home_team_id, f.canonical_away_team_id, f.kickoff_at_utc
    HAVING COUNT(*) > 1
),
ranked AS (
    SELECT category, record_id,
           row_number() OVER (PARTITION BY category ORDER BY record_id) AS ordinal
    FROM findings
),
aggregated AS (
    SELECT category, COUNT(*)::INTEGER AS issue_count,
           COALESCE(
             array_agg(record_id ORDER BY record_id)
               FILTER (WHERE ordinal <= %s),
             ARRAY[]::TEXT[]
           ) AS sample_ids
    FROM ranked
    GROUP BY category
)
SELECT c.category, COALESCE(a.issue_count, 0),
       COALESCE(a.sample_ids, ARRAY[]::TEXT[])
FROM categories c
LEFT JOIN aggregated a USING(category)
ORDER BY c.category
"""


def audit_postgres_reconciliation(
    connection_factory: Callable[[], object], *, sample_limit: int = 20
) -> ReconciliationAudit:
    """Inspect reconciliation integrity without mutating any V2 table."""
    if sample_limit < 1 or sample_limit > 100:
        raise ValueError("SAMPLE_LIMIT_MUST_BE_BETWEEN_1_AND_100")
    connection = connection_factory()
    try:
        cursor = connection.cursor()
        # PostgreSQL enforces this for every statement in the transaction.
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute(_AUDIT_SQL, (sample_limit,))
        rows = cursor.fetchall()
        findings = tuple(
            ReconciliationFinding(str(category), int(count), tuple(samples or ()))
            for category, count, samples in rows
        )
        return ReconciliationAudit(findings)
    finally:
        # Roll back the read-only transaction and close even on query failure.
        connection.rollback()
        connection.close()
