"""Score a saved prediction report against a completed-fixture API JSON response."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.paper_tracking import evaluate_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Saved daily_predictions.json")
    parser.add_argument("--results", required=True, help="API-Football fixture response JSON for the same date")
    parser.add_argument("--output", default="reports/paper_evaluation.json")
    args = parser.parse_args()
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        results = json.loads(Path(args.results).read_text(encoding="utf-8"))
        evaluation = evaluate_report(report, results)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evaluation, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "report_date": evaluation["report_date"],
            "completed_forecasts_scored": evaluation["completed_forecasts_scored"],
            "metrics": evaluation["metrics"],
            "output": str(output),
            "model_status": evaluation["model_status"],
        }, indent=2))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"PAPER EVALUATION FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
