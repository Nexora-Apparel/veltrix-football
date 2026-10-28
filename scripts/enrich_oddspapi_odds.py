"""Optional non-blocking OddsPapi enrichment for the daily Veltrix report."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from app.oddspapi_odds import OddsPapiClient, OddsPapiError, enrich_report

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    path = Path(args.report)
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        enriched = enrich_report(report, OddsPapiClient())
        path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        meta = enriched.get("oddspapi_odds", {})
        print("ODDSPAPI_ENRICHMENT:", json.dumps(meta, ensure_ascii=False))
        return 0
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, OddsPapiError) as exc:
        print(f"ODDSPAPI_ENRICHMENT_SKIPPED: {type(exc).__name__}: {str(exc)[:180]}")
        # Optional provider failure must not block the existing API-Football report.
        return 0

if __name__ == "__main__":
    sys.exit(main())
