import json

from scripts.veltrix_v2.build_report_surface_bundle import build
from veltrix_v2.reporting.report_identity import REPORT_SCHEMA


def test_local_bundle_cli_builder_emits_only_aggregate_summary(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "schema": REPORT_SCHEMA,
        "report_id": "cli-report-2026-11-14",
        "as_of_date": "2026-11-14",
        "release_mode": "INTERNAL_SHADOW",
        "predictions": [{"fixture_id": "private-fixture", "publication_status": "SHADOW_ONLY"}],
    }))
    output = tmp_path / "output"
    summary = build(source, output)
    assert summary["status"] == "ARTIFACT_BUNDLE_READY"
    assert summary["fixture_count"] == 1
    assert "private-fixture" not in json.dumps(summary)
    assert summary["side_effects"] == {
        "provider_requests": 0,
        "database_writes": 0,
        "telegram_messages": 0,
        "schedule_activation": 0,
        "publications": 0,
    }
    assert all(path.exists() for path in summary["outputs"].values())
