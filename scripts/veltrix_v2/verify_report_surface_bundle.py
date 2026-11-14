#!/usr/bin/env python3
"""Verify all immutable V2 report surface artifacts without publishing or sending."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from veltrix_v2.reporting.artifact_bundle import load_report_surface_bundle


def verify(bundle_dir: Path, report_id: str) -> dict[str, object]:
    bundle = load_report_surface_bundle(bundle_dir, report_id)
    return {
        "status": "REPORT_SURFACE_BUNDLE_VERIFIED",
        "report_id": bundle.identity.report_id,
        "report_sha256": bundle.identity.report_sha256,
        "as_of_date": bundle.identity.as_of_date,
        "surfaces_verified": ["canonical", "scheduled", "telegram", "website"],
        "fixture_count": len(bundle.canonical_report["predictions"]),
        "side_effects": {
            "provider_requests": 0,
            "database_writes": 0,
            "telegram_messages": 0,
            "schedule_activation": 0,
            "publications": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--report-id", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle_dir, args.report_id), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
