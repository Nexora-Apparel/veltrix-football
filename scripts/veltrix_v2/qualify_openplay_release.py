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
USER_AGENT = "VELTRIX-FOOTBALL-OPENPLAY-READONLY-QUALIFIER/1.0"

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


def audit_release(output_dir: str | Path) -> dict:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

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
        count = db.execute("SELECT COUNT(*) FROM read_parquet(?)", [path]).fetchone()[0]
        columns = [row[0] for row in db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [path]).fetchall()]
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

    report = {
        "schema_version": "openplay-release-qualification-v1",
        "status": "REVIEW_REQUIRED" if schema_failures else "STRUCTURE_AND_HASHES_PASS",
        "source_acceptance": False,
        "production_approved": False,
        "training_approved": False,
        "rights_review_required": True,
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
                "The release declares CC BY 4.0 and permits commercial reuse with attribution. "
                "Because the maintainer identifies WhoScored / Opta as the upstream data origin, "
                "VELTRIX must complete a documented upstream-rights review before production or "
                "commercial model-training approval."
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
        f"rights_review_required=true"
    )
    print("PRODUCTION_APPROVED: false; TRAINING_APPROVED: false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
