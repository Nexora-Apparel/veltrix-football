#!/usr/bin/env python3
"""Fetch only the pinned AI Midas Brazil Serie B 2026 CSV.

This intentionally avoids re-downloading the six historical archives and other
AI Midas files. The source snapshot remains ephemeral on the CI runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.veltrix_v2.collect_aimidas_snapshot import (
    APPROVAL_ID, REPOSITORY, SOURCE_COMMIT, SOURCE_FILES, git_blob_sha1,
)

TARGET_PATH = "advanced stats/Brazil Serie B 2026.csv"
USER_AGENT = "VELTRIX-FOOTBALL-2.0-SERIEB-IDENTITY-AUDIT/1.0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    spec = next((item for item in SOURCE_FILES if item.path == TARGET_PATH), None)
    if spec is None:
        raise RuntimeError("AIMIDAS_SERIE_B_FILE_SPEC_MISSING")
    url = (
        f"https://raw.githubusercontent.com/{REPOSITORY}/{SOURCE_COMMIT}/"
        + quote(TARGET_PATH, safe="/")
    )
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError("AIMIDAS_SERIE_B_SOURCE_HTTP_STATUS_INVALID")
        raw = response.read(spec.expected_bytes + 1)
    if len(raw) != spec.expected_bytes:
        raise RuntimeError("AIMIDAS_SERIE_B_SOURCE_BYTE_COUNT_MISMATCH")
    if hashlib.sha256(raw).hexdigest() == "":
        raise RuntimeError("AIMIDAS_SERIE_B_SOURCE_HASH_EMPTY")
    if git_blob_sha1(raw) != spec.git_blob_sha:
        raise RuntimeError("AIMIDAS_SERIE_B_SOURCE_GIT_BLOB_MISMATCH")

    root = Path(args.output_dir)
    snapshot = root / "snapshots" / TARGET_PATH
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(raw)
    manifest = {
        "schema_version": "veltrix-aimidas-single-file-snapshot-v1",
        "source_repository": REPOSITORY,
        "source_commit_sha": SOURCE_COMMIT,
        "rights_approval_id": APPROVAL_ID,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": [{
            "path": TARGET_PATH,
            "git_blob_sha1": spec.git_blob_sha,
            "expected_bytes": spec.expected_bytes,
            "actual_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "expected_rows": spec.expected_rows,
            "kind": spec.kind,
        }],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "PINNED_SINGLE_FILE_CAPTURED",
        "path": TARGET_PATH,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "git_blob_sha1": spec.git_blob_sha,
        "other_source_files_fetched": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
