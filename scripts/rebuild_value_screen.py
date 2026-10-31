"""Rebuild the paper-only value screen from a saved report without live provider calls."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.value_bets_runtime import attach_value_bet_screens


def rebuild_value_screen(report: dict[str, Any]) -> dict[str, Any]:
    """Recompute candidate previews while preserving certificate-controlled release."""
    if not isinstance(report.get("predictions"), list) or not report.get("as_of_date"):
        raise ValueError("Saved report is missing its date or predictions list.")
    certificate = report.get("value_validation_certificate")
    attach_value_bet_screens(
        report,
        validation_certificate=certificate if isinstance(certificate, dict) else None,
    )
    report["value_screen_rebuilt_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["value_screen_rebuild_notice"] = (
        "Rebuilt from saved pre-kickoff bookmaker snapshots. No football provider was called; "
        "paper-only candidates are not approved betting alerts."
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="reports/daily_predictions.json")
    args = parser.parse_args()
    path = Path(args.report)
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("Saved report must be a JSON object.")
    rebuilt = rebuild_value_screen(report)
    path.write_text(json.dumps(rebuilt, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "as_of_date": rebuilt.get("as_of_date"),
        "status": (rebuilt.get("value_bet_screen") or {}).get("status"),
        "release_approved": (rebuilt.get("value_bet_screen") or {}).get("candidate_count", 0),
        "paper_only_candidates": (rebuilt.get("value_bet_screen") or {}).get("paper_candidate_count", 0),
        "alerts_enabled": (rebuilt.get("value_bet_screen") or {}).get("alerts_enabled", False),
        "provider_calls": 0,
    }, indent=2))


if __name__ == "__main__":
    main()
