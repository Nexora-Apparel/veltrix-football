#!/usr/bin/env python3
"""Assemble a complete, non-overlapping offline 5Dollar history archive."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output", default="fivedollar_historical_archive.json")
    parser.add_argument("reports", nargs="+", help="Previously downloaded batch JSON reports")
    args = parser.parse_args()

    from app.provider_historical_archive import (
        HistoricalArchiveError,
        assemble_fivedollar_history_archive,
        validate_fivedollar_history_archive,
    )

    try:
        reports = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.reports]
        archive = assemble_fivedollar_history_archive(
            reports=reports,
            target_start_date=args.start_date,
            target_end_date=args.end_date,
        )
        validation = validate_fivedollar_history_archive(archive)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(archive, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            "ARCHIVE_RESULT: PASS; "
            f"batches={validation['batch_count']}; "
            f"accepted={validation['accepted_count']}; "
            f"database_writes=0; imports=0"
        )
        print(f"ARCHIVE_FILE: {output}")
        print(f"ARCHIVE_SHA256: {validation['archive_sha256']}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ARCHIVE_RESULT: REVIEW_REQUIRED ({type(exc).__name__}: {str(exc)[:160]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
