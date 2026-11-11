#!/usr/bin/env python3
"""Offline, fail-closed provider acquisition to chronological dataset assembly."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json_atomic(path: str, value: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", required=True, help="JSON array of retained normalized acquisition records with raw evidence")
    parser.add_argument("--settlement-packages", required=True, help="JSON object keyed by provider:source_id")
    parser.add_argument("--team-crosswalk-registry", required=True, help="KMS-signed canonical team crosswalk registry JSON")
    parser.add_argument("--team-crosswalk-as-of", required=True, help="Timezone-aware ISO-8601 coverage verification time")
    parser.add_argument("--split-policy", required=True, help="Chronological train/validation/test split policy JSON")
    parser.add_argument("--output", default="audited_provider_dataset_report.json")
    parser.add_argument("--cutoff-hours", type=int, default=6)
    parser.add_argument("--form-window", type=int, default=10)
    parser.add_argument("--minimum-team-matches", type=int, default=3)
    args = parser.parse_args()

    try:
        trusted_registry = os.getenv("VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON")
        if not trusted_registry:
            raise ValueError("VELTRIX_EVIDENCE_RECEIPT_KMS_TRUSTED_KEYS_JSON_missing")
        from app.source_qualification_registry import build_trusted_kms_clients
        from app.provider_acquisition_dataset_pipeline import assemble_audited_provider_dataset

        records = _read_json(args.records)
        packages = _read_json(args.settlement_packages)
        team_registry = _read_json(args.team_crosswalk_registry)
        split_policy = _read_json(args.split_policy)
        if (not isinstance(records, list) or not isinstance(packages, dict)
                or not isinstance(team_registry, dict) or not isinstance(split_policy, dict)):
            raise ValueError("input_json_top_level_shape_invalid")
        trusted_clients = build_trusted_kms_clients(registry_json=trusted_registry)
        report = assemble_audited_provider_dataset(
            acquisition_records=records,
            settlement_timestamp_packages=packages,
            trusted_kms_clients=trusted_clients,
            team_crosswalk_registry=team_registry,
            team_crosswalk_as_of=args.team_crosswalk_as_of,
            split_policy=split_policy,
            cutoff_hours=args.cutoff_hours,
            form_window=args.form_window,
            minimum_team_matches=args.minimum_team_matches,
        )
        _write_json_atomic(args.output, report)
        feature = report.get("feature_reconstruction", {})
        print(
            "DATASET_PIPELINE_RESULT: "
            f"settlement_eligible={report.get('acquisition_eligibility', {}).get('settlement_eligible_count', 0)}; "
            f"feature_snapshots={feature.get('snapshot_count', 0)}; "
            f"feature_withheld={feature.get('withheld_count', 0)}; "
            f"dataset_assembled={report.get('dataset_assembled', False)}; "
            "training_started=false; database_writes=0; publications=0"
        )
        print(f"REPORT_FILE: {args.output}")
        print(f"REPORT_SHA256: {report['pipeline_report_sha256']}")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"DATASET_PIPELINE_RESULT: REVIEW_REQUIRED ({type(exc).__name__}: {str(exc)[:180]})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
