"""Audit row-level OpenPlay feature tables and inherit documented page-save time.

This is a read-only extraction audit. It does not admit historical backtests:
all observations retain the source page-save timestamp and actual VELTRIX
recording time, and are usable only at later prospective cutoffs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TABLES = {
    "player_match_stats.parquet": {
        "key": ["match_id", "team_id", "player_id"],
    },
    "lineups.parquet": {
        "key": ["match_id", "team_id", "player_id"],
    },
    "shots.parquet": {
        "key": ["match_id", "event_id", "event_id_sub"],
    },
    "formations.parquet": {
        "key": ["match_id", "team_id", "period", "start_expanded_minute"],
    },
    "cards.parquet": {
        "key": ["match_id", "event_id"],
    },
    "team_match_stats.parquet": {
        "key": ["match_id", "team_id"],
    },
}

EXPECTED_MATCH_ROWS = 26547
TIMESTAMP_EVIDENCE_ID = "openplay-data-v0.1.0:DATA_DICTIONARY.md#matches.scraped_at"
TIMESTAMP_EVIDENCE_SHA256 = "24a1037a948afa1759e3bc2babeb8b17b9e1e2dc3c8a8beea2e18f9b5b671279"


def audit(input_dir: str | Path) -> dict:
    import duckdb

    root = Path(input_dir)
    db = duckdb.connect(database=":memory:")
    try:
        matches_path = str(root / "matches.parquet")
        match_stats = db.execute("""
            SELECT count(*) AS rows,
                   count(DISTINCT match_id) AS unique_match_ids,
                   count(*) FILTER (WHERE try_cast(scraped_at AS TIMESTAMPTZ) IS NOT NULL) AS timestamped,
                   min(try_cast(scraped_at AS TIMESTAMPTZ)) AS first_saved,
                   max(try_cast(scraped_at AS TIMESTAMPTZ)) AS last_saved
            FROM read_parquet(?)
        """, [matches_path]).fetchone()
        if match_stats[0] != EXPECTED_MATCH_ROWS or match_stats[1] != EXPECTED_MATCH_ROWS or match_stats[2] != EXPECTED_MATCH_ROWS:
            raise RuntimeError("OPENPLAY_FEATURE_MATCH_TIMESTAMP_BASELINE_MISMATCH")

        reports = {}
        for filename, spec in TABLES.items():
            path = str(root / filename)
            columns = db.execute("DESCRIBE SELECT * FROM read_parquet(?)", [path]).fetchall()
            available = {row[0] for row in columns}
            required = set(spec["key"]) | {"match_id"}
            if not required.issubset(available):
                raise RuntimeError("OPENPLAY_FEATURE_REQUIRED_COLUMNS_MISSING:" + filename)
            key_sql = ", ".join(f"f.\"{name}\"" for name in spec["key"])
            duplicate_sql = f"""
                SELECT count(*) FROM (
                    SELECT {key_sql}, count(*) AS n
                    FROM read_parquet(?) f GROUP BY {key_sql} HAVING count(*) > 1
                ) d
            """
            duplicate_keys = db.execute(duplicate_sql, [path]).fetchone()[0]
            row = db.execute("""
                SELECT count(*) AS rows,
                       count(*) FILTER (WHERE m.match_id IS NOT NULL) AS matched_rows,
                       count(*) FILTER (WHERE m.match_id IS NOT NULL
                           AND try_cast(m.scraped_at AS TIMESTAMPTZ) IS NOT NULL) AS timestamped_rows,
                       count(DISTINCT f.match_id) AS distinct_matches,
                       count(*) FILTER (WHERE m.match_id IS NULL) AS orphan_rows
                FROM read_parquet(?) f
                LEFT JOIN read_parquet(?) m USING(match_id)
            """, [path, matches_path]).fetchone()
            reports[filename] = {
                "rows": row[0],
                "matched_to_documented_match_page": row[1],
                "inherited_page_save_timestamp_rows": row[2],
                "distinct_match_ids": row[3],
                "orphan_rows": row[4],
                "duplicate_natural_keys": duplicate_keys,
                "natural_key": spec["key"],
                "source_timestamp": "matches.scraped_at (documented UTC page-save time)",
                "temporal_admission": "only cutoffs after actual VELTRIX recorded_at",
                "xg_model_join": filename in {"shots.parquet", "player_match_stats.parquet", "team_match_stats.parquet"},
            }
        failed = [
            name for name, row in reports.items()
            if row["rows"] != row["matched_to_documented_match_page"]
            or row["rows"] != row["inherited_page_save_timestamp_rows"]
            or row["orphan_rows"] != 0
            or row["duplicate_natural_keys"] != 0
        ]
        if failed:
            raise RuntimeError("OPENPLAY_FEATURE_ROW_AUDIT_FAILED:" + ",".join(failed))
        return {
            "status": "PASS_ROW_LEVEL_PAGE_TIMESTAMP_INHERITANCE",
            "commercial_use_allowed": False,
            "monetisation_prohibited": True,
            "timestamp_evidence_id": TIMESTAMP_EVIDENCE_ID,
            "timestamp_evidence_sha256": TIMESTAMP_EVIDENCE_SHA256,
            "match_rows": match_stats[0],
            "unique_match_ids": match_stats[1],
            "first_page_saved_at_utc": str(match_stats[3]),
            "last_page_saved_at_utc": str(match_stats[4]),
            "veltrix_recorded_at": "preserved separately on source_observations; never backdated",
            "historical_cutoffs_before_veltrix_import_eligible": False,
            "feature_tables": reports,
            "rows_total": sum(row["rows"] for row in reports.values()),
        }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", default="openplay-feature-temporal-audit.json")
    args = parser.parse_args()
    result = audit(args.input_dir)
    Path(args.output).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
