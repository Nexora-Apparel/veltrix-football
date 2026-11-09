#!/usr/bin/env python3
"""Manual, read-only 5Dollar day acquisition; emits sanitized JSON only."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Africa/Lagos calendar date (YYYY-MM-DD)")
    parser.add_argument("--output", default="fivedollar_fixture_acquisition.json")
    parser.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()

    from app.provider_acquisition_adapters import acquire_fivedollar_day
    from app.provider_adapters import FiveDollarFootballClient

    retrieved = datetime.now(timezone.utc).replace(microsecond=0)
    run_id = f"fivedollar-{args.date}-{retrieved.strftime('%Y%m%dT%H%M%SZ')}"
    client = FiveDollarFootballClient()
    if not client.api_key:
        print("ACQUISITION_RESULT: BLOCKED_MISSING_SECRET (FIVEDOLLARFOOTBALL_API_KEY)")
        return 2

    try:
        result = acquire_fivedollar_day(
            client=client,
            day=args.date,
            run_id=run_id,
            retrieved_at=retrieved.isoformat().replace("+00:00", "Z"),
            max_pages=args.max_pages,
        )
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"ACQUISITION_RESULT: FAILED ({type(exc).__name__}: {str(exc)[:160]})")
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result["report"], indent=2, sort_keys=True, ensure_ascii=False) + "\\n",
        encoding="utf-8",
    )
    print(
        "ACQUISITION_RESULT: "
        f'{"PASS" if result["acceptance_pass"] else "REVIEW_REQUIRED"}; '
        f'accepted={result["batch"]["accepted_count"]}; '
        f'quarantined={result["batch"]["quarantined_count"]}; '
        f'pages={result["report"]["request_budget"].get("calls_made", 0)}; '
        f"database_writes=0; imports=0"
    )
    print(f"REPORT_FILE: {output}")
    print(f'REPORT_SHA256: {result["report"]["report_sha256"]}')
    return 0 if result["acceptance_pass"] else 3


if __name__ == "__main__":
    sys.exit(main())
