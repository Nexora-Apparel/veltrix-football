#!/usr/bin/env python3
"""Profile coverage and integrity of a validated historical archive."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", help="Validated historical archive JSON")
    parser.add_argument("--output", default="fivedollar_historical_coverage.json")
    args = parser.parse_args()

    from app.provider_historical_coverage import (
        HistoricalCoverageError,
        profile_fivedollar_historical_coverage,
        validate_fivedollar_coverage_profile,
    )

    try:
        archive = json.loads(Path(args.archive).read_text(encoding="utf-8"))
        report = profile_fivedollar_historical_coverage(archive)
        result = validate_fivedollar_coverage_profile(report)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            "COVERAGE_PROFILE: PASS; "
            f"matches={result['accepted_finished_matches']}; "
            f"competitions={result['competition_count']}; "
            "training_ready=false; database_writes=0"
        )
        print(f"COVERAGE_FILE: {output}")
        print(f"COVERAGE_SHA256: {result['report_sha256']}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"COVERAGE_PROFILE: REVIEW_REQUIRED ({type(exc).__name__}: {str(exc)[:160]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
