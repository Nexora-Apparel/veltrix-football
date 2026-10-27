"""Run and print a chronological model comparison from the imported CSV."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

# Support direct execution as `python scripts/run_backtest.py` as well as `-m`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtest_engine import chronological_backtest, load_matches, write_report


def dataset_provenance(input_path: str | Path, matches: list[dict]) -> dict:
    """Return a reproducible fingerprint for the exact bytes evaluated."""
    path = Path(input_path)
    return {
        "input_file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "rows_loaded": len(matches),
        "first_match_date": min((str(row.get("match_date") or row.get("date") or "")[:10] for row in matches), default=None),
        "last_match_date": max((str(row.get("match_date") or row.get("date") or "")[:10] for row in matches), default=None),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Chronological Poisson vs Elo backtest")
    parser.add_argument("--input", default="data/open_historical_matches.csv")
    parser.add_argument("--output", default="reports/backtest_summary.json")
    parser.add_argument("--min-training-matches", type=int, default=100)
    args = parser.parse_args()
    input_path = Path(args.input)
    matches = load_matches(input_path)
    result = chronological_backtest(matches, min_training_matches=args.min_training_matches)
    # Pin every evaluation to the exact dataset bytes. The source file is an
    # ephemeral workflow artifact, so dates and row counts alone are not enough
    # to reproduce a result if upstream data changes.
    result["dataset_provenance"] = dataset_provenance(input_path, matches)
    write_report(result, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "predictions"}, indent=2))
    print(f"Report saved: {args.output}")

if __name__ == "__main__":
    main()
