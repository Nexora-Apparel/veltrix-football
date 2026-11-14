"""Export a provenance-bound OpenFootball archive into JSONL for offline use."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from veltrix_v2.providers.openfootball_archive import parse_archive


def parse_timestamp(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    result = datetime.fromisoformat(normalized)
    if result.tzinfo is None or result.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone offset")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--source-path", required=True)
    parser.add_argument("--competition-id", required=True)
    parser.add_argument("--snapshot-commit-sha", required=True)
    parser.add_argument("--snapshot-available-at", required=True, type=parse_timestamp)
    parser.add_argument("--imported-at", type=parse_timestamp)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--allow-rejected", action="store_true")
    args = parser.parse_args()

    imported_at = args.imported_at or datetime.now(timezone.utc)
    source_text = Path(args.source_file).read_text(encoding="utf-8")
    archive = parse_archive(
        source_text,
        competition_id=args.competition_id,
        source_path=args.source_path,
        snapshot_commit_sha=args.snapshot_commit_sha,
        snapshot_available_at=args.snapshot_available_at,
        imported_at=imported_at,
    )
    if not archive.observations:
        raise SystemExit("No eligible scored results were parsed.")
    if archive.rejected_result_count and not args.allow_rejected:
        raise SystemExit(
            f"Refusing partial export: {archive.rejected_result_count} scored rows rejected."
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    observations_path = output_dir / "observations.jsonl"
    lines = []
    for item in archive.observations:
        lines.append(json.dumps({
            "fixture_id": item.fixture_id,
            "competition_id": item.competition_id,
            "home_team_id": item.home_team_id,
            "away_team_id": item.away_team_id,
            "kickoff_at": None,
            "kickoff_date": item.kickoff_date.isoformat(),
            "available_at": item.available_at.isoformat(),
            "recorded_at": item.recorded_at.isoformat(),
            "home_goals": item.home_goals,
            "away_goals": item.away_goals,
        }, sort_keys=True, separators=(",", ":")))
    payload = "\n".join(lines) + "\n"
    observations_path.write_text(payload, encoding="utf-8")
    manifest = {
        "schema_version": "veltrix-openfootball-archive-v1",
        "competition_id": archive.competition_id,
        "season_title": archive.season_title,
        "source_repository": "openfootball/world",
        "source_path": archive.source_path,
        "source_commit_sha": archive.snapshot_commit_sha,
        "snapshot_available_at": archive.snapshot_available_at.isoformat(),
        "imported_at": archive.imported_at.isoformat(),
        "source_content_sha256": archive.content_sha256,
        "observations_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "fixture_line_count": archive.fixture_line_count,
        "result_count": archive.result_count,
        "rejected_result_count": archive.rejected_result_count,
        "kickoff_precision": "date_only",
        "date_only_eligibility": "00:00 UTC on source-local match date + 2 calendar days",
        "publication_policy": "not eligible as historical walk-forward target fixtures",
        "database_written": False,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path),
        "observations": str(observations_path),
        "result_count": archive.result_count,
        "rejected_result_count": archive.rejected_result_count,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
