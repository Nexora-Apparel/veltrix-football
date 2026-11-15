from datetime import datetime, timezone

import json
import pytest

from veltrix_v2.data.openplay_feature_bundle import (
    OPENPLAY_APPROVAL_ID,
    canonical_json_bytes,
    eligible_openplay_features_as_of,
    iter_openplay_feature_bundle,
    sha256_hex,
)

UTC = timezone.utc


def _row(**overrides):
    row = {
        "provider": "OpenPlay / WhoScored / Opta",
        "source_id": "openplay-data-v0.1.0",
        "provider_match_id": "100",
        "canonical_team_id": "team-a",
        "canonical_competition_id": "league-a",
        "match_date": "2026-11-01",
        "source_published_at": "2026-11-02T12:00:00+00:00",
        "available_at": "2026-11-02T12:00:00+00:00",
        "recorded_at": "2026-11-15T12:56:05.890000+00:00",
        "eligibility_at": "2026-11-15T13:09:32.332000+00:00",
        "rights_approval_id": OPENPLAY_APPROVAL_ID,
        "commercial_use_allowed": False,
        "point_in_time_certifiable": True,
        "source_timestamp_basis": "documented_guarantee",
        "crosswalk_provenance": {
            "team": {
                "provider_entity_id": "100", "canonical_entity_id": "team-a",
                "crosswalk_version_id": 20, "mapping_status": "RESOLVED",
                "evidence_observation_id": 108,
                "valid_from": "2026-11-15T13:09:32.332000+00:00",
                "recorded_at": "2026-11-15T13:09:32.332000+00:00",
                "valid_until": None,
            },
            "opponent": {
                "provider_entity_id": "200", "canonical_entity_id": "team-b",
                "crosswalk_version_id": 21, "mapping_status": "RESOLVED",
                "evidence_observation_id": 108,
                "valid_from": "2026-11-15T13:09:32.332000+00:00",
                "recorded_at": "2026-11-15T13:09:32.332000+00:00",
                "valid_until": None,
            },
            "competition": {
                "provider_entity_id": "eng", "canonical_entity_id": "league-a",
                "crosswalk_version_id": 22, "mapping_status": "RESOLVED",
                "evidence_observation_id": 109,
                "valid_from": "2026-11-15T13:09:32.332000+00:00",
                "recorded_at": "2026-11-15T13:09:32.332000+00:00",
                "valid_until": None,
            },
        },
        "approval_provenance": {
            "status": "APPROVED",
            "evidence_sha256": "5e6bd00416f180109751e422521d76910da8b491c62507c4d9836e6700c38c46",
            "effective_at": "2026-11-15T00:00:00+00:00",
            "recorded_at": "2026-11-15T12:37:26+00:00",
            "approval_recorded_at": "2026-11-15T12:37:26+00:00",
            "valid_until": None,
        },
        "asset_provenance": {
            name: {"provider_response_id": response, "source_observation_id": observation,
                   "sha256": "a" * 64}
            for name, response, observation in (
                ("matches.parquet", 101, 101),
                ("team_match_stats.parquet", 102, 102),
                ("player_match_stats.parquet", 103, 103),
                ("lineups.parquet", 104, 104),
                ("shots.parquet", 105, 105),
                ("cards.parquet", 106, 106),
                ("formations.parquet", 107, 107),
                ("teams.parquet", 108, 108),
                ("competitions.parquet", 109, 109),
            )
        },
        "source_observation_id": 700,
        "provider_response_id": 101,
        "monetisation_prohibited": True,
    }
    row.update(overrides)
    row["feature_sha256"] = sha256_hex(canonical_json_bytes(row))
    return row


def test_bundle_loader_verifies_manifest_and_feature_hash(tmp_path):
    row = _row()
    rows_path = tmp_path / "features.jsonl"
    rows_path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    import hashlib
    manifest = {
        "status": "PASS_STAGING_FEATURE_BUNDLE",
        "feature_rows_file": rows_path.name,
        "feature_rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "feature_count": 1,
        "rights_approval_id": OPENPLAY_APPROVAL_ID,
        "commercial_use_allowed": False,
        "monetisation_prohibited": True,
        "raw_redistribution_allowed": False,
        "database_writes": 0,
        "timestamp_evidence_sha256": "24a1037a948afa1759e3bc2babeb8b17b9e1e2dc3c8a8beea2e18f9b5b671279",
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert tuple(iter_openplay_feature_bundle(manifest_path)) == (row,)


def test_bundle_loader_rejects_row_hash_mismatch(tmp_path):
    row = _row()
    row["metrics"] = {"tampered": True}
    rows_path = tmp_path / "features.jsonl"
    rows_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    import hashlib
    manifest = {
        "status": "PASS_STAGING_FEATURE_BUNDLE",
        "feature_rows_file": rows_path.name,
        "feature_rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "feature_count": 1,
        "rights_approval_id": OPENPLAY_APPROVAL_ID,
        "commercial_use_allowed": False,
        "monetisation_prohibited": True,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="OPENPLAY_BUNDLE_FEATURE_HASH_MISMATCH"):
        tuple(iter_openplay_feature_bundle(manifest_path))


def test_feature_cutoff_is_strict_and_same_day_features_are_excluded():
    row = _row()
    before = datetime(2026, 11, 15, 13, 9, 32, 332000, tzinfo=UTC)
    after = datetime(2026, 11, 15, 13, 9, 33, tzinfo=UTC)
    assert eligible_openplay_features_as_of((row,), cutoff_at=before) == ()
    assert len(eligible_openplay_features_as_of(
        (row,), cutoff_at=after, canonical_team_id="team-a",
        canonical_competition_id="league-a", before_match_date="2026-11-16",
    )) == 1
    assert eligible_openplay_features_as_of(
        (row,), cutoff_at=after, before_match_date="2026-11-01",
    ) == ()


def test_feature_cutoff_rejects_expired_identity_crosswalk():
    row = _row()
    row["crosswalk_provenance"]["team"]["valid_until"] = "2026-11-15T13:09:33+00:00"
    row["feature_sha256"] = sha256_hex(canonical_json_bytes({
        key: value for key, value in row.items() if key != "feature_sha256"
    }))
    assert eligible_openplay_features_as_of(
        (row,), cutoff_at=datetime(2026, 11, 15, 13, 9, 34, tzinfo=UTC),
    ) == ()
