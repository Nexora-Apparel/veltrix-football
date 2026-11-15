#!/usr/bin/env python3
"""Read-only AI Midas historical fixture identity reconciliation.

The six pinned archives are treated as source rows, not as canonical fixtures.
This tool never writes to Neon and never marks an identity crosswalk RESOLVED.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts.veltrix_v2.collect_aimidas_snapshot import (
    REPOSITORY, SOURCE_COMMIT, SOURCE_FILES,
)
from scripts.veltrix_v2.import_aimidas_staging import EXPECTED_DATABASE, EXPECTED_HOST

PROVIDER = "AI Midas Football Data"
SOURCE_ID = "ai-midas-github-csv"
EXPECTED_ROLE = "neondb_owner"
HISTORICAL_FILES = tuple(spec for spec in SOURCE_FILES if spec.kind == "historical_match_csv")
COMPETITIONS = {
    "csv/past-seasons/leagues/Brasileirão_Série_A_2016-2024.csv": "Brazil Serie A",
    "csv/past-seasons/leagues/England_Premier_League_2016-2025.csv": "England Premier League",
    "csv/past-seasons/leagues/France_Ligue_1_2016-2025.csv": "France Ligue 1",
    "csv/past-seasons/leagues/Germany_Bundesliga_2016-2025.csv": "Germany Bundesliga I",
    "csv/past-seasons/leagues/Italy_Serie_A_2016-2025.csv": "Italy Serie A",
    "csv/past-seasons/leagues/Spain_La_Liga_2016-2025.csv": "Spain La Liga",
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def parse_source_date(value: str) -> date:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("SOURCE_DATE_EMPTY")
    # The source date is deliberately reduced to its literal calendar date.
    # No timezone conversion or UTC kickoff claim is made.
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        raise ValueError(f"SOURCE_DATE_UNPARSEABLE:{raw}") from None


def derived_season_key(competition: str, match_date: date) -> str:
    if competition == "Brazil Serie A":
        return str(match_date.year)
    start_year = match_date.year if match_date.month >= 7 else match_date.year - 1
    return f"{start_year}-{start_year + 1}"


def source_rows(input_dir: Path) -> tuple[list[dict], dict]:
    manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_repository") != REPOSITORY or manifest.get("source_commit_sha") != SOURCE_COMMIT:
        raise RuntimeError("AIMIDAS_SOURCE_PIN_MISMATCH")
    rows: list[dict] = []
    file_audits: dict = {}
    manifest_files = {item["path"]: item for item in manifest["files"]}
    for spec in HISTORICAL_FILES:
        record = manifest_files.get(spec.path)
        if not record:
            raise RuntimeError("AIMIDAS_HISTORICAL_FILE_MISSING:" + spec.path)
        raw = (input_dir / "snapshots" / spec.path).read_bytes()
        if sha256(raw) != record["sha256"] or len(raw) != record["actual_bytes"]:
            raise RuntimeError("AIMIDAS_FILE_PROVENANCE_MISMATCH:" + spec.path)
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        required = {"date", "home_name", "away_name", "homeGoalCount", "awayGoalCount", "season"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise RuntimeError("AIMIDAS_REQUIRED_IDENTITY_COLUMNS_MISSING:" + spec.path)
        comp = COMPETITIONS[spec.path]
        count = 0
        for line_no, row in enumerate(reader, start=2):
            if not any((v or "").strip() for v in row.values()):
                continue
            count += 1
            raw_date = (row.get("date") or "").strip()
            match_date = parse_source_date(raw_date)
            home = (row.get("home_name") or "").strip()
            away = (row.get("away_name") or "").strip()
            if not home or not away or normalize_name(home) == normalize_name(away):
                raise RuntimeError(f"AIMIDAS_TEAM_IDENTITY_INVALID:{spec.path}:{line_no}")
            try:
                hg, ag = int(row["homeGoalCount"]), int(row["awayGoalCount"])
                if hg < 0 or ag < 0:
                    raise ValueError
            except (TypeError, ValueError):
                raise RuntimeError(f"AIMIDAS_SCORE_INVALID:{spec.path}:{line_no}") from None
            raw_season = (row.get("season") or "").strip().lstrip("\ufeff")
            canonical_row = json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            row_hash = sha256(canonical_row.encode("utf-8"))
            rows.append({
                "source_id": SOURCE_ID,
                "source_repository": REPOSITORY,
                "source_commit": SOURCE_COMMIT,
                "source_path": spec.path,
                "source_git_blob_sha1": spec.git_blob_sha,
                "source_file_sha256": record["sha256"],
                "source_line_number": line_no,
                "source_row_sha256": row_hash,
                "source_fixture_key": f"aimidas:{SOURCE_COMMIT}:{spec.path}:{line_no}:{row_hash[:16]}",
                "competition": comp,
                "source_season_raw": raw_season,
                "derived_season_key": derived_season_key(comp, match_date),
                "source_date_raw": raw_date,
                "source_calendar_date": match_date.isoformat(),
                "home_name_raw": home,
                "away_name_raw": away,
                "home_name_normalized": normalize_name(home),
                "away_name_normalized": normalize_name(away),
                "home_score": hg,
                "away_score": ag,
            })
        if count != spec.expected_rows:
            raise RuntimeError(f"AIMIDAS_ROW_COUNT_MISMATCH:{spec.path}:{count}!={spec.expected_rows}")
        file_audits[spec.path] = {
            "rows": count,
            "git_blob_sha1": spec.git_blob_sha,
            "file_sha256": record["sha256"],
            "first_source_line": 2,
            "last_source_line": count + 1,
            "competition": comp,
        }
    return rows, file_audits


def read_canonical_registry(database_url: str) -> tuple[list[dict], dict]:
    parsed = urlparse(database_url)
    if (parsed.hostname or "").casefold() != EXPECTED_HOST:
        raise RuntimeError("AIMIDAS_RECONCILIATION_DATABASE_HOST_MISMATCH")
    if parse_qs(parsed.query).get("sslmode", [""])[0].casefold() not in {"require", "verify-ca", "verify-full"}:
        raise RuntimeError("AIMIDAS_RECONCILIATION_TLS_REQUIRED")
    import psycopg
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT current_database(), current_user, current_setting('transaction_read_only')")
            db, role, read_only = cur.fetchone()
            if db != EXPECTED_DATABASE or role != EXPECTED_ROLE or read_only != "on":
                raise RuntimeError("AIMIDAS_RECONCILIATION_READ_ONLY_TARGET_MISMATCH")
            cur.execute(
                """
                SELECT f.id AS fixture_id, f.provider, f.provider_fixture_id,
                       f.competition_id, c.name AS competition,
                       f.home_team_id, ht.name AS home_name,
                       f.away_team_id, at.name AS away_name,
                       f.kickoff_at, f.season_key, f.status,
                       fr.home_score, fr.away_score, fr.result_source
                FROM fixtures f
                JOIN competitions c ON c.id=f.competition_id
                JOIN teams ht ON ht.id=f.home_team_id
                JOIN teams at ON at.id=f.away_team_id
                LEFT JOIN fixture_results fr ON fr.fixture_id=f.id
                ORDER BY f.kickoff_at, f.id
                """
            )
            columns = [item.name for item in cur.description]
            fixtures = [dict(zip(columns, row)) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT r.request_id, r.response_sha256, r.raw_body,
                       o.id AS observation_id, o.payload_sha256,
                       o.provider_response_id, o.rights_approval_id,
                       o.point_in_time_certifiable, o.source_published_at,
                       o.source_effective_at, o.source_timestamp_basis
                FROM provider_responses r
                JOIN source_observations o ON o.provider_response_id=r.id
                WHERE r.provider=%s AND r.source_id=%s
                  AND r.request_id LIKE %s
                ORDER BY r.request_id
                """,
                (PROVIDER, SOURCE_ID, SOURCE_COMMIT + ":csv/past-seasons/%"),
            )
            evidence = cur.fetchall()
    return fixtures, {"database": db, "role": role, "transaction_read_only": read_only, "evidence_rows": evidence}


