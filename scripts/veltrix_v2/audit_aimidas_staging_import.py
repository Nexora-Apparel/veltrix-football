#!/usr/bin/env python3
"""Independent-process read-after-commit audit for AI Midas staging evidence."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.veltrix_v2.import_aimidas_staging import (
    audit_import, canonical_json, sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL_REQUIRED")
    manifest = json.loads((Path(args.input_dir) / "manifest.json").read_text(encoding="utf-8"))
    digest = sha256(canonical_json(manifest))
    result = audit_import(database_url, digest)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
