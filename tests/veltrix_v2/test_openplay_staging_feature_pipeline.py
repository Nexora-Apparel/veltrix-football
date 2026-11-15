from __future__ import annotations

import csv
from datetime import date, datetime, timezone

import pytest

from scripts.veltrix_v2.build_openplay_feature_bundle import (
    APPROVAL_ID,
    PROVIDER,
    SOURCE_ID,
    build_feature_rows_from_assets,
)
from veltrix_v2.data.openplay_feature_bundle import (
    eligible_openplay_features_as_of,
    iter_openplay_feature_bundle,
)

UTC = timezone.utc
SAVED = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
RECORDED = datetime(2026, 11, 15, 12, 56, 5, 890000, tzinfo=UTC)
CROSSWALKED = datetime(2026, 11, 15, 13, 9, 32, 332000, tzinfo=UTC)


def _write_parquet(db, table: str, path):
    db.execute(f"COPY {table} TO '{path.as_posix()}' (FORMAT PARQUET)")


def _assets():
    return {
        name: {
            "asset_name": name, "sha256": "a" * 64, "bytes": 100,
            "provider_response_id": index, "source_observation_id": 100 + index,
            "source_observation_payload_sha256": "b" * 64,
            "recorded_at": RECORDED.isoformat(), "retrieved_at": RECORDED.isoformat(),
            "row_count": None,
        }
        for index, name in enumerate((
            "matches.parquet", "team_match_stats.parquet", "player_match_stats.parquet",
            "lineups.parquet", "shots.parquet", "cards.parquet", "formations.parquet",
            "teams.parquet", "competitions.parquet",
        ), 1)
    }


def _crosswalk(provider_id, canonical_id, evidence_id, method="EXACT_NAME_AND_COMPETITION_OVERLAP"):
    return {
        "canonical_entity_id": canonical_id,
        "crosswalk_version_id": evidence_id,
        "provider_entity_id": str(provider_id),
        "mapping_status": "RESOLVED",
        "mapping_method": method,
        "valid_from": CROSSWALKED.isoformat(),
        "valid_until": None,
        "recorded_at": CROSSWALKED.isoformat(),
        "evidence_observation_id": evidence_id,
    }


