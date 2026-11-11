"""Evidence-backed admission profile for historical model datasets.

Summarizes settlement admission, point-in-time feature reconstruction, split
coverage, competition coverage, market outcomes and feature availability. It
never trains, calibrates, certifies or publishes models.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any

from app.point_in_time_feature_contract import FEATURE_CATALOGUE


class HistoricalAdmissionReportError(ValueError):
    pass


def _digest(value: Any) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise HistoricalAdmissionReportError("admission_report_not_canonical_json") from None
    return hashlib.sha256(raw).hexdigest()


def build_historical_dataset_admission_report(pipeline_report: Any) -> dict:
    if not isinstance(pipeline_report, dict):
        raise HistoricalAdmissionReportError("pipeline_report_invalid")
    eligibility = pipeline_report.get("acquisition_eligibility")
    reconstruction = pipeline_report.get("feature_reconstruction")
    dataset = pipeline_report.get("dataset")
    if not isinstance(eligibility, dict) or not isinstance(reconstruction, dict):
        raise HistoricalAdmissionReportError("pipeline_admission_sections_missing")
    accepted = eligibility.get("accepted_records")
    rejected = eligibility.get("rejected_records")
    withheld = reconstruction.get("withheld")
    if not isinstance(accepted, list) or not isinstance(rejected, list) or not isinstance(withheld, list):
        raise HistoricalAdmissionReportError("pipeline_admission_records_invalid")
    if dataset is None:
        rows = []
        quality = {}
    elif isinstance(dataset, dict) and isinstance(dataset.get("rows"), list):
        rows = dataset["rows"]
        quality = dataset.get("quality", {})
        if not isinstance(quality, dict):
            raise HistoricalAdmissionReportError("dataset_quality_invalid")
    else:
        raise HistoricalAdmissionReportError("dataset_shape_invalid")

    split_counts = Counter()
    competition_counts = defaultdict(Counter)
    market_outcomes = defaultdict(lambda: defaultdict(Counter))
    feature_counts = Counter()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise HistoricalAdmissionReportError(f"dataset_row_invalid:{index}")
        split, competition = row.get("split"), row.get("competition_key")
        predictors, targets = row.get("predictors"), row.get("targets")
        if split not in {"train", "validation", "test"} or not isinstance(competition, str) or not competition:
            raise HistoricalAdmissionReportError(f"dataset_row_scope_invalid:{index}")
        if not isinstance(predictors, dict) or not isinstance(targets, dict):
            raise HistoricalAdmissionReportError(f"dataset_row_features_invalid:{index}")
        split_counts[split] += 1
        competition_counts[competition][split] += 1
        feature_counts.update(predictors.keys())
        for market, outcome in targets.items():
            market_outcomes[market][split][outcome] += 1

    expected_snapshot_count = reconstruction.get("snapshot_count", 0)
    expected_withheld_count = reconstruction.get("withheld_count", len(withheld))
    if (isinstance(expected_snapshot_count, bool) or not isinstance(expected_snapshot_count, int)
            or expected_snapshot_count < 0 or expected_snapshot_count > len(accepted)):
        raise HistoricalAdmissionReportError("feature_snapshot_count_invalid")
    if (isinstance(expected_withheld_count, bool) or not isinstance(expected_withheld_count, int)
            or expected_withheld_count != len(withheld)):
        raise HistoricalAdmissionReportError("feature_withheld_count_mismatch")

    feature_coverage = {
        name: {
            "fixtures": feature_counts.get(name, 0),
            "included_dataset_rows": len(rows),
            "coverage_rate": (feature_counts.get(name, 0) / len(rows)) if rows else 0.0,
        }
        for name in sorted(FEATURE_CATALOGUE)
    }
    absent_feature_names = sorted(name for name, stats in feature_coverage.items() if stats["fixtures"] == 0)
    market_counts = {
        market: {
            split: dict(sorted(outcomes.get(split, {}).items()))
            for split in ("train", "validation", "test")
        }
        for market, outcomes in sorted(market_outcomes.items())
    }
    report = {
        "schema_version": 1,
        "report_type": "veltrix_historical_dataset_admission_profile",
        "settlement_admission": {
            "input_records": eligibility.get("input_record_count", 0),
            "eligible_fixtures": len(accepted),
            "rejected_fixtures": len(rejected),
            "rejected_by_reason": eligibility.get("rejected_by_reason", {}),
            "unmatched_settlement_packages": len(eligibility.get("unmatched_settlement_package_ids", [])),
        },
        "point_in_time_feature_admission": {
            "target_fixtures": reconstruction.get("target_fixture_count", 0),
            "snapshots_built": expected_snapshot_count,
            "withheld_fixtures": expected_withheld_count,
            "withheld_by_reason": reconstruction.get("withheld_by_reason", {}),
            "withheld_examples": withheld,
            "historical_feature_availability_proven": pipeline_report.get("historical_availability_proven") is True,
        },
        "dataset": {
            "included_rows": len(rows),
            "excluded_after_split_assignment": quality.get("excluded_fixture_count", 0),
            "counts_by_split": {s: split_counts.get(s, 0) for s in ("train", "validation", "test")},
            "counts_by_competition_and_split": {
                comp: {s: counts.get(s, 0) for s in ("train", "validation", "test")}
                for comp, counts in sorted(competition_counts.items())
            },
            "market_outcome_counts": market_counts,
        },
        "feature_coverage": {
            "included_row_denominator": len(rows),
            "by_feature": feature_coverage,
            "catalogue_features_absent": absent_feature_names,
        },
        "training_readiness": {
            "ready_for_model_training": False,
            "reason": "Admission profile is descriptive only; source completeness, minimum sample sizes, walk-forward performance and certification remain unverified",
            "model_training_started": False,
            "calibration_performed": False,
            "publication_allowed": False,
            "value_betting_enabled": False,
        },
        "side_effects": {
            "database_writes": 0,
            "model_training_runs": 0,
            "prediction_publications": 0,
        },
    }
    report["report_sha256"] = _digest(report)
    return report
