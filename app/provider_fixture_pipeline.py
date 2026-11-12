"""Pure, read-only orchestration for provider fixture observation batches."""
from __future__ import annotations

from app.provider_fixture_batch import process_observations
from app.provider_acquisition_report import build_acquisition_report


def run_fixture_acquisition_pipeline(*, observations: list[dict], run_id: str,
                                     provider_scope: list[str],
                                     competition_scope: list[str],
                                     window: dict, retrieved_at: str,
                                     request_budget: dict | None = None) -> dict:
    """Normalize, validate, deduplicate, quarantine, and build an audit report."""
    batch = process_observations(observations)
    report = build_acquisition_report(
        run_id=run_id,
        provider_scope=provider_scope,
        competition_scope=competition_scope,
        window=window,
        retrieved_at=retrieved_at,
        batch_result=batch,
        request_budget=request_budget,
    )
    return {
        "schema_version": 1,
        "mode": "read_only_fixture_acquisition_pipeline",
        "acceptance_pass": batch["acceptance_pass"],
        "batch": batch,
        "report": report,
        "side_effects": {
            "provider_requests": 0,
            "database_writes": 0,
            "imports": 0,
            "checkpoints": 0,
            "canonical_merges": 0,
            "prediction_publications": 0,
        },
    }
