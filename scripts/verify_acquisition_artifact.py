#!/usr/bin/env python3
"""Offline integrity verifier for a sanitized Veltrix acquisition report."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.provider_acquisition_artifact import (
    ArtifactIntegrityError,
    validate_acquisition_report_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="Path to a sanitized acquisition JSON report")
    args = parser.parse_args()
    try:
        result = validate_acquisition_report_file(args.report)
    except ArtifactIntegrityError as exc:
        print(f"ARTIFACT_INTEGRITY: FAIL ({str(exc)[:180]})")
        return 1
    print(
        "ARTIFACT_INTEGRITY: PASS; "
        f"accepted={result['accepted_count']}; "
        f"quarantined={result['quarantined_count']}; "
        f"input={result['input_count']}; "
        f"acceptance_pass={str(result['acceptance_pass']).lower()}"
    )
    print(f"REPORT_SHA256: {result['report_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
