from __future__ import annotations

import json
from pathlib import Path

from scripts.veltrix_v2.build_certification_manifest import main
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA, bind_report_identity


def test_offline_manifest_cli_writes_not_certified_output_without_rights_verifier(tmp_path):
    report = bind_report_identity({
        "schema": REPORT_SCHEMA,
        "report_id": "veltrix-test",
        "as_of_date": "2026-11-14",
        "status": "PUBLISHED",
        "release_mode": "FULL_PUBLIC",
        "cutoff_at_utc": "2026-11-14T05:00:00Z",
        "predictions": [{
            "fixture_id": "fixture-1",
            "competition_id": "comp-1",
            "model_build_id": "model-build",
            "kickoff_utc": "2026-11-14T07:00:00Z",
            "cutoff_at_utc": "2026-11-14T05:00:00Z",
            "publication_status": "PUBLISHED",
            "certified_markets": ["1X2"],
            "markets": {"1X2": {"home": 0.5, "draw": 0.25, "away": 0.25}},
        }],
    })
    walk_forward = {
        "evaluation_as_of": "2026-11-14T05:00:00Z",
        "model_build_id": "model-build",
        "fixtures": [],
    }
    inputs = {
        "report.json": report,
        "walk-forward.json": walk_forward,
        "selections.json": [],
        "quotes.json": [],
        "evidence.json": {},
    }
    for name, value in inputs.items():
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "out" / "candidate-manifest.json"

    result = main([
        "--report", str(tmp_path / "report.json"),
        "--walk-forward", str(tmp_path / "walk-forward.json"),
        "--selections", str(tmp_path / "selections.json"),
        "--bookmaker-quotes", str(tmp_path / "quotes.json"),
        "--evidence", str(tmp_path / "evidence.json"),
        "--output", str(output),
    ])

    assert result == 0
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["status"] == "NOT_CERTIFIED"
    assert manifest["certifications"][0]["status"] == "NOT_CERTIFIED"
    assert "RIGHTS_VERIFIER_MISSING" in manifest["certifications"][0]["blockers"]
