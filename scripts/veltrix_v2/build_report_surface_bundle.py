#!/usr/bin/env python3
"""Create immutable V2 report artifacts for website, scheduler and Telegram.

This command performs local file operations only. It does not publish, deploy,
send Telegram messages, access providers or activate a schedule.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from veltrix_v2.reporting.artifact_bundle import (
    build_report_surface_bundle,
    persist_report_surface_bundle,
)


def build(input_report: Path, output_dir: Path) -> dict[str, object]:
    raw = input_report.read_bytes()
    if len(raw) > 8_000_000:
        raise ValueError("INPUT_REPORT_TOO_LARGE")
    report = json.loads(raw.decode("utf-8"))
    bundle = build_report_surface_bundle(report)
    paths = persist_report_surface_bundle(bundle, output_dir)
    return {
        "status": "ARTIFACT_BUNDLE_READY",
        "report_id": bundle.identity.report_id,
        "report_sha256": bundle.identity.report_sha256,
        "as_of_date": bundle.identity.as_of_date,
        "fixture_count": len(bundle.canonical_report["predictions"]),
        "outputs": {name: str(path) for name, path in paths.items()},
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
    parser.add_argument("--input-report", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.input_report, args.output_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
