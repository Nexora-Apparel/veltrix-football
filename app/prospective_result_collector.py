"""Fail-closed, network-free collector for prospective result observations.

This module converts already-retrieved 5Dollar response rows into immutable
availability observations. It does not poll providers, persist data, or infer
settlement timestamps.
"""
from __future__ import annotations

from typing import Any

from app.result_availability_ledger import (
    ResultAvailabilityLedgerError, append_observations,
    build_result_observation,
)

QUALIFIED_FIVEDOLLAR_COMPETITIONS = frozenset({
    "3405541143", "3614399544", "4160026622", "4212821298", "686337048",
})
COLLECTABLE_STATUSES = frozenset({"scheduled", "finished"})


class ProspectiveCollectorError(ValueError):
    pass


def collect_fivedollar_observations(*, response_rows: Any, competition_id: str,
                                    endpoint: str, run_id: str,
                                    observed_at: str) -> dict:
    """Convert a bounded, already-fetched competition response into ledger rows.

    The caller is responsible for reserving and recording HTTP attempts before
    fetching. This function accepts no transport/client and performs no I/O.
    """
    if not isinstance(competition_id, str) or competition_id not in QUALIFIED_FIVEDOLLAR_COMPETITIONS:
        raise ProspectiveCollectorError("competition_not_qualified")
    if not isinstance(response_rows, list):
        raise ProspectiveCollectorError("response_rows_must_be_list")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ProspectiveCollectorError("endpoint_required")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ProspectiveCollectorError("run_id_required")
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ProspectiveCollectorError("observed_at_required")

    observations = []
    rejected = []
    seen_source_ids = set()
    for index, row in enumerate(response_rows):
        if not isinstance(row, dict):
            rejected.append({"input_index": index, "reason": "row_not_object"})
            continue
        league = row.get("league")
        source_competition = league.get("id") if isinstance(league, dict) else None
        if source_competition is None or str(source_competition) != competition_id:
            rejected.append({"input_index": index, "reason": "competition_scope_mismatch"})
            continue
        source_id = row.get("id")
        if isinstance(source_id, bool) or not isinstance(source_id, (str, int)) or not str(source_id).strip():
            rejected.append({"input_index": index, "reason": "source_id_invalid"})
            continue
        source_id = str(source_id)
        if source_id in seen_source_ids:
            rejected.append({"input_index": index, "reason": "duplicate_source_id"})
            continue
        seen_source_ids.add(source_id)
        status = row.get("status")
        if status not in COLLECTABLE_STATUSES:
            rejected.append({"input_index": index, "reason": "status_not_collectable"})
            continue
        fixture_id = f"fivedollar:{source_id}"
        try:
            item = build_result_observation(
                provider="fivedollar",
                competition_id=competition_id,
                fixture_id=fixture_id,
                source_id=source_id,
                endpoint=endpoint,
                run_id=run_id,
                observed_at=observed_at,
                payload=row,
            )
        except ResultAvailabilityLedgerError as exc:
            rejected.append({"input_index": index, "reason": str(exc)[:120]})
            continue
        observations.append(item)

    return {
        "schema_version": 1,
        "provider": "fivedollar",
        "competition_id": competition_id,
        "run_id": run_id,
        "observation_count": len(observations),
        "terminal_result_count": sum(item["terminal_result_observed"] for item in observations),
        "observations": observations,
        "rejected_count": len(rejected),
        "rejected": rejected,
        "provider_requests_made": 0,
        "database_writes": 0,
        "imports": 0,
        "settlement_timestamps_created": 0,
    }


def merge_collected_observations(*, ledger: dict, collection: dict) -> dict:
    """Validate and append a collector result to an in-memory ledger."""
    if not isinstance(collection, dict) or collection.get("schema_version") != 1:
        raise ProspectiveCollectorError("collection_schema_invalid")
    if collection.get("provider") != "fivedollar":
        raise ProspectiveCollectorError("collection_provider_invalid")
    if collection.get("competition_id") not in QUALIFIED_FIVEDOLLAR_COMPETITIONS:
        raise ProspectiveCollectorError("competition_not_qualified")
    rows = collection.get("observations")
    if not isinstance(rows, list):
        raise ProspectiveCollectorError("collection_observations_invalid")
    for item in rows:
        if item.get("provider") != "fivedollar" or item.get("competition_id") != collection["competition_id"]:
            raise ProspectiveCollectorError("collection_scope_mismatch")
        if item.get("run_id") != collection.get("run_id"):
            raise ProspectiveCollectorError("collection_run_id_mismatch")
    try:
        result = append_observations(ledger, rows)
    except ResultAvailabilityLedgerError as exc:
        raise ProspectiveCollectorError(str(exc)) from None
    return {
        **result,
        "rejected_count": collection.get("rejected_count", 0),
        "provider_requests_made": 0,
        "database_writes": 0,
        "imports": 0,
        "settlement_timestamps_created": 0,
    }
