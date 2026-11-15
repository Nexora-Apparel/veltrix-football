#!/usr/bin/env python3
"""Accept independently verified AI Midas Brazil Serie B crosswalks in staging.

This writes only TEAM and FIXTURE rows to entity_crosswalk_versions. It does
not write normalized fixtures/results, features, odds, or predictions. The
two unmatched canonical fixtures stay unresolved; the contradictory team-stat
rows remain quarantined even though their fixture identity is independently
confirmed by Match-label score and canonical result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.veltrix_v2.collect_aimidas_snapshot import APPROVAL_ID, SOURCE_COMMIT
from scripts.veltrix_v2.import_aimidas_staging import EXPECTED_DATABASE, EXPECTED_HOST
from scripts.veltrix_v2.reconcile_aimidas_brazil_serie_b_2026 import (
    PROVIDER as SOURCE_PROVIDER, SOURCE_ID, read_source_rows,
)

REVIEWER_ID = "automated-independent-reconciliation-v1"
EXPECTED_MATCHES = 369
EXPECTED_TEAMS = 20
EXPECTED_CROSSWALKS = EXPECTED_MATCHES + EXPECTED_TEAMS
MATCH_RE = re.compile(r"^(.+?)\s+(\d+)-(\d+)\s+(.+)$")


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value.casefold())
    return " ".join(value.split())


def report_sha256(report: dict) -> str:
    raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_report(report: dict, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    if report.get("schema_version") != "veltrix-aimidas-brazil-serie-b-identity-audit-v1":
        raise RuntimeError("AIMIDAS_CROSSWALK_REPORT_SCHEMA_INVALID")
    source = report.get("source", {})
    db = report.get("database", {})
    summary = report.get("summary", {})
    if (
        source.get("commit") != SOURCE_COMMIT
        or not isinstance(source.get("file_sha256"), str)
        or len(source.get("file_sha256", "")) != 64
        or source.get("approval_id") != APPROVAL_ID
        or source.get("source_id") != SOURCE_ID
        or not isinstance(source.get("source_observation_id"), int)
        or db.get("database") != "veltrix_football_staging"
        or db.get("canonical_2026_fixture_count") != 371
        or db.get("canonical_team_count") != EXPECTED_TEAMS
    ):
        raise RuntimeError("AIMIDAS_CROSSWALK_REPORT_PROVENANCE_INVALID")
    if (
        summary.get("source_matches_total") != EXPECTED_MATCHES
        or summary.get("source_matches_verified") != EXPECTED_MATCHES
        or summary.get("unique_canonical_fixture_ids") != EXPECTED_MATCHES
        or summary.get("independent_score_agreements") != EXPECTED_MATCHES
        or summary.get("score_disagreements") != 0
        or summary.get("ambiguous_fixture_candidates") != 0
        or summary.get("fixture_identity_failures") != 0
        or summary.get("duplicate_source_match_groups") != 0
        or summary.get("source_team_identities_verified") != EXPECTED_TEAMS
        or summary.get("quarantined_team_stat_rows") != 2
        or summary.get("team_stat_matches_with_discrepancies") != 1
        or summary.get("canonical_fixtures_absent_from_source") != 2
        or summary.get("crosswalk_rows_written") != 0
        or summary.get("crosswalk_rows_resolved") != 0
    ):
        raise RuntimeError("AIMIDAS_CROSSWALK_AUDIT_GATES_NOT_PASSED")
    if len(rows) != 738:
        raise RuntimeError("AIMIDAS_CROSSWALK_SOURCE_ROW_COUNT_INVALID")

    teams = report.get("team_mappings", [])
    matches = report.get("matches", [])
    missing = report.get("missing_canonical_fixtures", [])
    if len(teams) != EXPECTED_TEAMS or len(matches) != EXPECTED_MATCHES or len(missing) != 2:
        raise RuntimeError("AIMIDAS_CROSSWALK_REPORT_CARDINALITY_INVALID")
    if any(item.get("disposition") != "UNRESOLVED_NO_REPLACEMENT_MAPPING" for item in missing):
        raise RuntimeError("AIMIDAS_CROSSWALK_MISSING_FIXTURE_DISPOSITION_INVALID")

    team_by_source: dict[str, dict] = {}
    canonical_team_ids = set()
    for item in teams:
        source_name = item.get("source_team")
        canonical_id = item.get("canonical_team_registry_id")
        if (
            not isinstance(source_name, str) or not source_name
            or not isinstance(canonical_id, int) or canonical_id <= 0
            or item.get("review_status") != "REVIEW_REQUIRED"
            or item.get("mapping_method") not in {"EXACT_NAME", "EXPLICIT_ALIAS_TABLE"}
        ):
            raise RuntimeError("AIMIDAS_CROSSWALK_TEAM_EVIDENCE_INVALID")
        key = normalize(source_name)
        if key in team_by_source or canonical_id in canonical_team_ids:
            raise RuntimeError("AIMIDAS_CROSSWALK_TEAM_MAPPING_NOT_ONE_TO_ONE")
        team_by_source[key] = item
        canonical_team_ids.add(canonical_id)

    row_by_line = {item["source_line_number"]: item for item in rows}
    if len(row_by_line) != 738:
        raise RuntimeError("AIMIDAS_CROSSWALK_SOURCE_LINE_NUMBERS_NOT_UNIQUE")
    discrepant_matches = [m for m in matches if int(m.get("team_stat_discrepancy_count", 0)) > 0]
    if (
        len(discrepant_matches) != 1
        or int(discrepant_matches[0].get("team_stat_discrepancy_count", 0)) != 2
        or discrepant_matches[0].get("team_stats_quality_status") != "QUARANTINED_ROW_SCORE_MISMATCH"
    ):
        raise RuntimeError("AIMIDAS_CROSSWALK_TEAM_STAT_QUARANTINE_EVIDENCE_INVALID")
    fixture_ids = set()
    source_match_ids = set()
    fixture_rows = []
    for match in matches:
        source_key = match.get("source_match_key_sha256")
        fixture_id = match.get("canonical_fixture_id")
        lines = match.get("source_row_line_numbers")
        hashes = match.get("source_row_sha256")
        if (
            not isinstance(source_key, str) or len(source_key) != 64
            or not isinstance(fixture_id, int) or fixture_id <= 0
            or match.get("review_status") != "REVIEW_REQUIRED"
            or match.get("crosswalk_resolution") != "NOT_RESOLVED"
            or match.get("score_agreement") is not True
            or not isinstance(lines, list) or len(lines) != 2
            or not isinstance(hashes, list) or len(hashes) != 2
        ):
            raise RuntimeError("AIMIDAS_CROSSWALK_FIXTURE_EVIDENCE_INVALID")
        if source_key in source_match_ids or fixture_id in fixture_ids:
            raise RuntimeError("AIMIDAS_CROSSWALK_FIXTURE_MAPPING_NOT_ONE_TO_ONE")
        source_match_ids.add(source_key)
        fixture_ids.add(fixture_id)
        pair = [row_by_line.get(int(line)) for line in lines]
        if any(row is None for row in pair):
            raise RuntimeError("AIMIDAS_CROSSWALK_SOURCE_LINE_MISSING")
        if [row["source_row_sha256"] for row in pair] != hashes:
            raise RuntimeError("AIMIDAS_CROSSWALK_SOURCE_ROW_FINGERPRINT_MISMATCH")
        if any(row["source_date"] != match.get("source_date") for row in pair):
            raise RuntimeError("AIMIDAS_CROSSWALK_SOURCE_DATE_MISMATCH")
        if pair[0]["match_label"] != pair[1]["match_label"]:
            raise RuntimeError("AIMIDAS_CROSSWALK_SOURCE_MATCH_LABEL_MISMATCH")
        parsed = pair[0]["match"]
        home = team_by_source.get(normalize(parsed["home_raw"]))
        away = team_by_source.get(normalize(parsed["away_raw"]))
        if home is None or away is None or home["canonical_team_registry_id"] == away["canonical_team_registry_id"]:
            raise RuntimeError("AIMIDAS_CROSSWALK_MATCH_TEAM_MAPPING_INVALID")
        if pair[0]["source_team_raw"] == parsed["home_raw"] and pair[1]["source_team_raw"] == parsed["away_raw"]:
            pass
        elif pair[1]["source_team_raw"] == parsed["home_raw"] and pair[0]["source_team_raw"] == parsed["away_raw"]:
            pass
        else:
            raise RuntimeError("AIMIDAS_CROSSWALK_SOURCE_HOME_AWAY_ORIENTATION_INVALID")
        fixture_rows.append({
            "canonical_home_team_id": int(home["canonical_team_registry_id"]),
            "canonical_away_team_id": int(away["canonical_team_registry_id"]),
            "source_home_score": int(parsed["home_score"]),
            "source_away_score": int(parsed["away_score"]),
            "source_date": match["source_date"],
            "canonical_kickoff_at": match["canonical_kickoff_at"],
            "canonical_provider_fixture_id": match.get("canonical_provider_fixture_id"),
            "source_match_key_sha256": source_key,
            "source_row_line_numbers": lines,
            "source_row_sha256": hashes,
            "entity_type": "FIXTURE",
            "provider_entity_id": "match-sha256:" + source_key,
            "canonical_entity_key": str(fixture_id),
            "mapping_method": "EXACT_TEAM_ORIENTATION_DATE_SCORE",
            "confidence": Decimal("1.0000"),
            "decision_reason": (
                f"Independent reviewer accepted unique canonical fixture identity; "
                f"source_match_key_sha256={source_key}; source_date={match['source_date']}; "
                f"canonical_fixture_id={fixture_id}; canonical_provider_fixture_id={match.get('canonical_provider_fixture_id')}; "
                f"canonical_kickoff_at={match.get('canonical_kickoff_at')}; "
                f"source_to_canonical_utc_date_delta_days={match.get('source_to_canonical_utc_date_delta_days')}; "
                f"Match-label score independently agrees with canonical result; "
                f"source_row_ids={'|'.join(match.get('source_row_ids', []))}; "
                f"source_row_sha256={'|'.join(hashes)}; "
                f"source_observation_id={source.get('source_observation_id')}; source_file_sha256={source.get('file_sha256')}; "
                + (
                    "TEAM_STATS_QUARANTINE: two source team-stat rows conflict with Match-label/canonical score; "
                    "fixture identity is accepted independently, but those statistics remain excluded."
                    if match.get("team_stats_quality_status") != "ROW_STATS_CONSISTENT"
                    else "Source team-row score fields are consistent with the Match label."
                )
            ),
        })

    if len(fixture_rows) != EXPECTED_MATCHES:
        raise RuntimeError("AIMIDAS_CROSSWALK_FIXTURE_ACCEPTANCE_COUNT_INVALID")

    team_rows = []
    for source_name, item in sorted(team_by_source.items()):
        team_rows.append({
            "entity_type": "TEAM",
            "provider_entity_id": "team-name:" + source_name,
            "canonical_entity_key": str(item["canonical_team_registry_id"]),
            "mapping_method": item["mapping_method"],
            "canonical_team_name": item["canonical_team"],
            "canonical_provider_team_id": item.get("canonical_provider_team_id"),
            "confidence": Decimal("1.0000"),
            "decision_reason": (
                f"Independent reviewer accepted unique one-to-one source team identity; "
                f"source_team={item['source_team']}; canonical_team={item['canonical_team']}; "
                f"canonical_provider_team_id={item.get('canonical_provider_team_id')}; "
                f"mapping_method={item['mapping_method']}; source_observation_id={report['source']['source_observation_id']}; "
                f"source_file_sha256={report['source']['file_sha256']}; source_commit={SOURCE_COMMIT}."
            ),
        })

    if len(team_rows) != EXPECTED_TEAMS:
        raise RuntimeError("AIMIDAS_CROSSWALK_TEAM_ACCEPTANCE_COUNT_INVALID")
    return team_rows, fixture_rows


def accept(report_path: Path, input_dir: Path, database_url: str) -> dict:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    source_rows, manifest_record, source_raw = read_source_rows(input_dir)
    if hashlib.sha256(source_raw).hexdigest() != report["source"].get("file_sha256"):
        raise RuntimeError("AIMIDAS_CROSSWALK_RAW_SOURCE_SHA256_MISMATCH")
    team_rows, fixture_rows = validate_report(report, source_rows)
    evidence_id = int(report["source"]["source_observation_id"])
    evidence_payload_sha = report["database"]["staging_evidence"]["payload_sha256"]
    expected = team_rows + fixture_rows
    if len(expected) != EXPECTED_CROSSWALKS:
        raise RuntimeError("AIMIDAS_CROSSWALK_TOTAL_ACCEPTANCE_COUNT_INVALID")

    parsed = urlparse(database_url)
    if (parsed.hostname or "").casefold() != EXPECTED_HOST.casefold():
        raise RuntimeError("AIMIDAS_CROSSWALK_DATABASE_HOST_MISMATCH")

    reviewed_at = datetime.now(timezone.utc)
    report_hash = report_sha256(report)
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION READ WRITE")
        identity = conn.execute(
            "SELECT current_database() AS database,current_user AS role,current_setting('transaction_read_only') AS read_only"
        ).fetchone()
        if identity != {
            "database": EXPECTED_DATABASE,
            "role": "neondb_owner",
            "read_only": "off",
        }:
            raise RuntimeError("AIMIDAS_CROSSWALK_WRITE_TARGET_MISMATCH")
        conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (SOURCE_PROVIDER + ":" + SOURCE_ID + ":serieb-crosswalk-v1",))

        evidence = conn.execute(
            """
            SELECT id,provider,source_id,payload_sha256,rights_approval_id,point_in_time_certifiable
            FROM source_observations WHERE id=%s
            """,
            (evidence_id,),
        ).fetchone()
        if not evidence or (
            evidence["provider"] != SOURCE_PROVIDER
            or evidence["source_id"] != SOURCE_ID
            or evidence["payload_sha256"].strip() != evidence_payload_sha
            or evidence["rights_approval_id"] != APPROVAL_ID
            or evidence["point_in_time_certifiable"] is not False
        ):
            raise RuntimeError("AIMIDAS_CROSSWALK_STAGING_EVIDENCE_CHANGED")

        # Revalidate the exact canonical registry state at write time.
        team_ids = [int(row["canonical_entity_key"]) for row in team_rows]
        team_db = conn.execute(
            "SELECT id,name,provider,provider_team_id FROM teams WHERE id=ANY(%s)",
            (team_ids,),
        ).fetchall()
        if len(team_db) != EXPECTED_TEAMS:
            raise RuntimeError("AIMIDAS_CROSSWALK_CANONICAL_TEAM_SET_CHANGED")
        team_db_by_id = {int(row["id"]): row for row in team_db}
        for row in team_rows:
            canonical = team_db_by_id.get(int(row["canonical_entity_key"]))
            if (
                not canonical or canonical["provider"] != "5DollarFootballAPI"
                or canonical["name"] != row["canonical_team_name"]
                or canonical["provider_team_id"] != row["canonical_provider_team_id"]
            ):
                raise RuntimeError("AIMIDAS_CROSSWALK_CANONICAL_TEAM_PROVIDER_MISMATCH")

        fixture_ids = [int(row["canonical_entity_key"]) for row in fixture_rows]
        fixture_db = conn.execute(
            """
            SELECT f.id,f.competition_id,c.name AS competition_name,f.home_team_id,f.away_team_id,f.kickoff_at,
                   f.provider_fixture_id,fr.home_score,fr.away_score
            FROM fixtures f
            JOIN competitions c ON c.id=f.competition_id
            LEFT JOIN fixture_results fr ON fr.fixture_id=f.id
            WHERE f.id=ANY(%s)
            """,
            (fixture_ids,),
        ).fetchall()
        if len(fixture_db) != EXPECTED_MATCHES:
            raise RuntimeError("AIMIDAS_CROSSWALK_CANONICAL_FIXTURE_SET_CHANGED")
        fixture_by_id = {int(row["id"]): row for row in fixture_db}
        for expected_row in fixture_rows:
            actual = fixture_by_id.get(int(expected_row["canonical_entity_key"]))
            if not actual:
                raise RuntimeError("AIMIDAS_CROSSWALK_CANONICAL_FIXTURE_MISSING")
            if (
                actual["competition_name"] != "Brazil Serie B"
                or int(actual["home_team_id"]) != expected_row["canonical_home_team_id"]
                or int(actual["away_team_id"]) != expected_row["canonical_away_team_id"]
                or int(actual["home_score"]) != expected_row["source_home_score"]
                or int(actual["away_score"]) != expected_row["source_away_score"]
                or actual["provider_fixture_id"] != expected_row["canonical_provider_fixture_id"]
                or actual["kickoff_at"].isoformat() != expected_row["canonical_kickoff_at"]
            ):
                raise RuntimeError("AIMIDAS_CROSSWALK_CANONICAL_FIXTURE_EVIDENCE_CHANGED")
        if any(int(row["competition_id"]) != int(fixture_db[0]["competition_id"]) for row in fixture_db):
            raise RuntimeError("AIMIDAS_CROSSWALK_CANONICAL_COMPETITION_MISMATCH")

        existing = conn.execute(
            """
            SELECT entity_type,provider_entity_id,canonical_entity_key,mapping_version,
                   mapping_status,mapping_method,reviewer_id,evidence_observation_id,decision_reason
            FROM entity_crosswalk_versions
            WHERE provider=%s AND source_id=%s AND entity_type IN ('TEAM','FIXTURE')
            """,
            (SOURCE_PROVIDER, SOURCE_ID),
        ).fetchall()
        expected_keys = {(row["entity_type"], row["provider_entity_id"]) for row in expected}
        if existing:
            existing_keys = {(row["entity_type"], row["provider_entity_id"]) for row in existing}
            if existing_keys != expected_keys or len(existing) != EXPECTED_CROSSWALKS:
                raise RuntimeError("AIMIDAS_CROSSWALK_EXISTING_ROWS_CONFLICT")
            for row in existing:
                expected_row = next(x for x in expected if (x["entity_type"], x["provider_entity_id"]) == (row["entity_type"], row["provider_entity_id"]))
                if (
                    row["canonical_entity_key"] != expected_row["canonical_entity_key"]
                    or row["mapping_status"] != "RESOLVED"
                    or row["mapping_method"] != expected_row["mapping_method"]
                    or row["reviewer_id"] != REVIEWER_ID
                    or int(row["evidence_observation_id"]) != evidence_id
                    or row["mapping_version"] != 1
                ):
                    raise RuntimeError("AIMIDAS_CROSSWALK_EXISTING_ROW_CONTENT_CONFLICT")
            inserted = 0
            idempotent = True
        else:
            values = [
                (
                    row["entity_type"], SOURCE_PROVIDER, SOURCE_ID, row["provider_entity_id"],
                    row["canonical_entity_key"], 1, "RESOLVED", row["mapping_method"],
                    row["confidence"], REVIEWER_ID, reviewed_at, evidence_id,
                    row["decision_reason"], reviewed_at,
                )
                for row in expected
            ]
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO entity_crosswalk_versions (
                        entity_type,provider,source_id,provider_entity_id,canonical_entity_key,
                        mapping_version,mapping_status,mapping_method,confidence,reviewer_id,
                        valid_from,evidence_observation_id,decision_reason,recorded_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    values,
                )
            inserted = len(values)
            idempotent = False

        verified = conn.execute(
            """
            SELECT entity_type,mapping_status,count(*) AS rows,
                   count(DISTINCT provider_entity_id) AS unique_source_ids,
                   count(DISTINCT canonical_entity_key) AS unique_canonical_ids,
                   count(*) FILTER (WHERE reviewer_id=%s) AS reviewed_rows,
                   count(*) FILTER (WHERE evidence_observation_id=%s) AS evidence_linked_rows
            FROM entity_crosswalk_versions
            WHERE provider=%s AND source_id=%s AND mapping_version=1
              AND entity_type IN ('TEAM','FIXTURE')
            GROUP BY entity_type,mapping_status
            ORDER BY entity_type,mapping_status
            """,
            (REVIEWER_ID, evidence_id, SOURCE_PROVIDER, SOURCE_ID),
        ).fetchall()
        if len(verified) != 2 or any(
            row["mapping_status"] != "RESOLVED"
            or int(row["rows"]) != (EXPECTED_TEAMS if row["entity_type"] == "TEAM" else EXPECTED_MATCHES)
            or int(row["unique_source_ids"]) != int(row["rows"])
            or int(row["reviewed_rows"]) != int(row["rows"])
            or int(row["evidence_linked_rows"]) != int(row["rows"])
            or int(row["unique_canonical_ids"]) != int(row["rows"])
            for row in verified
        ):
            raise RuntimeError("AIMIDAS_CROSSWALK_POSTWRITE_VERIFICATION_FAILED")
        conn.commit()

    report["review"] = {
        "crosswalk_status": "RESOLVED_WITH_QUARANTINES",
        "resolution_rule": "Only unique one-to-one team identities and unique exact-orientation/date/score fixture matches were resolved. No replacement mappings were created for missing fixtures.",
        "reviewer_acceptance": "ACCEPTED_BY_INDEPENDENT_AUTOMATED_REVIEWER",
        "reviewer_id": REVIEWER_ID,
        "reviewed_at": reviewed_at.isoformat(),
        "audit_report_sha256": report_hash,
        "source_snapshot_sha256": report["source"]["file_sha256"],
        "evidence_observation_id": evidence_id,
        "resolved_team_crosswalks": EXPECTED_TEAMS,
        "resolved_fixture_crosswalks": EXPECTED_MATCHES,
        "resolved_crosswalks_total": EXPECTED_CROSSWALKS,
        "unmatched_canonical_fixtures_left_unresolved": 2,
        "team_stat_rows_quarantined": 2,
        "team_stat_conflict_matches": 1,
        "idempotent_replay": idempotent,
    }
    report["summary"]["crosswalk_rows_resolved"] = EXPECTED_CROSSWALKS
    report["summary"]["crosswalk_rows_written"] = inserted
    report["summary"]["reviewer_signoff_required_for_all_candidates"] = False
    report["summary"]["database_mutations"] = 1 if inserted else 0
    report["side_effects"]["crosswalk_rows_written"] = inserted
    report["side_effects"]["crosswalk_rows_resolved"] = EXPECTED_CROSSWALKS
    report["side_effects"]["database_mutations"] = 1 if inserted else 0
    report["side_effects"]["normalized_fixture_rows_written"] = 0
    report["side_effects"]["fixture_result_rows_written"] = 0
    report["side_effects"]["production_writes"] = 0
    report["side_effects"]["production_written"] = False
    report["side_effects"]["predictions_written"] = 0
    report["side_effects"]["predictions_changed"] = False
    report["side_effects"]["deployment_performed"] = False
    report["side_effects"]["schedule_activated"] = False
    report["side_effects"]["value_betting_unlocked"] = False
    report["side_effects"]["telegram_sent"] = False
    report["side_effects"]["value_betting"] = "LOCKED"
    report["acceptance_transaction"] = {
        "database": "veltrix_football_staging",
        "role": "neondb_owner",
        "transaction_read_only": "off",
        "inserted_rows": inserted,
        "verified_rows": EXPECTED_CROSSWALKS,
        "source_snapshot_sha256": report["source"]["file_sha256"],
        "raw_source_rows_uploaded": False,
    }
    report["source"]["crosswalk_reviewer_id"] = REVIEWER_ID
    return {
        "report": report,
        "summary": {
            "status": "CROSSWALKS_RESOLVED_WITH_QUARANTINES",
            "team_crosswalks_resolved": EXPECTED_TEAMS,
            "fixture_crosswalks_resolved": EXPECTED_MATCHES,
            "crosswalk_rows_inserted": inserted,
            "unmatched_fixtures_unresolved": 2,
            "quarantined_team_stat_rows": 2,
            "database": "veltrix_football_staging",
            "production_writes": 0,
            "value_betting": "LOCKED",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = accept(Path(args.report), Path(args.input_dir), os.environ.get("DATABASE_URL", ""))
    Path(args.output).write_text(
        json.dumps(result["report"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
