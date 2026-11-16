"""Qualify OpenPlay's pinned historical football data release without production writes.

Downloads only the compact core tables needed for player, team, lineup and shot
research. Every asset is verified against GitHub's SHA-256 release digest.
No prediction code, Neon database, or Telegram infrastructure is accessed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import duckdb

OWNER = "nlbair"
REPO = "openplay"
TAG = "data-v0.1.0"
TAG_COMMIT = "ac0bd9aff52016066433ebebf818bec4278fcf54"
API_RELEASE = f"https://api.github.com/repos/{OWNER}/{REPO}/releases/tags/{TAG}"
API_REF = f"https://api.github.com/repos/{OWNER}/{REPO}/git/ref/tags/{TAG}"
USER_AGENT = "VELTRIX-FOOTBALL-OPENPLAY-QUALIFIER/2.1"
DATA_DICTIONARY_URL = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{TAG_COMMIT}/DATA_DICTIONARY.md"
SCRAPED_AT_DEFINITION = b"| scraped_at | string | 100% | When the page was saved (UTC) |"
AUTHORIZATION_RECORD = Path(__file__).resolve().parents[2] / "docs" / "legal" / "openplay-whoscored-opta-authorization-2026-11-15.md"
AUTHORIZATION_URI = "https://github.com/Nexora-Apparel/veltrix-football/blob/5bd279544b0cf8a453fbae89638bac29cc51fd07/docs/legal/openplay-whoscored-opta-authorization-2026-11-15.md"

EXPECTED_ROWS = {
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
CSV_ASSETS = (
    "coverage.csv",
    "known_gaps.csv",
    "data_issues.csv",
    "qualifier_dictionary.csv",
    "checksums.json",
)
REQUIRED_COLUMNS = {
    "matches.parquet": {
        "match_id", "comp", "season", "date", "home_team_id", "away_team_id",
        "home_score", "away_score", "xg_model", "score_matches_events", "scraped_at",
    },
    "lineups.parquet": {
        "match_id", "comp", "season", "team_id", "player_id", "is_starter",
        "played", "minutes_played", "position", "date",
    },
    "player_match_stats.parquet": {
        "match_id", "comp", "season", "date", "team_id", "opponent_id",
        "player_id", "minutes_played", "goals", "assists", "xg", "npxg", "xa",
        "position", "is_starter",
    },
    "team_match_stats.parquet": {
        "match_id", "comp", "season", "team_id", "opponent_id",
        "goals_for", "goals_against", "xg", "npxg",
    },
    "shots.parquet": {
        "match_id", "comp", "season", "team_id", "player_id", "xg",
        "xg_model", "is_penalty", "is_shootout",
    },
    "coverage.csv": {
        "comp", "season", "in_v1_scope", "matches_played",
        "matches_with_events", "gaps", "coverage_pct", "matches_with_data_issues",
    },
    "data_issues.csv": {"match_id", "comp", "season", "issue"},
}


def _request(url: str, accept: str = "application/json") -> bytes:
    request = Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=60) as response:
            return response.read()
    except Exception as exc:
        # Do not include signed/temporary URLs or response bodies in logs.
        raise RuntimeError(f"DOWNLOAD_FAILED:{type(exc).__name__}") from None


def _json(url: str) -> dict:
    try:
        value = json.loads(_request(url).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("GITHUB_API_INVALID_JSON") from None
    if not isinstance(value, dict):
        raise RuntimeError("GITHUB_API_SCHEMA_INVALID")
    return value


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _truthy(value: object) -> bool:
    return str(value).strip().casefold() in {"true", "1", "yes", "y"}



def authorization_evidence() -> dict:
    """Return the hash-bound, non-commercial project authorization record."""
    if not AUTHORIZATION_RECORD.is_file():
        raise RuntimeError("OPENPLAY_AUTHORIZATION_RECORD_MISSING")
    return {
        "status": "USER_CONFIRMED_NONCOMMERCIAL_AUTHORIZATION",
        "uri": AUTHORIZATION_URI,
        "sha256": _sha256(AUTHORIZATION_RECORD.read_bytes()),
        "rights_basis": "WRITTEN_PERMISSION",
        "permitted_uses": [
            "collection", "storage", "historical_import", "internal_analysis",
            "model_training", "model_validation", "derived_research",
        ],
        "commercial_use_allowed": False,
        "raw_redistribution_allowed": False,
    }


def audit_release(output_dir: str | Path) -> dict:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    dictionary_raw = _request(DATA_DICTIONARY_URL, "text/plain")
    if SCRAPED_AT_DEFINITION not in dictionary_raw:
        raise RuntimeError("OPENPLAY_SCRAPED_AT_DOCUMENTATION_MISMATCH")
    dictionary_sha256 = _sha256(dictionary_raw)
    (root / "DATA_DICTIONARY.md").write_bytes(dictionary_raw)

    ref = _json(API_REF)
    commit_sha = (ref.get("object") or {}).get("sha")
    if ref.get("ref") != f"refs/tags/{TAG}" or commit_sha != TAG_COMMIT:
        raise RuntimeError("OPENPLAY_TAG_COMMIT_MISMATCH")

    release = _json(API_RELEASE)
    if release.get("tag_name") != TAG:
        raise RuntimeError("OPENPLAY_RELEASE_TAG_MISMATCH")
    assets = {
        item.get("name"): item
        for item in release.get("assets", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }

    selected = list(EXPECTED_ROWS) + list(CSV_ASSETS)
    asset_evidence = {}
    for name in selected:
        asset = assets.get(name)
        if not asset:
            raise RuntimeError(f"OPENPLAY_ASSET_MISSING:{name}")
        digest = asset.get("digest")
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise RuntimeError(f"OPENPLAY_ASSET_DIGEST_MISSING:{name}")
        body = _request(asset["browser_download_url"], "application/octet-stream")
        actual = _sha256(body)
        expected = digest.split(":", 1)[1].lower()
        if actual != expected:
            raise RuntimeError(f"OPENPLAY_ASSET_HASH_MISMATCH:{name}")
        (root / name).write_bytes(body)
        asset_evidence[name] = {
            "sha256": actual,
            "bytes": len(body),
            "release_asset_id": asset.get("id"),
            "release_digest": digest,
        }

    db = duckdb.connect(database=":memory:")
    parquet_evidence = {}
    schema_failures = []
    for name, expected_rows in EXPECTED_ROWS.items():
        path = (root / name).as_posix()
        safe_path = path.replace("'", "''")
        count = db.execute(f"SELECT COUNT(*) FROM read_parquet('{safe_path}')").fetchone()[0]
        columns = [row[0] for row in db.execute(f"DESCRIBE SELECT * FROM read_parquet('{safe_path}')").fetchall()]
        missing = sorted(REQUIRED_COLUMNS.get(name, set()) - set(columns))
        if count != expected_rows or missing:
            schema_failures.append({
                "asset": name,
                "expected_rows": expected_rows,
                "actual_rows": count,
                "missing_columns": missing,
            })
        parquet_evidence[name] = {
            "rows": count,
            "columns": columns,
            "expected_rows": expected_rows,
            "row_count_matches_release_dictionary": count == expected_rows,
            "missing_required_columns": missing,
        }

    matches_path = (root / "matches.parquet").as_posix().replace("'", "''")
    scrape_row = db.execute(f"""
        SELECT
            COUNT(*) AS match_rows,
            COUNT(scraped_at) AS non_null_scraped_at,
            COUNT(TRY_CAST(scraped_at AS TIMESTAMPTZ)) AS parseable_scraped_at,
            COUNT(*) FILTER (WHERE TRY_CAST(scraped_at AS TIMESTAMPTZ) IS NULL) AS unparseable_scraped_at,
            MIN(TRY_CAST(scraped_at AS TIMESTAMPTZ)) AS first_page_saved_at_utc,
            MAX(TRY_CAST(scraped_at AS TIMESTAMPTZ)) AS last_page_saved_at_utc,
            COUNT(DISTINCT match_id) AS unique_match_ids,
            COUNT(*) FILTER (
                WHERE TRY_CAST(scraped_at AS TIMESTAMPTZ) >= CAST(date AS TIMESTAMPTZ) + INTERVAL '2 days'
            ) AS safely_after_match_date,
            COUNT(*) FILTER (
                WHERE TRY_CAST(scraped_at AS TIMESTAMPTZ) <= CURRENT_TIMESTAMP
            ) AS not_future_scrape_timestamps
        FROM read_parquet('{matches_path}')
    """).fetchone()
    scrape_timestamp_audit = {
        "match_rows": scrape_row[0],
        "non_null_scraped_at": scrape_row[1],
        "parseable_scraped_at": scrape_row[2],
        "unparseable_scraped_at": scrape_row[3],
        "first_page_saved_at_utc": str(scrape_row[4]) if scrape_row[4] is not None else None,
        "last_page_saved_at_utc": str(scrape_row[5]) if scrape_row[5] is not None else None,
        "unique_match_ids": scrape_row[6],
        "safely_after_match_date": scrape_row[7],
        "not_future_scrape_timestamps": scrape_row[8],
        "data_dictionary_semantics": "When the page was saved (UTC)",
        "data_dictionary_documented_definition_verified": True,
        "data_dictionary_url": DATA_DICTIONARY_URL,
        "timestamp_guarantee_evidence_id": "openplay-data-v0.1.0:DATA_DICTIONARY.md#matches.scraped_at",
        "timestamp_guarantee_evidence_sha256": dictionary_sha256,
        "temporal_status": (
            "CAPTURE_TIMESTAMP_CANDIDATE"
            if scrape_row[0] == scrape_row[1] == scrape_row[2] == scrape_row[6] == scrape_row[7] == scrape_row[8]
            else "TIMESTAMP_COVERAGE_INCOMPLETE"
        ),
        "historical_pit_admitted": False,
    }

    coverage_rows = _csv_rows(root / "coverage.csv")
    issue_rows = _csv_rows(root / "data_issues.csv")
    gap_rows = _csv_rows(root / "known_gaps.csv")
    qualifier_rows = _csv_rows(root / "qualifier_dictionary.csv")
    v1_coverage = [row for row in coverage_rows if _truthy(row.get("in_v1_scope"))]
    issue_counts: dict[str, int] = {}
    for row in issue_rows:
        issue = row.get("issue") or "unknown"
        issue_counts[issue] = issue_counts.get(issue, 0) + 1

    coverage_summary = []
    for row in v1_coverage:
        coverage_summary.append({
            "competition_code": row.get("comp"),
            "season": row.get("season"),
            "matches_played": int(row.get("matches_played") or 0),
            "matches_with_events": int(row.get("matches_with_events") or 0),
            "gaps": int(row.get("gaps") or 0),
            "coverage_pct": float(row.get("coverage_pct") or 0),
            "matches_with_data_issues": int(row.get("matches_with_data_issues") or 0),
        })

    rights_evidence = authorization_evidence()
    report = {
        "schema_version": "openplay-release-qualification-v2",
        "status": "FAILED" if schema_failures else "PASS_NONCOMMERCIAL_SOURCE_QUALIFIED",
        "source_acceptance": not bool(schema_failures),
        "production_approved": False,
        "training_approved": not bool(schema_failures),
        "rights_review_required": False,
        "non_commercial_only": True,
        "commercial_use_allowed": False,
        "monetisation_prohibited": True,
        "authorization_evidence": rights_evidence,
        "read_only": True,
        "database_writes": 0,
        "prediction_code_access": False,
        "source": {
            "repository": f"https://github.com/{OWNER}/{REPO}",
            "release_tag": TAG,
            "tag_commit_sha": commit_sha,
            "license_declared_by_release": "CC BY 4.0",
            "required_attribution": "openplay (Noah Bair), https://github.com/nlbair/openplay",
            "upstream_provenance_disclosed_by_maintainer": "Public match pages on WhoScored.com displaying Opta / Stats Perform data",
            "rights_note": (
                "The project owner confirms authorization covering OpenPlay and its underlying "
                "WhoScored / Opta data for VELTRIX FOOTBALL use, subject to a strict non-commercial "
                "condition. Monetisation and commercial use are prohibited. Preserve attribution "
                "and provenance. The authorization record is hashed in authorization_evidence."
            ),
        },
        "assets": asset_evidence,
        "parquet_tables": parquet_evidence,
        "csv_counts": {
            "coverage_rows": len(coverage_rows),
            "v1_scope_coverage_rows": len(v1_coverage),
            "known_gap_rows": len(gap_rows),
            "data_issue_rows": len(issue_rows),
            "qualifier_dictionary_rows": len(qualifier_rows),
            "data_issues_by_type": issue_counts,
        },
        "v1_scope_coverage": coverage_summary,
        "scrape_timestamp_audit": scrape_timestamp_audit,
        "schema_failures": schema_failures,
        "limitations": [
            "This is a static snapshot through 2025/26; it is not a current-season 2026/27 feed.",
            "Competition coverage is uneven; each competition-season must be qualified independently.",
            "Known gaps and data issues must be excluded or handled explicitly in training/evaluation.",
            "The OpenPlay xG values are from the maintainer's own xG model; preserve its model identity.",
            "The dataset is not a confirmed injury feed or a live lineup feed.",
            "The release is a preview (v0.1.0); schema and coverage can change in later versions.",
        ],
    }
    db.close()
    return report


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openplay-audit")
    try:
        report = audit_release(output)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"OPENPLAY_QUALIFICATION: FAILED ({str(exc)[:160]})")
        return 1
    output.mkdir(parents=True, exist_ok=True)
    (output / "openplay_qualification_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"OPENPLAY_QUALIFICATION: {report['status']}; "
        f"tables={len(report['parquet_tables'])}; "
        f"player_match_rows={report['parquet_tables']['player_match_stats.parquet']['rows']}; "
        f"lineup_rows={report['parquet_tables']['lineups.parquet']['rows']}; "
        f"shot_rows={report['parquet_tables']['shots.parquet']['rows']}; "
        f"non_commercial_only=true"
    )
    print("RIGHTS_REVIEW_REQUIRED: false; COMMERCIAL_USE_ALLOWED: false")
    print("TRAINING_APPROVED_NONCOMMERCIAL: " + str(report["training_approved"]).lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
