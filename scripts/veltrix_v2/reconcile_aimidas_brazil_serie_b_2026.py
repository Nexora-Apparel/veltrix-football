#!/usr/bin/env python3
"""Read-only AI Midas 2026 Brazil Serie B match identity reconciliation.

Verifies all 738 team-match rows / 369 matches against the canonical 5Dollar
fixture registry. Emits row fingerprints and candidate crosswalk evidence only.
No database writes, normalized imports, or RESOLVED crosswalks are performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.veltrix_v2.collect_aimidas_snapshot import (
    APPROVAL_ID, REPOSITORY, SOURCE_COMMIT, SOURCE_FILES,
)
from scripts.veltrix_v2.import_aimidas_staging import EXPECTED_DATABASE, EXPECTED_HOST

PROVIDER = "AI Midas Football Data"
SOURCE_ID = "ai-midas-github-csv"
SOURCE_PATH = "advanced stats/Brazil Serie B 2026.csv"
CANONICAL_PROVIDER = "5DollarFootballAPI"
CANONICAL_COMPETITION_ID = "522514093"
CANONICAL_COMPETITION_NAME = "Brazil Serie B"
EXPECTED_ROLE = "neondb_owner"
MATCH_RE = re.compile(r"^(?P<home>.+) (?P<hg>\\d+)-(?P<ag>\\d+) (?P<away>.+)$")

TEAM_ALIASES = {
    "América Mineiro": "America MG",
    "Atlético Goianiense": "Atletico GO",
    "Avaí": "Avai",
    "Ceará": "Ceara",
    "Criciúma": "Criciuma",
    "Cuiabá": "Cuiaba",
    "Goiás": "Goias",
    "Náutico": "Nautico",
    "Operário PR": "Operario PR",
    "São Bernardo": "Sao Bernardo",
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_row_hash(row: dict[str, str]) -> str:
    serialized = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(serialized.encode("utf-8"))


def source_match_key(source_date: str, match_label: str) -> str:
    material = "\\0".join((SOURCE_COMMIT, SOURCE_PATH, source_date, match_label))
    return sha256(material.encode("utf-8"))


def parse_match_label(label: str) -> dict:
    match = MATCH_RE.fullmatch((label or "").strip())
    if not match:
        raise ValueError("AIMIDAS_MATCH_LABEL_INVALID:" + str(label))
    return {
        "home_raw": match.group("home").strip(),
        "home_score": int(match.group("hg")),
        "away_score": int(match.group("ag")),
        "away_raw": match.group("away").strip(),
    }


def canonical_team_name(source_name: str) -> str:
    return TEAM_ALIASES.get(source_name, source_name)


def read_source_rows(input_dir: Path) -> tuple[list[dict], dict, bytes]:
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_repository") != REPOSITORY or manifest.get("source_commit_sha") != SOURCE_COMMIT:
        raise RuntimeError("AIMIDAS_SOURCE_PIN_MISMATCH")
    record = next((item for item in manifest.get("files", []) if item.get("path") == SOURCE_PATH), None)
    spec = next((item for item in SOURCE_FILES if item.path == SOURCE_PATH), None)
    if record is None or spec is None:
        raise RuntimeError("AIMIDAS_SERIE_B_SOURCE_FILE_MISSING")
    raw = (input_dir / "snapshots" / SOURCE_PATH).read_bytes()
    if len(raw) != spec.expected_bytes or len(raw) != record.get("actual_bytes"):
        raise RuntimeError("AIMIDAS_SERIE_B_BYTE_COUNT_MISMATCH")
    if sha256(raw) != record.get("sha256"):
        raise RuntimeError("AIMIDAS_SERIE_B_SHA256_MISMATCH")
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
    required = {"Team", "Match", "Date", "Goals", "Goals Conceded"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise RuntimeError("AIMIDAS_SERIE_B_REQUIRED_COLUMNS_MISSING")
    rows = []
    for line_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        team = (row.get("Team") or "").strip()
        label = (row.get("Match") or "").strip()
        source_date = (row.get("Date") or "").strip()
        try:
            parsed_date = date.fromisoformat(source_date)
            goals = int(float(row["Goals"]))
            goals_conceded = int(float(row["Goals Conceded"]))
        except (TypeError, ValueError):
            raise RuntimeError(f"AIMIDAS_SERIE_B_ROW_INVALID:{line_number}") from None
        if not team or not label or goals < 0 or goals_conceded < 0:
            raise RuntimeError(f"AIMIDAS_SERIE_B_ROW_INVALID:{line_number}")
        match = parse_match_label(label)
        row_hash = canonical_row_hash(row)
        rows.append({
            "source_line_number": line_number,
            "source_row_sha256": row_hash,
            "source_row_id": f"aimidas:{SOURCE_COMMIT}:{SOURCE_PATH}:{line_number}:{row_hash[:16]}",
            "source_team_raw": team,
            "source_team_canonical": canonical_team_name(team),
            "match_label": label,
            "source_date_raw": source_date,
            "source_date": parsed_date.isoformat(),
            "match": match,
            "row_goals": goals,
            "row_goals_conceded": goals_conceded,
        })
    if len(rows) != spec.expected_rows or len(rows) != 738:
        raise RuntimeError(f"AIMIDAS_SERIE_B_ROW_COUNT_MISMATCH:{len(rows)}")
    if len({item["source_team_raw"] for item in rows}) != 20:
        raise RuntimeError("AIMIDAS_SERIE_B_TEAM_COUNT_MISMATCH")
    return rows, record, raw


def read_canonical_registry(database_url: str, source_raw: bytes, source_record: dict) -> dict:
    parsed = urlparse(database_url)
    if (parsed.hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("AIMIDAS_SERIE_B_DATABASE_HOST_MISMATCH")
    if parse_qs(parsed.query).get("sslmode", [""])[0].casefold() not in {"require", "verify-ca", "verify-full"}:
        raise RuntimeError("AIMIDAS_SERIE_B_TLS_REQUIRED")
    import psycopg

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT current_database(), current_user, current_setting('transaction_read_only')")
            database, role, read_only = cur.fetchone()
            if database != EXPECTED_DATABASE or role != EXPECTED_ROLE or read_only != "on":
                raise RuntimeError("AIMIDAS_SERIE_B_READ_ONLY_TARGET_MISMATCH")

            cur.execute(
                """
                SELECT o.id, o.source_id, o.endpoint, o.payload_sha256, o.payload,
                       o.rights_approval_id, o.retrieved_at, o.point_in_time_certifiable,
                       r.id, r.request_id, r.response_sha256, r.raw_body, r.fetched_at
                FROM source_observations o
                JOIN provider_responses r ON r.id=o.provider_response_id
                WHERE o.provider=%s AND o.source_id=%s AND o.endpoint=%s
                  AND o.entity_type='dataset_asset'
                """,
                (PROVIDER, SOURCE_ID, "github_raw/" + SOURCE_PATH),
            )
            evidence = cur.fetchall()
            if len(evidence) != 1:
                raise RuntimeError("AIMIDAS_SERIE_B_STAGING_EVIDENCE_CARDINALITY")
            (observation_id, source_id, endpoint, payload_hash, payload, rights_id,
             retrieved_at, pit, response_id, request_id, response_hash, raw_body, fetched_at) = evidence[0]
            if bytes(raw_body) != source_raw or sha256(bytes(raw_body)) != response_hash.strip():
                raise RuntimeError("AIMIDAS_SERIE_B_STAGING_RAW_BYTES_MISMATCH")
            if source_id != SOURCE_ID or rights_id != APPROVAL_ID or pit is not False:
                raise RuntimeError("AIMIDAS_SERIE_B_STAGING_RIGHTS_OR_PIT_MISMATCH")
            if payload.get("git_blob_sha1") != source_record.get("git_blob_sha1"):
                raise RuntimeError("AIMIDAS_SERIE_B_STAGING_GIT_BLOB_MISMATCH")
            if payload.get("row_count") != 738 or payload.get("distinct_match_labels") != 369 or payload.get("distinct_teams") != 20:
                raise RuntimeError("AIMIDAS_SERIE_B_STAGING_MANIFEST_MISMATCH")

            cur.execute(
                "SELECT id, provider_team_id, name FROM teams WHERE provider=%s ORDER BY name, provider_team_id",
                (CANONICAL_PROVIDER,),
            )
            teams = [{"id": row[0], "provider_team_id": row[1], "name": row[2]} for row in cur.fetchall()]

            cur.execute(
                """
                SELECT f.id, f.provider_fixture_id, f.kickoff_at, f.status,
                       f.home_team_id, ht.provider_team_id, ht.name,
                       f.away_team_id, at.provider_team_id, at.name,
                       fr.home_score, fr.away_score, c.name, c.provider, c.provider_competition_id
                FROM fixtures f
                JOIN competitions c ON c.id=f.competition_id
                JOIN teams ht ON ht.id=f.home_team_id
                JOIN teams at ON at.id=f.away_team_id
                LEFT JOIN fixture_results fr ON fr.fixture_id=f.id
                WHERE c.provider=%s AND c.provider_competition_id=%s
                  AND f.kickoff_at >= '2026-01-01T00:00:00Z'
                  AND f.kickoff_at < '2027-01-01T00:00:00Z'
                ORDER BY f.kickoff_at, f.id
                """,
                (CANONICAL_PROVIDER, CANONICAL_COMPETITION_ID),
            )
            fixtures = []
            for row in cur.fetchall():
                (fixture_id, provider_fixture_id, kickoff_at, status, home_id,
                 home_provider_id, home_name, away_id, away_provider_id, away_name,
                 home_score, away_score, competition, provider, competition_provider_id) = row
                if competition != CANONICAL_COMPETITION_NAME or provider != CANONICAL_PROVIDER or competition_provider_id != CANONICAL_COMPETITION_ID:
                    raise RuntimeError("AIMIDAS_SERIE_B_CANONICAL_COMPETITION_MISMATCH")
                fixtures.append({
                    "fixture_id": fixture_id,
                    "provider_fixture_id": provider_fixture_id,
                    "kickoff_at": kickoff_at.isoformat(),
                    "kickoff_date": kickoff_at.date().isoformat(),
                    "status": status,
                    "home_team_id": home_id,
                    "home_provider_team_id": home_provider_id,
                    "home_name": home_name,
                    "away_team_id": away_id,
                    "away_provider_team_id": away_provider_id,
                    "away_name": away_name,
                    "home_score": home_score,
                    "away_score": away_score,
                })
    return {
        "database": database,
        "role": role,
        "transaction_read_only": read_only,
        "staging_evidence": {
            "source_observation_id": observation_id,
            "provider_response_id": response_id,
            "source_id": source_id,
            "request_id": request_id,
            "endpoint": endpoint,
            "response_sha256": response_hash.strip(),
            "payload_sha256": payload_hash.strip(),
            "rights_approval_id": rights_id,
            "point_in_time_certifiable": pit,
            "retrieved_at": retrieved_at.isoformat(),
            "fetched_at": fetched_at.isoformat(),
            "raw_body_bytes": len(raw_body),
            "raw_body_matches_pinned_snapshot": True,
        },
        "teams": teams,
        "fixtures": fixtures,
    }


def reconcile(rows: list[dict], registry: dict, source_record: dict, *,
              expected_matches: int = 369, expected_teams: int = 20,
              expected_missing: int = 2) -> dict:
    team_lookup: dict[str, list[dict]] = defaultdict(list)
    for team in registry["teams"]:
        team_lookup[team["name"]].append(team)
    source_team_names = sorted({row["source_team_raw"] for row in rows})
    team_mappings = []
    source_team_to_id = {}
    for source_name in source_team_names:
        canonical_name = canonical_team_name(source_name)
        candidates = team_lookup.get(canonical_name, [])
        if len(candidates) != 1:
            raise RuntimeError(f"AIMIDAS_SERIE_B_TEAM_MAPPING_NOT_UNIQUE:{source_name}:{len(candidates)}")
        source_team_to_id[source_name] = candidates[0]["id"]
        team_mappings.append({
            "source_team": source_name,
            "canonical_team": canonical_name,
            "canonical_provider_team_id": candidates[0]["provider_team_id"],
            "canonical_team_registry_id": candidates[0]["id"],
            "mapping_method": "EXPLICIT_REVIEWED_ALIAS" if source_name != canonical_name else "EXACT_NAME",
            "review_status": "REVIEW_REQUIRED",
        })
    if len(team_mappings) != expected_teams or len({item["canonical_team_registry_id"] for item in team_mappings}) != expected_teams:
        raise RuntimeError("AIMIDAS_SERIE_B_TEAM_ID_COLLISION_OR_COUNT_FAILURE")

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        grouped[(row["source_date"], row["match_label"])].append(row)

    fixtures = registry["fixtures"]
    canonical_by_identity: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for fixture in fixtures:
        canonical_by_identity[(fixture["home_team_id"], fixture["away_team_id"])].append(fixture)

    match_details = []
    source_fixture_ids = []
    date_deltas = Counter()
    for (source_date, label), group in sorted(grouped.items()):
        parsed = parse_match_label(label)
        if len(group) != 2:
            raise RuntimeError(f"AIMIDAS_SERIE_B_MATCH_TEAM_ROW_COUNT:{label}:{len(group)}")
        source_home_id = source_team_to_id.get(parsed["home_raw"])
        source_away_id = source_team_to_id.get(parsed["away_raw"])
        if source_home_id is None or source_away_id is None:
            raise RuntimeError("AIMIDAS_SERIE_B_MATCH_TEAM_NOT_IN_TEAM_MAP")
        if {row["source_team_raw"] for row in group} != {parsed["home_raw"], parsed["away_raw"]}:
            raise RuntimeError(f"AIMIDAS_SERIE_B_MATCH_TEAM_ROWS_DISAGREE:{label}")
        for row in group:
            is_home = row["source_team_raw"] == parsed["home_raw"]
            expected_goals = parsed["home_score"] if is_home else parsed["away_score"]
            expected_conceded = parsed["away_score"] if is_home else parsed["home_score"]
            if row["row_goals"] != expected_goals or row["row_goals_conceded"] != expected_conceded:
                raise RuntimeError(f"AIMIDAS_SERIE_B_TEAM_ROW_SCORE_MISMATCH:{row['source_line_number']}")
        src_date = date.fromisoformat(source_date)
        candidates = []
        for fixture in canonical_by_identity.get((source_home_id, source_away_id), []):
            delta = (date.fromisoformat(fixture["kickoff_date"]) - src_date).days
            if abs(delta) <= 1:
                candidates.append((fixture, delta))
        if len(candidates) != 1:
            raise RuntimeError(f"AIMIDAS_SERIE_B_FIXTURE_CANDIDATE_CARDINALITY:{label}:{len(candidates)}")
        fixture, delta = candidates[0]
        score_agrees = (
            fixture["home_score"] is not None and fixture["away_score"] is not None
            and fixture["home_score"] == parsed["home_score"]
            and fixture["away_score"] == parsed["away_score"]
        )
        if not score_agrees:
            raise RuntimeError(f"AIMIDAS_SERIE_B_CANONICAL_SCORE_MISMATCH:{label}")
        date_deltas[str(delta)] += 1
        source_fixture_ids.append(fixture["fixture_id"])
        row_evidence = sorted(group, key=lambda item: item["source_line_number"])
        match_details.append({
            "source_match_key_sha256": source_match_key(source_date, label),
            "source_date": source_date,
            "source_row_ids": [item["source_row_id"] for item in row_evidence],
            "source_row_line_numbers": [item["source_line_number"] for item in row_evidence],
            "source_row_sha256": [item["source_row_sha256"] for item in row_evidence],
            "canonical_fixture_id": fixture["fixture_id"],
            "canonical_provider_fixture_id": fixture["provider_fixture_id"],
            "canonical_kickoff_at": fixture["kickoff_at"],
            "source_to_canonical_utc_date_delta_days": delta,
            "score_agreement": True,
            "review_status": "REVIEW_REQUIRED",
            "crosswalk_resolution": "NOT_RESOLVED",
        })

    if len(match_details) != expected_matches or len(set(source_fixture_ids)) != expected_matches:
        raise RuntimeError("AIMIDAS_SERIE_B_MATCH_OR_FIXTURE_UNIQUENESS_FAILURE")

    mapped_pairs = {
        (source_team_to_id[parse_match_label(label)["home_raw"]],
         source_team_to_id[parse_match_label(label)["away_raw"]], source_date)
        for source_date, label in grouped
    }
    missing = []
    for fixture in fixtures:
        fixture_date = date.fromisoformat(fixture["kickoff_date"])
        represented = any(
            home_id == fixture["home_team_id"] and away_id == fixture["away_team_id"]
            and abs((fixture_date - date.fromisoformat(source_date)).days) <= 1
            for home_id, away_id, source_date in mapped_pairs
        )
        if not represented:
            missing.append({
                "canonical_fixture_id": fixture["fixture_id"],
                "canonical_provider_fixture_id": fixture["provider_fixture_id"],
                "kickoff_at": fixture["kickoff_at"],
                "home_team": fixture["home_name"],
                "away_team": fixture["away_name"],
                "home_score": fixture["home_score"],
                "away_score": fixture["away_score"],
                "source_row_present": False,
                "disposition": "UNRESOLVED_NO_REPLACEMENT_MAPPING",
            })
    if len(missing) != expected_missing:
        raise RuntimeError(f"AIMIDAS_SERIE_B_MISSING_FIXTURE_COUNT:{len(missing)}")

    row_fingerprints = []
    for row in sorted(rows, key=lambda item: item["source_line_number"]):
        row_fingerprints.append({
            "source_row_id": row["source_row_id"],
            "source_line_number": row["source_line_number"],
            "source_row_sha256": row["source_row_sha256"],
            "source_match_key_sha256": source_match_key(row["source_date"], row["match_label"]),
            "team_slot": "HOME" if row["source_team_raw"] == row["match"]["home_raw"] else "AWAY",
        })

    return {
        "schema_version": "veltrix-aimidas-brazil-serie-b-identity-audit-v1",
        "audit_status": "PASS_WITH_TWO_SOURCE_COVERAGE_GAPS",
        "source": {
            "repository": REPOSITORY,
            "commit": SOURCE_COMMIT,
            "approval_id": APPROVAL_ID,
            "source_id": SOURCE_ID,
            "path": SOURCE_PATH,
            "git_blob_sha1": source_record["git_blob_sha1"],
            "file_sha256": source_record["sha256"],
            "file_bytes": source_record["actual_bytes"],
            "source_observation_id": registry["staging_evidence"]["source_observation_id"],
            "provider_response_id": registry["staging_evidence"]["provider_response_id"],
            "provider_response_sha256": registry["staging_evidence"]["response_sha256"],
            "source_rows": len(rows),
            "distinct_matches": len(match_details),
            "distinct_teams": len(team_mappings),
            "date_min": min(row["source_date"] for row in rows),
            "date_max": max(row["source_date"] for row in rows),
        },
        "database": {
            "database": registry["database"],
            "role": registry["role"],
            "transaction_read_only": registry["transaction_read_only"],
            "canonical_competition": CANONICAL_COMPETITION_NAME,
            "canonical_provider_competition_id": CANONICAL_COMPETITION_ID,
            "canonical_2026_fixture_count": len(fixtures),
            "canonical_team_count": expected_teams,
            "staging_evidence": registry["staging_evidence"],
        },
        "summary": {
            "source_team_identities_verified": len(team_mappings),
            "source_team_identities_total": expected_teams,
            "source_matches_verified": len(match_details),
            "source_matches_total": expected_matches,
            "unique_canonical_fixture_ids": len(set(source_fixture_ids)),
            "fixture_identity_failures": 0,
            "independent_score_agreements": len(match_details),
            "score_disagreements": 0,
            "ambiguous_fixture_candidates": 0,
            "duplicate_source_match_groups": 0,
            "source_row_score_consistency_checks": len(rows),
            "source_row_score_consistency_failures": 0,
            "source_to_canonical_utc_date_delta_counts": dict(sorted(date_deltas.items())),
            "canonical_fixtures_absent_from_source": len(missing),
            "crosswalk_rows_written": 0,
            "normalized_fixture_rows_written": 0,
            "database_mutations": 0,
            "model_admitted": False,
            "point_in_time_certifiable": False,
        },
        "team_mappings": team_mappings,
        "matches": match_details,
        "row_fingerprints": row_fingerprints,
        "missing_canonical_fixtures": missing,
        "review": {
            "reviewer_acceptance": "PENDING",
            "reviewer_id": None,
            "crosswalk_status": "REVIEW_REQUIRED",
            "resolution_rule": "Do not mark RESOLVED until a reviewer explicitly accepts the complete evidence set.",
        },
        "temporal_and_odds_boundary": {
            "point_in_time_certifiable": False,
            "historical_closing_odds_qualified": False,
            "clv_qualified": False,
            "average_odds_are_not_closing_quotes": True,
            "value_betting": "LOCKED",
        },
        "side_effects": {
            "database_mutations": 0,
            "crosswalk_rows_written": 0,
            "normalized_fixture_rows_written": 0,
            "production_written": False,
            "predictions_changed": False,
            "deployment_performed": False,
            "telegram_sent": False,
            "schedule_activated": False,
            "value_betting_unlocked": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary-output")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL_REQUIRED")
    rows, source_record, raw = read_source_rows(Path(args.input_dir))
    registry = read_canonical_registry(database_url, raw, source_record)
    report = reconcile(rows, registry, source_record)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\\n", encoding="utf-8")
    if args.summary_output:
        summary_path = Path(args.summary_output)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\\n", encoding="utf-8")
    print(json.dumps({
        "status": report["audit_status"],
        "teams_verified": report["summary"]["source_team_identities_verified"],
        "matches_verified": report["summary"]["source_matches_verified"],
        "score_agreements": report["summary"]["independent_score_agreements"],
        "missing_canonical_fixtures": report["summary"]["canonical_fixtures_absent_from_source"],
        "database_mutations": 0,
        "crosswalk_rows_written": 0,
        "value_betting": "LOCKED",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