def _make_assets(tmp_path, duplicate_player=False):
    duckdb = pytest.importorskip("duckdb")
    db = duckdb.connect(database=":memory:")
    db.execute("""
        CREATE TABLE matches(
            match_id BIGINT, comp VARCHAR, season VARCHAR, date DATE,
            home_team_id BIGINT, home_team VARCHAR, away_team_id BIGINT,
            away_team VARCHAR, xg_model VARCHAR, scraped_at TIMESTAMP,
            score_matches_events BOOLEAN, in_v1_scope BOOLEAN
        )
    """)
    db.execute("""
        INSERT INTO matches VALUES
        (7,'eng','2526','2026-11-01',100,'Home FC',200,'Away FC',
         'openplay_xg_v1','2026-11-02 12:00:00',TRUE,TRUE)
    """)
    db.execute("""
        CREATE TABLE team_match_stats(
            match_id BIGINT, team_id BIGINT, opponent_id BIGINT,
            goals_for INTEGER, goals_against INTEGER, xg DOUBLE, npxg DOUBLE,
            shots INTEGER, shots_on_target INTEGER, passes INTEGER,
            passes_completed INTEGER, tackles INTEGER, interceptions INTEGER,
            possession_pct DOUBLE
        )
    """)
    db.execute("""
        INSERT INTO team_match_stats VALUES
        (7,100,200,2,1,1.8,1.2,12,5,400,330,18,9,0.58),
        (7,200,100,1,2,0.8,0.7,7,2,290,220,20,11,0.42)
    """)
    db.execute("""
        CREATE TABLE player_match_stats(
            match_id BIGINT, team_id BIGINT, player_id BIGINT, is_starter BOOLEAN,
            minutes_played INTEGER, xg DOUBLE, npxg DOUBLE, shots INTEGER,
            shots_on_target INTEGER, goals INTEGER, xa DOUBLE, key_passes INTEGER,
            tackles INTEGER, interceptions INTEGER
        )
    """)
    db.execute("""
        INSERT INTO player_match_stats VALUES
        (7,100,1,TRUE,90,0.4,0.4,2,1,1,0.2,2,1,1),
        (7,200,2,TRUE,90,0.3,0.3,1,1,0,0.1,1,2,1)
    """)
    if duplicate_player:
        db.execute("INSERT INTO player_match_stats VALUES (7,100,1,TRUE,90,0.4,0.4,2,1,1,0.2,2,1,1)")
    db.execute("""
        CREATE TABLE lineups(
            match_id BIGINT, team_id BIGINT, player_id BIGINT,
            is_starter BOOLEAN, played BOOLEAN, is_captain_start BOOLEAN
        )
    """)
    db.execute("""
        INSERT INTO lineups VALUES
        (7,100,1,TRUE,TRUE,TRUE),(7,200,2,TRUE,TRUE,TRUE)
    """)
    db.execute("""
        CREATE TABLE shots(
            match_id BIGINT, event_id BIGINT, event_id_sub BIGINT, team_id BIGINT,
            xg DOUBLE, is_shootout BOOLEAN, is_penalty BOOLEAN,
            is_on_target BOOLEAN, is_big_chance BOOLEAN, is_set_piece BOOLEAN
        )
    """)
    db.execute("""
        INSERT INTO shots VALUES
        (7,1,0,100,0.4,FALSE,FALSE,TRUE,TRUE,FALSE),
        (7,2,0,200,0.2,FALSE,FALSE,TRUE,FALSE,FALSE)
    """)
    db.execute("""
        CREATE TABLE cards(match_id BIGINT, event_id BIGINT, team_id BIGINT, card VARCHAR)
    """)
    db.execute("INSERT INTO cards VALUES (7,3,100,'yellow')")
    db.execute("""
        CREATE TABLE formations(
            match_id BIGINT, team_id BIGINT, period INTEGER,
            start_expanded_minute INTEGER, formation_id BIGINT,
            sub_on_player_id BIGINT, sub_off_player_id BIGINT, formation VARCHAR
        )
    """)
    db.execute("""
        INSERT INTO formations VALUES
        (7,100,1,0,1,NULL,NULL,'4231'),(7,200,1,0,2,NULL,NULL,'433')
    """)
    for table, filename in (
        ("matches","matches.parquet"),
        ("team_match_stats","team_match_stats.parquet"),
        ("player_match_stats","player_match_stats.parquet"),
        ("lineups","lineups.parquet"),
        ("shots","shots.parquet"),
        ("cards","cards.parquet"),
        ("formations","formations.parquet"),
    ):
        _write_parquet(db, table, tmp_path / filename)
    db.close()
    for filename in ("known_gaps.csv", "data_issues.csv"):
        with (tmp_path / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["match_id","comp","season","in_v1_scope"])
    return tmp_path


def _snapshots():
    payload = {
        "match_id": "7",
        "scraped_at_utc": SAVED.isoformat(),
        "timestamp_guarantee_evidence_id": "openplay-data-v0.1.0:DATA_DICTIONARY.md#matches.scraped_at",
        "timestamp_guarantee_evidence_sha256": "24a1037a948afa1759e3bc2babeb8b17b9e1e2dc3c8a8beea2e18f9b5b671279",
        "temporal_use_scope": "only for cutoffs at or after actual VELTRIX recorded_at",
    }
    import hashlib, json
    payload_hash = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str, allow_nan=False,
    ).encode()).hexdigest()
    return {
        "7": {
            "source_observation_id": 700,
            "source_observation_payload_sha256": payload_hash,
            "provider_response_id": 1,
            "source_published_at": SAVED,
            "available_at": SAVED,
            "recorded_at": RECORDED,
            "source_timestamp_basis": "documented_guarantee",
            "payload": payload,
        }
    }


