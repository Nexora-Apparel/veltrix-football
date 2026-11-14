#!/usr/bin/env python3
"""Verify a portable V2 report surface bundle without publishing or sending."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from veltrix_v2.reporting.artifact_bundle import parse_portable_report_surface_bundle


def verify(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    bundle = parse_portable_report_surface_bundle(raw)
    return {
        "status": "PORTABLE_REPORT_SURFACE_BUNDLE_VERIFIED",
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
    parser.add_argument("--portable-bundle", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.portable_bundle), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
