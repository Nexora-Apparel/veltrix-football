import json
from pathlib import Path

import pytest
from datetime import datetime, timezone

from scripts.export_openfootball_archive import main


def test_export_script_writes_manifest_and_date_only_jsonl(tmp_path, monkeypatch):
    source = tmp_path / "season.txt"
    source.write_text(
        "= Nigeria Professional League 2025/2026\n"
        "▪ Matchday 1\n"
        "  Fri Aug 22 2025\n"
        "           Remo Stars FC              v Rivers United FC           1-1\n",
        encoding="utf-8",
    )
    output = tmp_path / "out"
    monkeypatch.setattr("sys.argv", [
        "export_openfootball_archive.py",
        "--source-file", str(source),
        "--source-path", "africa/nigeria/2025-26_ng1.txt",
        "--competition-id", "NGA_NPFL",
        "--snapshot-commit-sha", "94624a1b29c197cc9ac0d318a354e7f8062bb81e",
        "--snapshot-available-at", "2026-08-21T07:43:54Z",
        "--imported-at", "2026-11-14T00:42:00Z",
        "--output-dir", str(output),
    ])
    assert main() == 0
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    row = json.loads((output / "observations.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert manifest["database_written"] is False
    assert manifest["result_count"] == 1
    assert row["kickoff_at"] is None
    assert row["kickoff_date"] == "2025-08-22"


def test_full_nigeria_archive_export_records_the_awarded_fixture_exclusion(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "fixtures" / "openfootball" / "nigeria_2025-26_ng1.txt"
    output = tmp_path / "full-archive"
    monkeypatch.setattr("sys.argv", [
        "export_openfootball_archive.py",
        "--source-file", str(source),
        "--source-path", "africa/nigeria/2025-26_ng1.txt",
        "--competition-id", "NGA_NPFL",
        "--snapshot-commit-sha", "94624a1b29c197cc9ac0d318a354e7f8062bb81e",
        "--snapshot-available-at", "2026-08-21T07:43:54Z",
        "--imported-at", "2026-11-14T00:42:00Z",
        "--max-rejected", "1",
        "--output-dir", str(output),
    ])
    assert main() == 0
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fixture_line_count"] == 380
    assert manifest["result_count"] == 379
    assert manifest["rejected_result_count"] == 1
    assert manifest["rejected_annotations"] == ["AWARDED"]


def test_full_nigeria_archive_export_refuses_unapproved_rejected_rows(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "fixtures" / "openfootball" / "nigeria_2025-26_ng1.txt"
    output = tmp_path / "rejected-archive"
    monkeypatch.setattr("sys.argv", [
        "export_openfootball_archive.py",
        "--source-file", str(source),
        "--source-path", "africa/nigeria/2025-26_ng1.txt",
        "--competition-id", "NGA_NPFL",
        "--snapshot-commit-sha", "94624a1b29c197cc9ac0d318a354e7f8062bb81e",
        "--snapshot-available-at", "2026-08-21T07:43:54Z",
        "--imported-at", "2026-11-14T00:42:00Z",
        "--max-rejected", "0",
        "--output-dir", str(output),
    ])
    with pytest.raises(SystemExit, match="maximum permitted is 0"):
        main()
    assert not output.exists()
