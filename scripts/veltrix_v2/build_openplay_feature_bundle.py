"""Build a provenance-complete OpenPlay feature bundle from Neon staging.

This is read-only against Neon. It streams Parquet rows by match, calls the
unit-tested OpenPlay adapter one match at a time, and writes derived JSONL plus
a SHA-256 manifest. No raw provider bytes leave the process and no DB writes
are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping
from urllib.parse import urlparse

EXPECTED_DATABASE = "veltrix_football_staging"
EXPECTED_HOST = "ep-ancient-block-bcb439pk.c-16.us-east-1.aws.neon.tech"
PROVIDER = "OpenPlay / WhoScored / Opta"
SOURCE_ID = "openplay-data-v0.1.0"
APPROVAL_ID = "approval-openplay-whoscored-opta-noncommercial-2026-11-15"
TAG_COMMIT = "ac0bd9aff52016066433ebebf818bec4278fcf54"
AUTHORIZATION_SHA256 = "5e6bd00416f180109751e422521d76910da8b491c62507c4d9836e6700c38c46"
TIMESTAMP_EVIDENCE_ID = "openplay-data-v0.1.0:DATA_DICTIONARY.md#matches.scraped_at"
TIMESTAMP_EVIDENCE_SHA256 = "24a1037a948afa1759e3bc2babeb8b17b9e1e2dc3c8a8beea2e18f9b5b671279"

PARQUET_ROWS = {
    "competitions.parquet": 22,
    "teams.parquet": 422,
    "players.parquet": 20782,
    "matches.parquet": 26547,
    "lineups.parquet": 1068162,
    "formations.parquet": 245468,
    "cards.parquet": 115499,
    "shots.parquet": 669404,
    "player_match_stats.parquet": 775994,
    "team_match_stats.parquet": 53094,
}
CSV_FILES = ("coverage.csv", "known_gaps.csv", "data_issues.csv",
             "qualifier_dictionary.csv", "checksums.json")
TABLE_KEYS = {
    "team_match_stats.parquet": ("match_id", "team_id"),
    "player_match_stats.parquet": ("match_id", "team_id", "player_id"),
    "lineups.parquet": ("match_id", "team_id", "player_id"),
    "shots.parquet": ("match_id", "event_id", "event_id_sub"),
    "cards.parquet": ("match_id", "event_id"),
    "formations.parquet": (
        "match_id", "team_id", "period", "start_expanded_minute",
        "formation_id", "sub_on_player_id", "sub_off_player_id",
    ),
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str, allow_nan=False).encode("utf-8")


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def parse_aware(value: Any, code: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise RuntimeError(code + "_MISSING")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(code + "_NOT_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _approval_evidence(cur, now: datetime) -> dict[str, Any]:
    cur.execute("""
        SELECT status,rights_basis,evidence_sha256,valid_from,valid_until,
               permitted_uses,commercial_use_allowed,attribution_required,
               attribution_text,attribution_url,raw_redistribution_allowed,created_at
        FROM source_approvals WHERE approval_id=%s
    """, (APPROVAL_ID,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError("OPENPLAY_STAGING_APPROVAL_MISSING")
    (status,rights_basis,evidence_hash,valid_from,valid_until,uses,commercial,
     attribution_required,attribution_text,attribution_url,raw_redistribution,created_at) = row
    if (status != "APPROVED" or rights_basis != "WRITTEN_PERMISSION"
        or evidence_hash.strip() != AUTHORIZATION_SHA256
        or commercial is not False or attribution_required is not True
        or attribution_text != "openplay (Noah Bair)"
        or attribution_url != "https://github.com/nlbair/openplay"
        or raw_redistribution is not False
        or not {"collection","storage","historical_import","internal_analysis",
                "model_training","model_validation","derived_research","cache"} <= set(uses)
        or valid_from > now or (valid_until is not None and valid_until <= now)):
        raise RuntimeError("OPENPLAY_STAGING_APPROVAL_NOT_ACTIVE_OR_SCOPE_MISMATCH")
    cur.execute("""
        SELECT status,effective_at,recorded_at,evidence_sha256
        FROM source_approval_status_events
        WHERE approval_id=%s
        ORDER BY effective_at DESC,recorded_at DESC,event_id DESC LIMIT 1
    """, (APPROVAL_ID,))
    event = cur.fetchone()
    if (not event or event[0] != "APPROVED" or event[1] > now or event[2] > now
        or event[3].strip() != AUTHORIZATION_SHA256):
        raise RuntimeError("OPENPLAY_STAGING_APPROVAL_STATUS_EVENT_INVALID")
    return {
        "approval_id": APPROVAL_ID, "status": status,
        "effective_at": iso(event[1]), "recorded_at": iso(event[2]),
        "valid_from": iso(valid_from), "valid_until": iso(valid_until),
        "approval_recorded_at": iso(created_at),
        "evidence_sha256": evidence_hash.strip(),
        "permitted_uses": sorted(uses), "commercial_use_allowed": False,
        "raw_redistribution_allowed": False, "attribution_required": True,
        "attribution_text": attribution_text, "attribution_url": attribution_url,
    }


def _write_and_verify_assets(cur, root: Path) -> dict[str, dict[str, Any]]:
    cur.execute("""
        SELECT pr.id,pr.endpoint,pr.response_sha256,pr.raw_body,
               so.id,so.payload,so.payload_sha256,so.recorded_at,so.retrieved_at,
               so.rights_approval_id,so.point_in_time_certifiable,
               so.source_published_at,so.provider_response_id
        FROM provider_responses pr
        JOIN source_observations so ON so.provider_response_id=pr.id
        WHERE pr.provider=%s AND pr.source_id=%s
          AND so.provider=%s AND so.source_id=%s
          AND so.entity_type='dataset_asset'
        ORDER BY pr.endpoint
    """, (PROVIDER,SOURCE_ID,PROVIDER,SOURCE_ID))
    expected = set(PARQUET_ROWS) | set(CSV_FILES)
    assets: dict[str, dict[str, Any]] = {}
    for (response_id,endpoint,response_hash,raw,observation_id,payload,payload_hash,
         recorded_at,retrieved_at,rights_id,pit,published_at,linked_response_id) in cur.fetchall():
        name = endpoint.rsplit("/", 1)[-1]
        if name not in expected or name in assets:
            raise RuntimeError("OPENPLAY_STAGING_ASSET_SET_INVALID")
        raw_bytes = bytes(raw)
        actual = sha256(raw_bytes)
        if (actual != response_hash.strip() or payload.get("asset_sha256") != actual
            or sha256(canonical_json(payload)) != payload_hash.strip()
            or linked_response_id != response_id or rights_id != APPROVAL_ID
            or pit is not False or published_at is not None
            or payload.get("tag_commit") != TAG_COMMIT
            or payload.get("commercial_use_allowed") is not False
            or payload.get("monetisation_prohibited") is not True):
            raise RuntimeError("OPENPLAY_STAGING_ASSET_PROVENANCE_INVALID:" + name)
        expected_rows = PARQUET_ROWS.get(name)
        if payload.get("row_count") != expected_rows:
            raise RuntimeError("OPENPLAY_STAGING_ASSET_ROW_COUNT_METADATA_INVALID:" + name)
        (root / name).write_bytes(raw_bytes)
        assets[name] = {
            "asset_name": name, "sha256": actual, "bytes": len(raw_bytes),
            "provider_response_id": int(response_id),
            "source_observation_id": int(observation_id),
            "source_observation_payload_sha256": payload_hash.strip(),
            "recorded_at": iso(recorded_at), "retrieved_at": iso(retrieved_at),
            "row_count": expected_rows,
        }
    if set(assets) != expected or len(assets) != 15:
        raise RuntimeError("OPENPLAY_STAGING_ASSET_SET_INCOMPLETE")
    return assets


def _load_match_snapshots(cur, matches_asset: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    cur.execute("""
        SELECT id,provider_entity_id,payload,payload_sha256,source_published_at,
               available_at,recorded_at,source_timestamp_basis,
               point_in_time_certifiable,rights_approval_id,provider_response_id
        FROM source_observations
        WHERE provider=%s AND source_id=%s AND entity_type='match_result_snapshot'
          AND endpoint='release-assets/data-v0.1.0/matches.parquet'
        ORDER BY provider_entity_id
    """, (PROVIDER,SOURCE_ID))
    result: dict[str, dict[str, Any]] = {}
    while True:
        batch = cur.fetchmany(2000)
        if not batch:
            break
        for row in batch:
            (observation_id,match_id,payload,payload_hash,published_at,available_at,
             recorded_at,timestamp_basis,pit,rights_id,response_id) = row
            key = str(match_id)
            if key in result:
                raise RuntimeError("OPENPLAY_DUPLICATE_MATCH_SNAPSHOT:" + key)
            if (not isinstance(payload, dict) or payload.get("match_id") != key
                or rights_id != APPROVAL_ID or pit is not True
                or timestamp_basis != "documented_guarantee"
                or response_id != matches_asset["provider_response_id"]
                or payload.get("timestamp_guarantee_evidence_id") != TIMESTAMP_EVIDENCE_ID
                or payload.get("timestamp_guarantee_evidence_sha256") != TIMESTAMP_EVIDENCE_SHA256
                or payload.get("temporal_use_scope") != "only for cutoffs at or after actual VELTRIX recorded_at"
                or published_at is None or available_at != published_at
                or recorded_at is None or recorded_at < published_at
                or sha256(canonical_json(payload)) != payload_hash.strip()):
                raise RuntimeError("OPENPLAY_MATCH_SNAPSHOT_PROVENANCE_INVALID:" + key)
            result[key] = {
                "source_observation_id": int(observation_id),
                "source_observation_payload_sha256": payload_hash.strip(),
                "provider_response_id": int(response_id),
                "source_published_at": published_at,
                "available_at": available_at,
                "recorded_at": recorded_at,
                "source_timestamp_basis": timestamp_basis,
                "payload": payload,
            }
    if len(result) != PARQUET_ROWS["matches.parquet"]:
        raise RuntimeError("OPENPLAY_MATCH_SNAPSHOT_COUNT_MISMATCH")
    return result


def _load_crosswalks(cur, assets: Mapping[str, Mapping[str, Any]], now: datetime):
    cur.execute("""
        SELECT crosswalk_version_id,entity_type,provider_entity_id,canonical_entity_key,
               mapping_status,mapping_method,valid_from,valid_until,
               evidence_observation_id,recorded_at
        FROM entity_crosswalk_versions
        WHERE provider=%s AND source_id=%s AND entity_type IN ('TEAM','COMPETITION')
          AND mapping_status='RESOLVED' AND valid_from <= %s
          AND (valid_until IS NULL OR valid_until > %s)
        ORDER BY entity_type,provider_entity_id,mapping_version DESC
    """, (PROVIDER,SOURCE_ID,now,now))
    teams: dict[str, dict[str, Any]] = {}
    competitions: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        (version_id,entity_type,provider_id,canonical_id,status,method,
         valid_from,valid_until,evidence_id,recorded_at) = row
        target = teams if entity_type == "TEAM" else competitions
        expected_asset = "teams.parquet" if entity_type == "TEAM" else "competitions.parquet"
        expected_method = "EXACT_NAME_AND_COMPETITION_OVERLAP" if entity_type == "TEAM" else "EXPLICIT_REGION_NAME_ALIAS"
        if (status != "RESOLVED" or method != expected_method
            or evidence_id != assets[expected_asset]["source_observation_id"]
            or recorded_at is None or valid_from is None or recorded_at > now
            or (valid_until is not None and valid_until <= now)):
            raise RuntimeError("OPENPLAY_CROSSWALK_EVIDENCE_INVALID:" + str(provider_id))
        key = str(provider_id)
        if key in target:
            raise RuntimeError("OPENPLAY_OVERLAPPING_RESOLVED_CROSSWALK:" + key)
        target[key] = {
            "crosswalk_version_id": int(version_id),
            "provider_entity_id": key,
            "canonical_entity_id": str(canonical_id),
            "mapping_status": status, "mapping_method": method,
            "valid_from": iso(valid_from), "valid_until": iso(valid_until),
            "recorded_at": iso(recorded_at),
            "evidence_observation_id": int(evidence_id),
        }
    if not teams or not competitions:
        raise RuntimeError("OPENPLAY_RESOLVED_CROSSWALKS_MISSING")
    return teams, competitions


def _truthy(value: Any) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}


class MatchGroupStream:
    """Bounded-memory grouping over a DuckDB cursor already ordered by match_id."""
    def __init__(self, cursor, batch_size: int = 2048):
        self.cursor = cursor
        self.batch_size = batch_size
        self.columns = [item[0] for item in cursor.description]
        self.groups = self._iter_groups()
        self.current = next(self.groups, None)

    def _iter_groups(self):
        match_id = None
        rows: list[dict[str, Any]] = []
        while True:
            batch = self.cursor.fetchmany(self.batch_size)
            if not batch:
                break
            for values in batch:
                row = dict(zip(self.columns, values))
                key = str(row.get("match_id") or "")
                if not key:
                    continue
                if match_id is None:
                    match_id = key
                elif key != match_id:
                    yield match_id, rows
                    match_id, rows = key, []
                rows.append(row)
        if match_id is not None:
            yield match_id, rows

    def take(self, match_id: str) -> list[dict[str, Any]]:
        target = int(match_id)
        while self.current is not None and int(self.current[0]) < target:
            self.current = next(self.groups, None)
        if self.current is not None and self.current[0] == match_id:
            rows = self.current[1]
            self.current = next(self.groups, None)
            return rows
        return []


def _duplicate_counts(db, root: Path) -> dict[str, dict[str, int]]:
    report = {}
    for filename, keys in TABLE_KEYS.items():
        path = str(root / filename)
        key_sql = ", ".join('"' + key + '"' for key in keys)
        groups, rows = db.execute(f"""
            SELECT count(*),coalesce(sum(n),0) FROM (
                SELECT count(*) AS n FROM read_parquet(?) GROUP BY {key_sql} HAVING count(*) > 1
            ) d
        """, [path]).fetchone()
        report[filename] = {"duplicate_natural_key_groups": int(groups),
                            "duplicate_rows_quarantined": int(rows)}
    return report


def _filtered_cursor(db, root: Path, filename: str):
    path = str(root / filename)
    keys = TABLE_KEYS[filename]
    key_sql = ", ".join('"' + key + '"' for key in keys)
    cursor = db.cursor()
    cursor.execute(f"""
        SELECT * FROM read_parquet(?)
        QUALIFY count(*) OVER (PARTITION BY {key_sql}) = 1
        ORDER BY CAST(match_id AS BIGINT)
    """, [path])
    return cursor


def build_feature_rows_from_assets(
    input_dir: str | Path,
    *,
    assets: Mapping[str, Mapping[str, Any]],
    snapshots: Mapping[str, Mapping[str, Any]],
    team_crosswalk: Mapping[str, Mapping[str, Any]],
    competition_crosswalk: Mapping[str, Mapping[str, Any]],
    approval: Mapping[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Pure Parquet-to-feature stage; all input provenance is supplied by staging."""
    import duckdb
    from veltrix_v2.data.openplay_features import (
        OPENPLAY_XG_MODEL, build_openplay_team_match_features,
    )

    root = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows_path = out / "openplay_team_match_features.jsonl"
    db = duckdb.connect(database=":memory:")
    counters = {
        "matches_seen": 0, "matches_in_scope": 0,
        "matches_excluded_known_gaps_or_issues": 0,
        "matches_unmapped": 0, "matches_without_snapshot": 0,
        "matches_without_team_stats": 0, "feature_rows_written": 0,
    }
    exclusions = {}
    try:
        gaps_path = str(root / "known_gaps.csv")
        issues_path = str(root / "data_issues.csv")
        excluded = set()
        for csv_path in (gaps_path, issues_path):
            values = db.execute(
                "SELECT DISTINCT CAST(match_id AS VARCHAR) FROM read_csv_auto(?,header=true,all_varchar=true)",
                [csv_path],
            ).fetchall()
            excluded.update(str(row[0]) for row in values if row[0] is not None)
        exclusions["known_gap_and_data_issue_match_ids"] = len(excluded)
        duplicate_report = _duplicate_counts(db, root)

        matches_cursor = db.cursor()
        matches_cursor.execute("""
            SELECT * FROM read_parquet(?)
            WHERE in_v1_scope IS TRUE AND score_matches_events IS TRUE
              AND xg_model = ?
            ORDER BY CAST(match_id AS BIGINT)
        """, [str(root / "matches.parquet"), OPENPLAY_XG_MODEL])
        table_streams = {
            filename: MatchGroupStream(_filtered_cursor(db, root, filename))
            for filename in TABLE_KEYS
        }
        team_map = {key: value["canonical_entity_id"] for key, value in team_crosswalk.items()}
        comp_map = {key: value["canonical_entity_id"] for key, value in competition_crosswalk.items()}
        approval_times = [
            parse_aware(approval["effective_at"], "OPENPLAY_APPROVAL_EFFECTIVE_AT"),
            parse_aware(approval["recorded_at"], "OPENPLAY_APPROVAL_RECORDED_AT"),
            parse_aware(approval["approval_recorded_at"], "OPENPLAY_APPROVAL_ROW_RECORDED_AT"),
        ]
        eligible_min: datetime | None = None
        eligible_max: datetime | None = None
        with rows_path.open("w", encoding="utf-8", newline="\n") as output:
            columns = [item[0] for item in matches_cursor.description]
            while True:
                batch = matches_cursor.fetchmany(1000)
                if not batch:
                    break
                for values in batch:
                    match = dict(zip(columns, values))
                    match_id = str(match.get("match_id") or "")
                    if not match_id:
                        continue
                    counters["matches_seen"] += 1
                    if match_id in excluded:
                        counters["matches_excluded_known_gaps_or_issues"] += 1
                        continue
                    counters["matches_in_scope"] += 1
                    snapshot = snapshots.get(match_id)
                    if snapshot is None:
                        counters["matches_without_snapshot"] += 1
                        continue
                    payload = snapshot["payload"]
                    # Use the exact timezone-aware timestamp parsed and persisted by VELTRIX.
                    match["scraped_at"] = payload["scraped_at_utc"]
                    match["date"] = match["date"].isoformat() if isinstance(match.get("date"), date) else match.get("date")
                    home_id = str(match.get("home_team_id") or "")
                    away_id = str(match.get("away_team_id") or "")
                    comp_code = str(match.get("comp") or "")
                    if not (home_id in team_map and away_id in team_map and comp_code in comp_map):
                        counters["matches_unmapped"] += 1
                        continue

                    grouped = {
                        filename: table_streams[filename].take(match_id)
                        for filename in TABLE_KEYS
                    }
                    if not grouped["team_match_stats.parquet"]:
                        counters["matches_without_team_stats"] += 1
                        continue
                    feature_rows = build_openplay_team_match_features(
                        matches=[match],
                        team_match_stats=grouped["team_match_stats.parquet"],
                        player_match_stats=grouped["player_match_stats.parquet"],
                        lineups=grouped["lineups.parquet"],
                        shots=grouped["shots.parquet"],
                        cards=grouped["cards.parquet"],
                        formations=grouped["formations.parquet"],
                        team_crosswalk=team_map,
                        competition_crosswalk=comp_map,
                        recorded_at_by_match={match_id: snapshot["recorded_at"]},
                    )
                    for feature in feature_rows:
                        team_mapping = team_crosswalk[feature.provider_team_id]
                        opponent_mapping = team_crosswalk[feature.provider_opponent_id]
                        comp_mapping = competition_crosswalk[feature.competition_code]
                        clocks = [
                            feature.source_published_at, feature.available_at, feature.recorded_at,
                            *approval_times,
                            parse_aware(team_mapping["valid_from"], "TEAM_CROSSWALK_VALID_FROM"),
                            parse_aware(team_mapping["recorded_at"], "TEAM_CROSSWALK_RECORDED_AT"),
                            parse_aware(opponent_mapping["valid_from"], "OPPONENT_CROSSWALK_VALID_FROM"),
                            parse_aware(opponent_mapping["recorded_at"], "OPPONENT_CROSSWALK_RECORDED_AT"),
                            parse_aware(comp_mapping["valid_from"], "COMP_CROSSWALK_VALID_FROM"),
                            parse_aware(comp_mapping["recorded_at"], "COMP_CROSSWALK_RECORDED_AT"),
                        ]
                        eligibility_at = max(clocks)
                        asset_provenance = {
                            name: dict(value) for name, value in sorted(assets.items())
                        }
                        crosswalk_provenance = {
                            "team": dict(team_mapping),
                            "opponent": dict(opponent_mapping),
                            "competition": dict(comp_mapping),
                        }
                        row = {
                            "provider": PROVIDER, "source_id": SOURCE_ID,
                            "provider_match_id": feature.provider_match_id,
                            "provider_team_id": feature.provider_team_id,
                            "provider_opponent_id": feature.provider_opponent_id,
                            "canonical_team_id": feature.canonical_team_id,
                            "canonical_opponent_id": feature.canonical_opponent_id,
                            "canonical_competition_id": feature.canonical_competition_id,
                            "competition_code": feature.competition_code,
                            "season": feature.season, "match_date": feature.match_date.isoformat(),
                            "source_published_at": iso(feature.source_published_at),
                            "available_at": iso(feature.available_at),
                            "recorded_at": iso(feature.recorded_at),
                            "eligibility_at": iso(eligibility_at),
                            "xg_model": feature.xg_model, "metrics": feature.metrics,
                            "rights_approval_id": feature.rights_approval_id,
                            "commercial_use_allowed": False, "monetisation_prohibited": True,
                            "attribution_text": approval["attribution_text"],
                            "attribution_url": approval["attribution_url"],
                            "source_observation_id": snapshot["source_observation_id"],
                            "source_observation_payload_sha256": snapshot["source_observation_payload_sha256"],
                            "provider_response_id": snapshot["provider_response_id"],
                            "source_timestamp_basis": snapshot["source_timestamp_basis"],
                            "timestamp_evidence_id": TIMESTAMP_EVIDENCE_ID,
                            "timestamp_evidence_sha256": TIMESTAMP_EVIDENCE_SHA256,
                            "point_in_time_certifiable": True,
                            "asset_provenance": asset_provenance,
                            "crosswalk_provenance": crosswalk_provenance,
                            "approval_provenance": dict(approval),
                            "adapter_feature_sha256": feature.feature_sha256,
                        }
                        row["feature_sha256"] = sha256(canonical_json(row))
                        output.write(json.dumps(row, sort_keys=True, separators=(",", ":"),
                                                 ensure_ascii=False, allow_nan=False) + "\n")
                        counters["feature_rows_written"] += 1
                        eligible_min = eligibility_at if eligible_min is None else min(eligible_min, eligibility_at)
                        eligible_max = eligibility_at if eligible_max is None else max(eligible_max, eligibility_at)
        if counters["feature_rows_written"] == 0:
            raise RuntimeError("OPENPLAY_FEATURE_BUNDLE_EMPTY")
    finally:
        db.close()

    rows_digest = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    manifest = {
        "status": "PASS_STAGING_FEATURE_BUNDLE",
        "provider": PROVIDER, "source_id": SOURCE_ID,
        "release_tag": "data-v0.1.0", "tag_commit": TAG_COMMIT,
        "feature_rows_file": rows_path.name,
        "feature_rows_sha256": rows_digest,
        "feature_count": counters["feature_rows_written"],
        "counters": counters,
        "exclusions": exclusions,
        "duplicate_natural_keys": duplicate_report,
        "team_crosswalk_count": len(team_crosswalk),
        "competition_crosswalk_count": len(competition_crosswalk),
        "asset_provenance": {name: dict(value) for name, value in sorted(assets.items())},
        "rights_approval_id": APPROVAL_ID,
        "approval_evidence_sha256": approval["evidence_sha256"],
        "commercial_use_allowed": False, "monetisation_prohibited": True,
        "raw_redistribution_allowed": False,
        "attribution_text": approval["attribution_text"],
        "attribution_url": approval["attribution_url"],
        "timestamp_evidence_id": TIMESTAMP_EVIDENCE_ID,
        "timestamp_evidence_sha256": TIMESTAMP_EVIDENCE_SHA256,
        "eligibility_at_min": iso(eligible_min),
        "eligibility_at_max": iso(eligible_max),
        "temporal_rule": "cutoff must be strictly later than source page-save, actual VELTRIX recorded_at, approval recording/effective times and all three resolved crosswalk validity/recording times",
        "historical_cutoffs_before_import_or_crosswalk_verification_eligible": False,
        "same_day_match_features_eligible_for_target": False,
        "database_writes": 0,
    }
    manifest_path = out / "openplay_feature_bundle_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_from_staging(database_url: str, output_dir: str | Path) -> dict[str, Any]:
    parsed = urlparse(database_url)
    if (parsed.hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("OPENPLAY_FEATURE_STAGING_HOST_MISMATCH")
    import psycopg

    now = datetime.now(timezone.utc)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="veltrix-openplay-") as temp:
        root = Path(temp)
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(),current_user")
                database, role = cur.fetchone()
                if database != EXPECTED_DATABASE or role != "neondb_owner":
                    raise RuntimeError("OPENPLAY_FEATURE_STAGING_TARGET_MISMATCH")
                approval = _approval_evidence(cur, now)
                assets = _write_and_verify_assets(cur, root)
                snapshots = _load_match_snapshots(cur, assets["matches.parquet"])
                teams, competitions = _load_crosswalks(cur, assets, now)
        return build_feature_rows_from_assets(
            root, assets=assets, snapshots=snapshots,
            team_crosswalk=teams, competition_crosswalk=competitions,
            approval=approval, output_dir=out,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="openplay-feature-bundle")
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL") or os.getenv("VELTRIX_STAGING_DATABASE_URL") or ""
    if not database_url:
        raise RuntimeError("OPENPLAY_FEATURE_STAGING_DATABASE_URL_REQUIRED")
    manifest = build_from_staging(database_url, args.output_dir)
    print(json.dumps({
        "status": manifest["status"],
        "feature_count": manifest["feature_count"],
        "feature_rows_sha256": manifest["feature_rows_sha256"],
        "matches_in_scope": manifest["counters"]["matches_in_scope"],
        "matches_unmapped": manifest["counters"]["matches_unmapped"],
        "duplicate_rows_quarantined": sum(
            value["duplicate_rows_quarantined"]
            for value in manifest["duplicate_natural_keys"].values()
        ),
        "database_writes": 0,
        "commercial_use_allowed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