def reconcile(rows: list[dict], fixtures: list[dict]) -> dict:
    canonical_by_comp: dict[str, list[dict]] = defaultdict(list)
    for f in fixtures:
        canonical_by_comp[f["competition"]].append(f)
    exact_duplicate_groups: dict[tuple, list[dict]] = defaultdict(list)
    conflict_groups: dict[tuple, set[tuple[int, int]]] = defaultdict(set)
    team_names: dict[tuple[str, str], set[int]] = defaultdict(set)
    for f in fixtures:
        team_names[(f["competition"], normalize_name(f["home_name"]))].add(f["home_team_id"])
        team_names[(f["competition"], normalize_name(f["away_name"]))].add(f["away_team_id"])
    candidate_rows = []
    status_counts = Counter()
    season_counts = Counter()
    for row in rows:
        identity = (row["competition"], row["source_calendar_date"], row["home_name_normalized"], row["away_name_normalized"])
        score_identity = identity + (row["home_score"], row["away_score"])
        exact_duplicate_groups[score_identity].append(row)
        conflict_groups[identity].add((row["home_score"], row["away_score"]))
        season_counts[(row["competition"], row["derived_season_key"])] += 1
        candidates = []
        match_date = date.fromisoformat(row["source_calendar_date"])
        for f in canonical_by_comp.get(row["competition"], []):
            if normalize_name(f["home_name"]) != row["home_name_normalized"] or normalize_name(f["away_name"]) != row["away_name_normalized"]:
                continue
            canonical_date = f["kickoff_at"].date()
            if abs((canonical_date - match_date).days) > 1:
                continue
            score_agrees = (
                f["home_score"] is not None and f["away_score"] is not None
                and int(f["home_score"]) == row["home_score"]
                and int(f["away_score"]) == row["away_score"]
            )
            candidates.append({
                "fixture_id": f["fixture_id"],
                "provider": f["provider"],
                "provider_fixture_id": f["provider_fixture_id"],
                "kickoff_at": f["kickoff_at"].isoformat(),
                "canonical_season_key": f["season_key"],
                "canonical_status": f["status"],
                "score_agrees": score_agrees,
            })
        team_home = team_names.get((row["competition"], row["home_name_normalized"]), set())
        team_away = team_names.get((row["competition"], row["away_name_normalized"]), set())
        if len(candidates) == 1 and candidates[0]["score_agrees"]:
            status = "UNIQUE_CANONICAL_CANDIDATE_REVIEW_REQUIRED"
        elif len(candidates) == 1:
            status = "SCORE_MISMATCH_REVIEW_REQUIRED"
        elif len(candidates) > 1:
            status = "AMBIGUOUS_CANONICAL_CANDIDATES"
        elif not team_home or not team_away:
            status = "CANONICAL_TEAM_COVERAGE_MISSING"
        else:
            status = "CANONICAL_FIXTURE_COVERAGE_MISSING"
        status_counts[status] += 1
        candidate_rows.append({
            **row,
            "canonical_status": status,
            "canonical_home_team_ids": sorted(team_home),
            "canonical_away_team_ids": sorted(team_away),
            "canonical_candidates": candidates,
            "crosswalk_resolution": "NOT_RESOLVED_REVIEW_REQUIRED",
            "point_in_time_certifiable": False,
        })
    duplicate_groups = [
        {"identity": list(key), "source_fixture_keys": [r["source_fixture_key"] for r in group]}
        for key, group in exact_duplicate_groups.items() if len(group) > 1
    ]
    conflicting = [
        {"identity": list(key), "score_pairs": [list(pair) for pair in sorted(scores)]}
        for key, scores in conflict_groups.items() if len(scores) > 1
    ]
    return {
        "rows": candidate_rows,
        "summary": {
            "source_rows": len(rows),
            "canonical_fixtures_examined": len(fixtures),
            "status_counts": dict(sorted(status_counts.items())),
            "exact_duplicate_groups": len(duplicate_groups),
            "conflicting_duplicate_groups": len(conflicting),
            "season_row_counts": [
                {"competition": comp, "season": season, "rows": count}
                for (comp, season), count in sorted(season_counts.items())
            ],
            "duplicate_groups": duplicate_groups,
            "conflicting_duplicate_groups_detail": conflicting,
            "crosswalk_rows_written": 0,
            "normalized_fixture_rows_written": 0,
            "database_mutations": 0,
            "model_admitted": False,
            "point_in_time_certifiable": False,
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
    rows, file_audits = source_rows(Path(args.input_dir))
    fixtures, db_meta = read_canonical_registry(database_url)
    expected_evidence = {spec.path for spec in HISTORICAL_FILES}
    evidence_by_path = {}
    for item in db_meta["evidence_rows"]:
        request_id, response_hash, raw_body, observation_id, payload_hash, linked_id, rights_id, pit, published, effective, basis = item
        path = request_id.split(":", 1)[1]
        evidence_by_path[path] = {
            "response_sha256": response_hash.strip(),
            "actual_response_sha256": sha256(bytes(raw_body)),
            "observation_id": observation_id,
            "payload_sha256": payload_hash.strip(),
            "provider_response_id": linked_id,
            "rights_approval_id": rights_id,
            "point_in_time_certifiable": pit,
            "source_published_at": published.isoformat() if published else None,
            "source_effective_at": effective.isoformat() if effective else None,
            "source_timestamp_basis": basis,
        }
    if set(evidence_by_path) != expected_evidence:
        raise RuntimeError("AIMIDAS_STAGING_FILE_PROVENANCE_SET_MISMATCH")
    for path, evidence in evidence_by_path.items():
        if evidence["response_sha256"] != evidence["actual_response_sha256"] or evidence["point_in_time_certifiable"] is not False:
            raise RuntimeError("AIMIDAS_STAGING_RAW_EVIDENCE_MISMATCH:" + path)
        if evidence["source_published_at"] is not None or evidence["source_effective_at"] is not None or evidence["source_timestamp_basis"] != "unknown":
            raise RuntimeError("AIMIDAS_STAGING_TEMPORAL_CLASSIFICATION_MISMATCH:" + path)
        file_audits[path]["staging_evidence"] = {k: v for k, v in evidence.items() if k != "actual_response_sha256"}
    result = reconcile(rows, fixtures)
    result["source_file_audits"] = file_audits
    result["source"] = {"repository": REPOSITORY, "commit": SOURCE_COMMIT, "source_id": SOURCE_ID}
    result["database"] = {k: v for k, v in db_meta.items() if k != "evidence_rows"}
    result["policy"] = {
        "matching": "exact competition + exact normalized home/away + source calendar date within one UTC calendar day + exact score agreement",
        "season": "raw source season preserved; derived season key is calendar year for Brazil Serie A and July-to-June for European leagues",
        "resolution": "candidate only; reviewer approval required; no RESOLVED crosswalk written",
        "source_date": "literal source calendar date; timezone not inferred",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    if args.summary_output:
        summary = {k: v for k, v in result.items() if k != "rows"}
        summary["row_level_detail_retained_on_runner_only"] = True
        summary_path = Path(args.summary_output)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
