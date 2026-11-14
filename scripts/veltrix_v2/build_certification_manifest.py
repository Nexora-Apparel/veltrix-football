"""Build an unsigned, fail-closed V2 certification manifest from local evidence JSON.

This is an offline audit tool. It makes no provider/API calls and performs no
database writes. Without an injected trusted rights verifier, the output is
always NOT_CERTIFIED and cannot authorize publication.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from veltrix_v2.evaluation.certification_manifest_builder import build_certification_manifest
from veltrix_v2.evaluation.walk_forward import FixtureEvaluation, WalkForwardReport


def _load_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"INPUT_JSON_INVALID:{path}") from exc


def _aware(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"WALK_FORWARD_TIMESTAMP_INVALID:{field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"WALK_FORWARD_TIMESTAMP_INVALID:{field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"WALK_FORWARD_TIMESTAMP_NOT_AWARE:{field}")
    return parsed


def _walk_forward_report(document: dict[str, Any]) -> WalkForwardReport:
    if not isinstance(document, dict) or not isinstance(document.get("fixtures"), list):
        raise ValueError("WALK_FORWARD_JSON_SCHEMA_INVALID")
    fixtures = []
    for index, row in enumerate(document["fixtures"]):
        if not isinstance(row, dict):
            raise ValueError(f"WALK_FORWARD_FIXTURE_INVALID:{index}")
        payload = dict(row)
        payload["kickoff_at"] = _aware(payload.get("kickoff_at"), f"fixtures[{index}].kickoff_at")
        payload["cutoff_at"] = _aware(payload.get("cutoff_at"), f"fixtures[{index}].cutoff_at")
        fixtures.append(FixtureEvaluation(**payload))
    return WalkForwardReport(
        evaluation_as_of=_aware(document.get("evaluation_as_of"), "evaluation_as_of"),
        total_input_fixtures=int(document.get("total_input_fixtures", len(fixtures))),
        eligible_scored_fixtures=int(document.get("eligible_scored_fixtures", len(fixtures))),
        skipped_no_history=int(document.get("skipped_no_history", 0)),
        skipped_invalid_target=int(document.get("skipped_invalid_target", 0)),
        skipped_duplicate_ids=int(document.get("skipped_duplicate_ids", 0)),
        skipped_after_evaluation_as_of=int(document.get("skipped_after_evaluation_as_of", 0)),
        one_x_two=None,
        btts=None,
        over_2_5=None,
        fixtures=tuple(fixtures),
        skipped_date_only_targets=int(document.get("skipped_date_only_targets", 0)),
        non_certifiable_input_rows=int(document.get("non_certifiable_input_rows", 0)),
        recency_half_life_days=document.get("recency_half_life_days"),
        dixon_coles_rho=float(document.get("dixon_coles_rho", 0.0)),
        model_build_id=document.get("model_build_id"),
    )


def _rows(document: Any, key: str) -> list[dict[str, Any]]:
    rows = document.get(key) if isinstance(document, dict) else document
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{key.upper()}_JSON_SCHEMA_INVALID")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--walk-forward", required=True)
    parser.add_argument("--selections", required=True)
    parser.add_argument("--bookmaker-quotes", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--recent-window-days", type=int, default=90)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    args = parser.parse_args(argv)

    try:
        report = _load_json(args.report)
        walk_forward = _walk_forward_report(_load_json(args.walk_forward))
        selections = _rows(_load_json(args.selections), "selections")
        bookmaker_quotes = _rows(_load_json(args.bookmaker_quotes), "quotes")
        evidence = _load_json(args.evidence)
        if not isinstance(evidence, dict):
            raise ValueError("EVIDENCE_JSON_SCHEMA_INVALID")
        manifest = build_certification_manifest(
            report=report,
            walk_forward_report=walk_forward,
            prospective_selections=selections,
            bookmaker_quotes=bookmaker_quotes,
            evidence=evidence,
            rights_verifier=None,
            recent_window_days=args.recent_window_days,
            bootstrap_samples=args.bootstrap_samples,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
        blocker_count = sum(len(record.get("blockers", [])) for record in manifest["certifications"])
        print(json.dumps({
            "status": manifest["status"],
            "certification_records": len(manifest["certifications"]),
            "certified_records": sum(record["status"] == "CERTIFIED" for record in manifest["certifications"]),
            "blocker_count": blocker_count,
            "output": str(output),
            "publication_authorized": False,
            "reason": "UNSIGNED_MANIFEST_AND_NO_RUNTIME_RIGHTS_VERIFIER",
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
