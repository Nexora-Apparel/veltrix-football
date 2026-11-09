"""Auditable, sanitized acquisition-run report builder."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone


def build_acquisition_report(*, run_id: str, provider_scope: list[str],
                             competition_scope: list[str], window: dict,
                             retrieved_at: str, batch_result: dict,
                             request_budget: dict | None = None) -> dict:
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id_required")
    if not isinstance(provider_scope, list) or not provider_scope:
        raise ValueError("provider_scope_required")
    if not isinstance(competition_scope, list) or not competition_scope:
        raise ValueError("competition_scope_required")
    if not isinstance(window, dict):
        raise ValueError("window_must_be_object")
    if not isinstance(batch_result, dict):
        raise ValueError("batch_result_must_be_object")
    try:
        stamp = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("retrieved_at_invalid") from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("retrieved_at_timezone_missing")

    accepted = batch_result.get("accepted", [])
    quarantined = batch_result.get("quarantined", [])
    if not isinstance(accepted, list) or not isinstance(quarantined, list):
        raise ValueError("batch_result_rows_invalid")

    by_provider = Counter(row.get("provider", "unknown") for row in accepted)
    by_competition = Counter(
        f'{row.get("provider", "unknown")}:{row.get("competition_key", "unknown")}'
        for row in accepted
    )
    by_status = Counter(row.get("normalized_status", "unknown") for row in accepted)
    quarantine_reasons = Counter(row.get("reason", "unknown") for row in quarantined)

    report = {
        "schema_version": 1,
        "report_type": "veltrix_provider_fixture_acquisition",
        "run_id": run_id,
        "retrieved_at": stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "provider_scope": sorted(set(provider_scope)),
        "competition_scope": sorted(set(competition_scope)),
        "window": window,
        "request_budget": request_budget or {},
        "quality": {
            "input_count": batch_result.get("input_count", 0),
            "accepted_count": len(accepted),
            "quarantined_count": len(quarantined),
            "accepted_by_provider": dict(sorted(by_provider.items())),
            "accepted_by_provider_competition": dict(sorted(by_competition.items())),
            "accepted_by_normalized_status": dict(sorted(by_status.items())),
            "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
            "acceptance_pass": batch_result.get("acceptance_pass") is True,
        },
        "side_effects": {
            "provider_requests_made_by_report_builder": 0,
            "database_writes": 0,
            "imports": 0,
            "checkpoints": 0,
            "canonical_merges": 0,
            "prediction_publications": 0,
        },
        "records": accepted,
        "quarantine": quarantined,
    }
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    report["report_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return report
