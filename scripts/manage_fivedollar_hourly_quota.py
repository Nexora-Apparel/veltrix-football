#!/usr/bin/env python3
"""Reserve or settle the persistent rolling-hour 5Dollar request quota."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    reserve = sub.add_parser("reserve")
    reserve.add_argument("--ledger", required=True)
    reserve.add_argument("--run-id", required=True)
    reserve.add_argument("--reserved-requests", type=int, required=True)
    settle = sub.add_parser("settle")
    settle.add_argument("--ledger", required=True)
    settle.add_argument("--run-id", required=True)
    settle.add_argument("--report", required=True)
    args = parser.parse_args()

    from app.provider_hourly_quota_ledger import (
        HourlyQuotaError,
        reserve_hourly_quota,
        settle_hourly_quota,
    )

    try:
        if args.command == "reserve":
            result = reserve_hourly_quota(
                ledger_path=args.ledger,
                run_id=args.run_id,
                reserved_requests=args.reserved_requests,
            )
        else:
            from app.provider_acquisition_artifact import validate_fivedollar_history_batch_report
            report = json.loads(Path(args.report).read_text(encoding="utf-8"))
            integrity = validate_fivedollar_history_batch_report(report, require_acceptance=False)
            if not integrity["valid"]:
                raise HourlyQuotaError("historical_report_integrity_not_valid")
            result = settle_hourly_quota(
                ledger_path=args.ledger,
                run_id=args.run_id,
                actual_requests=integrity["actual_requests"],
            )
        print(json.dumps({"hourly_quota": "PASS", **result}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"HOURLY_QUOTA: BLOCKED ({type(exc).__name__}: {str(exc)[:160]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
