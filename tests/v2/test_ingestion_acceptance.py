from datetime import datetime, timedelta, timezone

import pytest

from veltrix_v2.domain.contracts import DataUsePurpose, RightsStatus, SourceRights
from veltrix_v2.ingestion.acceptance import (
    IngestionRejected,
    ProviderSourceRecord,
    accept_provider_record,
)


NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


def rights(**overrides):
    values = dict(
        source_id="provider-primary",
        rights_status=RightsStatus.VERIFIED,
        commercial_use_allowed=True,
        permitted_uses=frozenset({
            DataUsePurpose.HISTORICAL_IMPORT,
            DataUsePurpose.CACHE,
            DataUsePurpose.MODEL_TRAINING,
            DataUsePurpose.INFERENCE,
        }),
        terms_url="https://provider.example/terms",
        terms_version="2026-11-06",
        verified_at_utc=NOW,
        evidence_sha256="b" * 64,
    )
    values.update(overrides)
    return SourceRights(**values)


def record(**overrides):
    values = dict(
        provider="primary-provider",
        source_id="provider-primary",
        provider_record_id="response-123",
        provider_fixture_id="fixture-456",
        provider_competition_id="league-7",
        data_class="FIXTURE",
        raw_payload_sha256="c" * 64,
        payload_reference="raw/provider-primary/response-123.json",
        fetched_at_utc=NOW,
        ingested_at_utc=NOW + timedelta(seconds=1),
        source_updated_at_utc=NOW - timedelta(seconds=5),
    )
    values.update(overrides)
    return ProviderSourceRecord(**values)


def test_acceptance_requires_rights_for_requested_use_and_cache():
    result = accept_provider_record(
        record(), rights(), purpose=DataUsePurpose.HISTORICAL_IMPORT
    )
    assert [item.purpose for item in result.rights_decisions] == [
        DataUsePurpose.HISTORICAL_IMPORT,
        DataUsePurpose.CACHE,
    ]
    assert all(item.allowed for item in result.rights_decisions)


def test_record_is_rejected_when_cache_permission_is_not_granted():
    source_rights = rights(
        permitted_uses=frozenset({DataUsePurpose.HISTORICAL_IMPORT})
    )
    with pytest.raises(ValueError, match="PURPOSE_NOT_PERMITTED"):
        accept_provider_record(
            record(), source_rights, purpose=DataUsePurpose.HISTORICAL_IMPORT
        )


def test_unverified_rights_block_before_acceptance():
    with pytest.raises(ValueError, match="RIGHTS_UNVERIFIED"):
        accept_provider_record(
            record(),
            rights(rights_status=RightsStatus.UNVERIFIED),
            purpose=DataUsePurpose.HISTORICAL_IMPORT,
        )


def test_source_identity_must_match_rights_register():
    with pytest.raises(IngestionRejected, match="does not match rights"):
        accept_provider_record(
            record(source_id="different-provider"),
            rights(),
            purpose=DataUsePurpose.HISTORICAL_IMPORT,
        )


@pytest.mark.parametrize("digest", ["", "not-a-hash", "a" * 63, "g" * 64])
def test_invalid_raw_payload_hash_is_rejected(digest):
    with pytest.raises(IngestionRejected, match="SHA-256"):
        accept_provider_record(
            record(raw_payload_sha256=digest),
            rights(),
            purpose=DataUsePurpose.HISTORICAL_IMPORT,
        )


def test_naive_fetch_timestamp_is_rejected():
    with pytest.raises(IngestionRejected, match="fetched_at_utc"):
        accept_provider_record(
            record(fetched_at_utc=datetime(2026, 11, 6, 12, 0)),
            rights(),
            purpose=DataUsePurpose.HISTORICAL_IMPORT,
        )


def test_ingestion_cannot_precede_fetch():
    with pytest.raises(IngestionRejected, match="cannot precede"):
        accept_provider_record(
            record(ingested_at_utc=NOW - timedelta(seconds=1)),
            rights(),
            purpose=DataUsePurpose.HISTORICAL_IMPORT,
        )


def test_provider_provenance_and_rights_decisions_are_preserved():
    original = record()
    accepted = accept_provider_record(
        original, rights(), purpose=DataUsePurpose.INFERENCE
    )
    assert accepted.record == original
    assert accepted.record.provider_fixture_id == "fixture-456"
    assert accepted.record.provider_competition_id == "league-7"
    assert accepted.rights_decisions[0].terms_url == "https://provider.example/terms"
    assert accepted.rights_decisions[0].evidence_sha256 == "b" * 64


def test_cache_only_purpose_is_checked_once():
    accepted = accept_provider_record(
        record(), rights(), purpose=DataUsePurpose.CACHE
    )
    assert len(accepted.rights_decisions) == 1
    assert accepted.rights_decisions[0].purpose is DataUsePurpose.CACHE