def _approval():
    return {
        "status": "APPROVED",
        "effective_at": datetime(2026, 11, 15, 0, 0, tzinfo=UTC).isoformat(),
        "recorded_at": datetime(2026, 11, 15, 12, 37, 26, tzinfo=UTC).isoformat(),
        "approval_recorded_at": datetime(2026, 11, 15, 12, 37, 26, tzinfo=UTC).isoformat(),
        "evidence_sha256": "5e6bd00416f180109751e422521d76910da8b491c62507c4d9836e6700c38c46",
        "attribution_text": "openplay (Noah Bair)",
        "attribution_url": "https://github.com/nlbair/openplay",
        "valid_until": None,
    }


def test_streaming_staging_adapter_builds_provenance_bound_features(tmp_path):
    assets_dir = _make_assets(tmp_path)
    assets = _assets()
    teams = {
        "100": _crosswalk("100", "team-home", 108),
        "200": _crosswalk("200", "team-away", 108),
    }
    competitions = {
        "eng": _crosswalk("eng", "competition-eng", 109, "EXPLICIT_REGION_NAME_ALIAS")
    }
    output_dir = tmp_path / "output"
    manifest = build_feature_rows_from_assets(
        assets_dir, assets=assets, snapshots=_snapshots(),
        team_crosswalk=teams, competition_crosswalk=competitions,
        approval=_approval(), output_dir=output_dir,
    )
    assert manifest["status"] == "PASS_STAGING_FEATURE_BUNDLE"
    assert manifest["feature_count"] == 2
    assert manifest["counters"]["matches_seen"] == 1
    assert manifest["database_writes"] == 0
    rows = tuple(iter_openplay_feature_bundle(output_dir / "openplay_feature_bundle_manifest.json"))
    assert len(rows) == 2
    home = next(row for row in rows if row["canonical_team_id"] == "team-home")
    assert home["canonical_opponent_id"] == "team-away"
    assert home["canonical_competition_id"] == "competition-eng"
    assert home["source_observation_id"] == 700
    assert home["recorded_at"] == RECORDED.isoformat()
    assert home["eligibility_at"] == CROSSWALKED.isoformat()
    assert home["metrics"]["team"]["xg"] == 1.8
    assert home["rights_approval_id"] == APPROVAL_ID
    assert home["commercial_use_allowed"] is False
    assert len(home["feature_sha256"]) == 64
    eligible = eligible_openplay_features_as_of(
        rows, cutoff_at=datetime(2026, 11, 15, 13, 10, tzinfo=UTC),
        canonical_team_id="team-home", before_match_date="2026-11-03",
    )
    assert len(eligible) == 1


def test_streaming_adapter_quarantines_all_duplicate_player_natural_key_rows(tmp_path):
    assets_dir = _make_assets(tmp_path, duplicate_player=True)
    manifest = build_feature_rows_from_assets(
        assets_dir, assets=_assets(), snapshots=_snapshots(),
        team_crosswalk={
            "100": _crosswalk("100", "team-home", 108),
            "200": _crosswalk("200", "team-away", 108),
        },
        competition_crosswalk={
            "eng": _crosswalk("eng", "competition-eng", 109, "EXPLICIT_REGION_NAME_ALIAS")
        },
        approval=_approval(), output_dir=tmp_path / "output",
    )
    assert manifest["duplicate_natural_keys"]["player_match_stats.parquet"] == {
        "duplicate_natural_key_groups": 1, "duplicate_rows_quarantined": 2,
    }
    rows = tuple(iter_openplay_feature_bundle(tmp_path / "output/openplay_feature_bundle_manifest.json"))
    home = next(row for row in rows if row["canonical_team_id"] == "team-home")
    assert home["metrics"]["players"]["players_in_match_stats"] == 0
