from veltrix_v2.data.coverage_sql import (
    FIXTURE_COVERAGE_SQL, OBSERVATION_COVERAGE_SQL,
    FIVEDOLLAR_CROSSWALK_BOOTSTRAP_SQL,
    validate_read_only_coverage_sql,
)


def test_coverage_queries_are_read_only_and_use_actual_staging_tables():
    validate_read_only_coverage_sql()
    assert "FROM fixtures AS f" in FIXTURE_COVERAGE_SQL
    assert "JOIN source_observations AS o" in OBSERVATION_COVERAGE_SQL
    assert "f.id::text AS fixture_id" in OBSERVATION_COVERAGE_SQL
    assert "o.recorded_at AS recorded_at" in OBSERVATION_COVERAGE_SQL
    assert "o.point_in_time_certifiable AS point_in_time_certifiable" in OBSERVATION_COVERAGE_SQL
    assert "o.payload_sha256 AS payload_sha256" in FIVEDOLLAR_CROSSWALK_BOOTSTRAP_SQL
    assert "o.provider = '5DollarFootballAPI'" in FIVEDOLLAR_CROSSWALK_BOOTSTRAP_SQL
    assert "FROM fixtures AS f" in FIVEDOLLAR_CROSSWALK_BOOTSTRAP_SQL


def test_mutating_sql_is_rejected(monkeypatch):
    import veltrix_v2.data.coverage_sql as sql_module
    monkeypatch.setattr(sql_module, "FIXTURE_COVERAGE_SQL", "DELETE FROM fixtures")
    try:
        sql_module.validate_read_only_coverage_sql()
    except ValueError as exc:
        assert str(exc) == "COVERAGE_SQL_MUST_START_WITH_SELECT"
    else:
        raise AssertionError("mutating SQL was not rejected")
