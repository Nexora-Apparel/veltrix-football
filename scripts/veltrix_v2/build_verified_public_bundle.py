#!/usr/bin/env python3
"""Build the canonical public bundle only after deployment-grade certification."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from veltrix_v2.reporting.artifact_bundle import (
    build_report_surface_bundle,
    parse_portable_report_surface_bundle,
    serialize_portable_report_surface_bundle,
)
from veltrix_v2.reporting.report_identity import verify_report_identity
from veltrix_v2.reporting.runtime import _load_verifier_factory


def _write_new_or_identical(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("CANONICAL_PUBLIC_BUNDLE_IMMUTABLE_CONFLICT")
        return
    temporary = path.with_name("." + path.name + ".tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise ValueError("CANONICAL_PUBLIC_BUNDLE_IMMUTABLE_CONFLICT")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "command-data/public-data/v2_report_bundle.json",
    )
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    identity = verify_report_identity(report)
    factory_spec = os.environ.get(
        "VELTRIX_V2_PUBLICATION_VERIFIER_FACTORY",
        "veltrix_v2.reporting.trusted_runtime:build_deployment_publication_verifier_factory",
    )
    factory = _load_verifier_factory(factory_spec)
    verifier = factory()
    if not callable(verifier) or verifier(report, identity) is not True:
        raise PermissionError("REPORT_CERTIFICATION_NOT_VERIFIED")

    bundle = build_report_surface_bundle(report)
    if bundle.identity != identity:
        raise ValueError("REPORT_BUNDLE_IDENTITY_CHANGED")
    raw = serialize_portable_report_surface_bundle(bundle)

    # Re-parse the exact bytes and re-run the trust decision against the
    # canonical report extracted from those bytes before writing anything.
    parsed = parse_portable_report_surface_bundle(raw)
    if parsed.identity != identity or verifier(parsed.canonical_report, parsed.identity) is not True:
        raise PermissionError("PORTABLE_REPORT_BUNDLE_REVERIFICATION_FAILED")
    digest = hashlib.sha256(raw).hexdigest()
    _write_new_or_identical(args.output, raw)
    persisted = args.output.read_bytes()
    if hashlib.sha256(persisted).hexdigest() != digest:
        raise ValueError("CANONICAL_PUBLIC_BUNDLE_PERSISTENCE_HASH_MISMATCH")
    print(json.dumps({
        "status": "VERIFIED",
        "report_id": identity.report_id,
        "report_sha256": identity.report_sha256,
        "bundle_sha256": digest,
        "bundle_bytes": len(persisted),
        "path": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
