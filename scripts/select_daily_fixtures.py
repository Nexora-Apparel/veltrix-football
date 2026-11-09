#!/usr/bin/env python3
"""Offline selection of up to 25 qualified future fixtures for a Lagos date."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Sanitized acquisition report JSON")
    parser.add_argument("--qualification-registry", required=True,
                        help="Evidence-backed provider/competition qualification JSON")
    parser.add_argument("--date", required=True, help="Target Africa/Lagos date (YYYY-MM-DD)")
    parser.add_argument("--as-of", help="Timezone-aware ISO timestamp; defaults to current UTC")
    parser.add_argument("--max-fixtures", type=int, default=25)
    parser.add_argument("--output", default="veltrix_daily_fixture_selection.json")
    args = parser.parse_args()

    from app.daily_fixture_selection_artifact import (
        SelectionArtifactError,
        build_daily_selection_artifact,
    )

    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        registry = json.loads(Path(args.qualification_registry).read_text(encoding="utf-8"))
        as_of = args.as_of or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        artifact = build_daily_selection_artifact(
            acquisition_report=report,
            qualification_registry=registry,
            target_date=args.date,
            as_of=as_of,
            max_fixtures=args.max_fixtures,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, SelectionArtifactError) as exc:
        print(f"DAILY_SELECTION: BLOCKED ({type(exc).__name__}: {str(exc)[:180]})")
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    selection = artifact["selection"]
    print(
        "DAILY_SELECTION: PASS; "
        f"selected={selection['selected_count']}; "
        f"eligible={selection['eligible_count']}; "
        f"excluded={selection['excluded_count']}; "
        "synthetic=0; database_writes=0; prediction_publications=0"
    )
    print(f"SELECTION_FILE: {output}")
    print(f"SELECTION_SHA256: {artifact['selection_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
