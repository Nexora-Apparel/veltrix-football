"""Read-only SQL templates for the staging coverage audit.

These statements are SELECT-only and return aliases accepted by
persisted_coverage_adapter. The caller must use a read-only DB role.
"""

FIXTURE_COVERAGE_SQL = """
SELECT
    f.id::text AS fixture_id,
    f.competition_id::text AS competition_id,
    f.kickoff_at AS kickoff_at
FROM fixtures AS f
ORDER BY f.competition_id, f.kickoff_at, f.id
""".strip()


FIVEDOLLAR_CROSSWALK_BOOTSTRAP_SQL = """
SELECT
    f.id::text AS canonical_fixture_id,
    f.competition_id::text AS canonical_competition_id,
    f.home_team_id::text AS canonical_home_team_id,
    f.away_team_id::text AS canonical_away_team_id,
    o.id::text AS source_observation_id,
    o.provider AS provider,
    o.source_id AS source_id,
    o.payload AS payload,
    o.payload_sha256 AS payload_sha256
FROM fixtures AS f
JOIN source_observations AS o
  ON o.id = f.source_observation_id
WHERE o.provider = '5DollarFootballAPI'
  AND o.source_id = '5dollarfootballapi'
  AND o.data_type = 'fixture_result'
ORDER BY f.id, o.id
""".strip()


OBSERVATION_COVERAGE_SQL = """
SELECT
    f.id::text AS fixture_id,
    f.competition_id::text AS competition_id,
    f.kickoff_at AS fixture_kickoff_at,
    o.provider AS provider,
    o.source_id AS source_id,
    o.data_type AS data_type,
    o.payload_sha256 AS payload_sha256,
    o.available_at AS available_at,
    o.recorded_at AS recorded_at,
    o.rights_approval_id AS rights_approval_id,
    o.payload AS payload,
    o.point_in_time_certifiable AS point_in_time_certifiable,
    o.source_published_at AS source_published_at,
    o.source_effective_at AS source_effective_at,
    o.availability_basis AS availability_basis,
    EXISTS (
        SELECT 1 FROM capture_manifests AS cm
        WHERE cm.manifest_sha256 = o.payload->>'manifest_sha256'
    ) AS capture_manifest_verified
FROM fixtures AS f
JOIN source_observations AS o
  ON o.id = f.source_observation_id
ORDER BY f.competition_id, f.id, o.id
""".strip()


def validate_read_only_coverage_sql() -> None:
    """Fail closed if a future edit adds a mutating SQL statement."""
    for statement in (
        FIXTURE_COVERAGE_SQL, OBSERVATION_COVERAGE_SQL,
        FIVEDOLLAR_CROSSWALK_BOOTSTRAP_SQL,
    ):
        normalized = " ".join(statement.lower().split())
        if not normalized.startswith("select "):
            raise ValueError("COVERAGE_SQL_MUST_START_WITH_SELECT")
        forbidden = (" insert ", " update ", " delete ", " truncate ", " alter ", " drop ", " create ")
        if any(token in f" {normalized} " for token in forbidden):
            raise ValueError("COVERAGE_SQL_MUTATION_FORBIDDEN")
