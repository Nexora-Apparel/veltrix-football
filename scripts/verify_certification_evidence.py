"""Run raw-row VELTRIX certification diagnostics against a hash-bound evidence bundle."""
from __future__ import annotations

import argparse
import json
import sys

from app.certification_metrics import recompute_raw_certification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Path to the evidence manifest JSON")
    args = parser.parse_args()
    try:
        result = recompute_raw_certification(args.manifest)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Raw certification audit failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    # A diagnostic pass is not a source-attested release certificate.
    return 0 if result["statistical_status"] == "RAW_EVIDENCE_THRESHOLDS_MET" else 1


if __name__ == "__main__":
    raise SystemExit(main())
