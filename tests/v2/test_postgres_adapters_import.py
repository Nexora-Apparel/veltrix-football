def test_v2_storage_and_identity_adapters_import_without_opening_connections():
    from veltrix_v2.history.postgres import PostgresHistoryStore
    from veltrix_v2.identity.postgres_registry import PostgresIdentityMappingRepository
    from veltrix_v2.identity.postgres_fixtures import PostgresFixtureDecisionRepository
    from veltrix_v2.ingestion.postgres_records import PostgresProviderRecordRepository

    def forbidden_connection():
        raise AssertionError("repository construction must not connect to a database")

    assert PostgresHistoryStore(forbidden_connection)
    assert PostgresIdentityMappingRepository(forbidden_connection)
    assert PostgresFixtureDecisionRepository(forbidden_connection)
    assert PostgresProviderRecordRepository(forbidden_connection)
