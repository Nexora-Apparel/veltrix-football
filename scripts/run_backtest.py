"""Run and print a chronological model comparison from the imported CSV."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Support direct execution as `python scripts/run_backtest.py` as well as `-m`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backtest_engine import chronological_backtest, load_matches, write_report

def main() -> None:
    parser = argparse.ArgumentParser(description="Chronological Poisson vs Elo backtest")
    parser.add_argument("--input", default="data/open_historical_matches.csv")
    parser.add_argument("--output", default="reports/backtest_summary.json")
    parser.add_argument("--min-training-matches", type=int, default=100)
    args = parser.parse_args()
    matches = load_matches(args.input)
    result = chronological_backtest(matches, min_training_matches=args.min_training_matches)
    write_report(result, args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "predictions"}, indent=2))
    print(f"Report saved: {args.output}")

if __name__ == "__main__":
    main()
