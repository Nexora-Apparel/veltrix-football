"""Restore evidence that was generated but not published during the 2026-11-01 run."""
from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

from app.value_evidence_ledger import merge_evidence_ledger
from scripts.publish_command_data import publish


def reconcile(previous: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Merge the preserved pre-failure ledger with the current published report."""
    if previous.get("version") != "VELTRIX_VALUE_EVIDENCE_V1":
        raise ValueError("Recovery artifact has an unsupported evidence schema.")
    if previous.get("release_status") != "LOCKED_SHADOW_MODE":
        raise ValueError("Recovery artifact is not locked in shadow mode.")
    merged = merge_evidence_ledger(previous, report)
    previous_ids = {
        str(row.get("observation_id"))
        for row in previous.get("observations", [])
        if isinstance(row, dict) and row.get("observation_id")
    }
    merged_ids = {
        str(row.get("observation_id"))
        for row in merged.get("observations", [])
        if isinstance(row, dict) and row.get("observation_id")
    }
    if not previous_ids.issubset(merged_ids):
        raise ValueError("Recovery would discard previously recorded evidence.")
    if merged.get("release_status") != "LOCKED_SHADOW_MODE":
        raise ValueError("Recovery unexpectedly changed the value release lock.")
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-zip", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if not repo or not token:
        print("Recovery refused: GitHub publication context is unavailable.", file=sys.stderr)
        return 2

    with zipfile.ZipFile(args.artifact_zip) as archive:
        candidates = [name for name in archive.namelist() if name.endswith("value_evidence_ledger.json")]
        if len(candidates) != 1:
            raise ValueError("Recovery artifact must contain exactly one value evidence ledger.")
        previous = json.loads(archive.read(candidates[0]).decode("utf-8"))

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("as_of_date") != "2026-11-02":
        raise ValueError("Recovery report is not the expected 2026-11-02 published report.")

    merged = reconcile(previous, report)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(merged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    publish("public-data/value_evidence_ledger.json", output, repo, token)
    print(json.dumps({
        "status": "RECOVERED_AND_PUBLISHED",
        "previous_observations": len(previous.get("observations") or []),
        "new_observations": merged.get("summary", {}).get("observations_added", 0),
        "merged_observations": len(merged.get("observations") or []),
        "price_series": len(merged.get("price_series") or []),
        "last_report_date": merged.get("last_report_date"),
        "alerts_enabled": merged.get("summary", {}).get("alerts_enabled"),
        "bytes": output.stat().st_size,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
