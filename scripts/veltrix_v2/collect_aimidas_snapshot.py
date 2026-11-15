#!/usr/bin/env python3
"""Fetch a pinned, no-key AI Midas CSV snapshot into an artifact-only pack.

No database, provider API, model, or production operations are performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

REPOSITORY = "aimidas1/aimidas1"
SOURCE_COMMIT = "29baca362a34ce5dcd3924b07ec9c7d5139d83fc"
APPROVAL_ID = "approval-aimidas-football-data-noncommercial-2026-11-15"
USER_AGENT = "VELTRIX-FOOTBALL-2.0-AIMidas-ReadOnly-Snapshot/1.0"
MAX_FILE_BYTES = 4_000_000
MAX_TOTAL_BYTES = 20_000_000
SCHEMA_VERSION = "veltrix-aimidas-snapshot-pack-v1"


@dataclass(frozen=True)
class FileSpec:
    path: str
    git_blob_sha: str
    expected_bytes: int
    expected_rows: int
    date_min: str
    date_max: str
    kind: str
    expected_avg_1x2: int = 0
    expected_distinct_matches: int = 0
    expected_distinct_teams: int = 0


SOURCE_FILES = (
    FileSpec("csv/past-seasons/leagues/Brasileirão_Série_A_2016-2024.csv", "5a42af579f336938eaad8ab08e60bd83ca0ed66d", 1845744, 3419, "2016-05-14 19:00:00", "2024-12-08 19:00:00", "historical_match_csv", 3379),
    FileSpec("csv/past-seasons/leagues/England_Premier_League_2016-2025.csv", "92bebb1ba8471fdd404ea48193fe2cacbe51ccdb", 1797374, 3420, "2016-08-13 11:30:00", "2025-05-25 15:00:00", "historical_match_csv", 3416),
    FileSpec("csv/past-seasons/leagues/France_Ligue_1_2016-2025.csv", "666555e3e60a3b59ef720ecd52557ac0522a0038", 1570415, 3171, "2016-08-12 18:00:00", "2025-05-17 19:00:00", "historical_match_csv", 3169),
    FileSpec("csv/past-seasons/leagues/Germany_Bundesliga_2016-2025.csv", "f39c8fbedcea2d1dc0771d844657f437a76663d6", 1384173, 2754, "2016-08-26 18:30:00", "2025-05-17 13:30:00", "historical_match_csv", 2667),
    FileSpec("csv/past-seasons/leagues/Italy_Serie_A_2016-2025.csv", "56478b8dc15ec0af0a340253889e10dbf2f51283", 1743197, 3421, "2016-08-20 16:00:00", "2025-05-25 18:45:00", "historical_match_csv", 3420),
    FileSpec("csv/past-seasons/leagues/Spain_La_Liga_2016-2025.csv", "e0dfc6f2129df1c857022b16fe1693811f8870a1", 1779859, 3420, "2016-08-19 18:45:00", "2025-05-25 19:00:00", "historical_match_csv", 3403),
    FileSpec("csv/matches/leagues/Brasileirão_Série_A_2025-2026.csv", "0779b8d3d1a626ae2dc4e2e9b30debc0f1e4ed89", 217224, 380, "2025-03-29 21:30:00", "2025-12-07 19:00:00", "season_match_csv", 380),
    FileSpec("csv/matches/leagues/Brasileirão_Série_A_2026.csv", "a3fffa1187ad0a1745c11a77f57e1d632168f768", 91448, 177, "2026-01-28 22:00:00", "2026-05-31 23:30:00", "season_match_csv", 177),
    FileSpec("csv/matches/leagues/England_Premier_League_2025-2026.csv", "3589069f19f804efcb7bc8b97dffb412ea1d4ded", 214467, 380, "2025-08-15 19:00:00", "2026-05-24 15:00:00", "season_match_csv", 379),
    FileSpec("csv/matches/leagues/France_Ligue_1_2025-2026.csv", "4b3b3db181dcb8e6a0249ded8b7cfe7cd8b8c9e7", 157954, 305, "2025-08-15 18:45:00", "2026-05-17 19:00:00", "season_match_csv", 305),
    FileSpec("csv/matches/leagues/Germany_Bundesliga_2025-2026.csv", "e1674246aa2f9d6f2006d46887e9ee69ee7eaec3", 172263, 306, "2025-08-22 18:30:00", "2026-05-16 13:30:00", "season_match_csv", 306),
    FileSpec("csv/matches/leagues/Italy_Serie_A_2025-2026.csv", "ae6ee88284cf474b226a39561d13008fa07d3368", 216364, 380, "2025-08-23 16:30:00", "2026-05-24 19:45:00", "season_match_csv", 380),
    FileSpec("csv/matches/leagues/Spain_La_Liga_2025-2026.csv", "076fea41135d65ad8fee7993b167bc7ddce7c1bf", 216720, 380, "2025-08-15 17:00:00", "2026-05-24 19:00:00", "season_match_csv", 380),
    FileSpec("advanced stats/Brazil Serie B 2026.csv", "b6bdb94c053d2149e6232fb100e1f158e46e4533", 192284, 738, "2026-03-21", "2026-11-08", "advanced_team_match_csv", 0, 369, 20),
)


def git_blob_sha1(raw: bytes) -> str:
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def parse_and_audit(raw: bytes, spec: FileSpec) -> dict:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("CSV_NOT_UTF8") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = reader.fieldnames
    if not fields:
        raise ValueError("CSV_HEADER_MISSING")
    rows = [row for row in reader if any((value or "").strip() for value in row.values())]
    date_field = "Date" if "Date" in fields else "date" if "date" in fields else None
    if date_field is None:
        raise ValueError("CSV_DATE_FIELD_MISSING")
    dates = sorted((row.get(date_field) or "").strip() for row in rows if (row.get(date_field) or "").strip())
    if not dates:
        raise ValueError("CSV_DATE_VALUES_MISSING")
    odds_fields = ("avg_odds_ft_1", "avg_odds_ft_x", "avg_odds_ft_2")
    valid_odds = 0
    if all(field in fields for field in odds_fields):
        for row in rows:
            try:
                values = [float(row[field]) for field in odds_fields]
            except (TypeError, ValueError):
                continue
            if all(value == value and 1 < value < 1000 for value in values):
                valid_odds += 1
    distinct_matches = len({(row.get("Match") or "").strip() for row in rows if (row.get("Match") or "").strip()})
    distinct_teams = len({(row.get("Team") or "").strip() for row in rows if (row.get("Team") or "").strip()})
    summary = {
        "path": spec.path,
        "kind": spec.kind,
        "row_count": len(rows),
        "column_count": len(fields),
        "date_field": date_field,
        "date_min": dates[0],
        "date_max": dates[-1],
        "has_average_1x2_fields": all(field in fields for field in odds_fields),
        "valid_average_1x2_rows": valid_odds,
        "distinct_match_labels": distinct_matches,
        "distinct_teams": distinct_teams,
        "has_prematch_named_fields": any("prematch" in field.lower() or "pre_match" in field.lower() for field in fields),
        "has_timezone_or_source_publication_timestamp": False,
        "point_in_time_certifiable": False,
    }
    expected = {
        "row_count": spec.expected_rows,
        "date_min": spec.date_min,
        "date_max": spec.date_max,
        "valid_average_1x2_rows": spec.expected_avg_1x2,
    }
    if spec.expected_distinct_matches:
        expected["distinct_match_labels"] = spec.expected_distinct_matches
    if spec.expected_distinct_teams:
        expected["distinct_teams"] = spec.expected_distinct_teams
    for key, value in expected.items():
        if summary[key] != value:
            raise ValueError(f"CSV_AUDIT_MISMATCH:{spec.path}:{key}:{summary[key]}!={value}")
    return summary


def fetch_raw(path: str) -> bytes:
    encoded = quote(path, safe="/")
    url = f"https://raw.githubusercontent.com/{REPOSITORY}/{SOURCE_COMMIT}/{encoded}"
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv"})
    with urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"SOURCE_HTTP_STATUS:{response.status}:{path}")
        raw = response.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise RuntimeError(f"SOURCE_FILE_TOO_LARGE:{path}")
    return raw


def collect_pack(output_dir: Path, *, fetcher=fetch_raw, generated_at: datetime | None = None,
                 specs: tuple[FileSpec, ...] = SOURCE_FILES) -> dict:
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("GENERATED_AT_MUST_BE_TIMEZONE_AWARE")
    if len(specs) != len({spec.path for spec in specs}):
        raise ValueError("SOURCE_FILE_ALLOWLIST_DUPLICATE")
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshots_dir = output_dir / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    file_records = []
    total_bytes = 0
    for spec in specs:
        raw = fetcher(spec.path)
        if not isinstance(raw, bytes) or not raw:
            raise RuntimeError(f"SOURCE_FILE_EMPTY:{spec.path}")
        if len(raw) != spec.expected_bytes:
            raise RuntimeError(f"SOURCE_BYTE_SIZE_MISMATCH:{spec.path}:{len(raw)}!={spec.expected_bytes}")
        blob_sha = git_blob_sha1(raw)
        if blob_sha != spec.git_blob_sha:
            raise RuntimeError(f"SOURCE_GIT_BLOB_SHA_MISMATCH:{spec.path}")
        summary = parse_and_audit(raw, spec)
        relative = Path("snapshots") / spec.path
        destination = output_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_BYTES:
            raise RuntimeError("SOURCE_TOTAL_BYTE_BUDGET_EXCEEDED")
        file_records.append({
            **summary,
            "expected_bytes": spec.expected_bytes,
            "actual_bytes": len(raw),
            "git_blob_sha1": blob_sha,
            "sha256": sha256(raw),
            "stored_path": relative.as_posix(),
        })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_repository": REPOSITORY,
        "source_commit_sha": SOURCE_COMMIT,
        "rights_approval_id": APPROVAL_ID,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "files_requested": len(specs),
        "files_captured": len(file_records),
        "total_bytes": total_bytes,
        "files": file_records,
        "database_written": False,
        "production_written": False,
        "model_admitted": False,
        "predictions_changed": False,
        "point_in_time_certifiable": False,
        "raw_redistribution_allowed": False,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    manifest = collect_pack(Path(args.output_dir))
    print(json.dumps({
        "status": "PASS",
        "files_captured": manifest["files_captured"],
        "total_bytes": manifest["total_bytes"],
        "database_written": False,
        "production_written": False,
        "model_admitted": False,
        "predictions_changed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
