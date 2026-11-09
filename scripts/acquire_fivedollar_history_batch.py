#!/usr/bin/env python3
"""Manual read-only historical 5Dollar batch acquisition for signed competitions."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXPECTED_COMPETITIONS = [
    "3405541143", "3614399544", "4160026622", "4212821298", "686337048",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, help="Inclusive Africa/Lagos date")
    parser.add_argument("--end-date", required=True, help="Inclusive Africa/Lagos date; max 7 days")
    parser.add_argument("--max-requests", type=int, default=15)
    parser.add_argument("--max-pages-per-competition", type=int, default=3)
    parser.add_argument("--registry", default="data/provider_qualification_registry.json")
    parser.add_argument("--output", default="fivedollar_history_batch.json")
    args = parser.parse_args()

    from app.daily_fixture_selection_artifact import qualified_sources_from_registry
    from app.provider_acquisition_adapters import acquire_fivedollar_history_batch
    from app.provider_acquisition_artifact import validate_acquisition_report
    from app.provider_adapters import FiveDollarFootballClient

    try:
        start, end = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
        today_lagos = datetime.now(ZoneInfo("Africa/Lagos")).date()
        if end >= today_lagos:
            raise ValueError("historical_end_date_must_be_before_today_lagos")
        if start < today_lagos - timedelta(days=89):
            raise ValueError("start_date_outside_documented_90_day_history_window")
        if end < start or (end - start).days > 6:
            raise ValueError("history_batch_must_cover_one_to_seven_days")
        if not 1 <= args.max_requests <= 20:
            raise ValueError("max_requests_must_be_between_1_and_20")
        if not 1 <= args.max_pages_per_competition <= 3:
            raise ValueError("max_pages_per_competition_must_be_between_1_and_3")
        registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
        qualified = qualified_sources_from_registry(registry)
        competition_ids = qualified.get("fivedollar", [])
        if competition_ids != EXPECTED_COMPETITIONS:
            raise ValueError("signed_fivedollar_registry_scope_mismatch")
        if not os.getenv("VELTRIX_QUALIFICATION_ATTESTATION_KEY"):
            raise ValueError("qualification_attestation_key_missing")
        client = FiveDollarFootballClient()
        if not client.api_key:
            print("ACQUISITION_RESULT: BLOCKED_MISSING_SECRET (FIVEDOLLARFOOTBALL_API_KEY)")
            return 2
        retrieved = datetime.now(timezone.utc).replace(microsecond=0)
        run_id = f"fivedollar-history-{start.isoformat()}-{end.isoformat()}-{retrieved.strftime('%Y%m%dT%H%M%SZ')}"
        result = acquire_fivedollar_history_batch(
            client=client,
            competition_ids=competition_ids,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            run_id=run_id,
            max_requests=args.max_requests,
            max_pages_per_competition=args.max_pages_per_competition,
            retrieved_at=retrieved.isoformat().replace("+00:00", "Z"),
        )
        integrity = validate_acquisition_report(result["report"])
        if not integrity["valid"] or not result["acceptance_pass"]:
            raise ValueError("historical_batch_quality_or_integrity_failed")
        if result["report"]["competition_scope"] != EXPECTED_COMPETITIONS:
            raise ValueError("historical_batch_competition_scope_mismatch")
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result["report"], indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            "ACQUISITION_RESULT: PASS; "
            f"accepted={integrity['accepted_count']}; "
            f"quarantined={integrity['quarantined_count']}; "
            f"requests={result['report']['request_budget']['actual_requests']}; "
            "database_writes=0; imports=0; canonical_merges=0"
        )
        print(f"ARTIFACT_INTEGRITY: PASS")
        print(f"REPORT_FILE: {output}")
        print(f"REPORT_SHA256: {result['report']['report_sha256']}")
        return 0
    except (RuntimeError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"ACQUISITION_RESULT: REVIEW_REQUIRED ({type(exc).__name__}: {str(exc)[:160]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
