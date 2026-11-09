"""Build and validate sanitized 5Dollar competition-qualification evidence.

This module is offline: it accepts already collected counters and never calls a
provider, opens a database connection, or writes project state.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_COMPETITION = {
    "competition_id", "competition_name", "pages_fetched", "source_rows",
    "accepted_rows", "invalid_rows", "duplicate_ids", "missing_team_ids",
    "pagination_complete",
}
_REQUIRED_ENDPOINT = {"endpoint", "requests"}


def _utc(value: str, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field}_must_be_nonnegative_integer")
    return value


def _hash(report: dict) -> str:
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_fivedollar_qualification_report(
    *, run_id: str, retrieved_at: str, window_start_utc: str,
    window_end_utc: str, max_requests: int, actual_requests: int,
    endpoint_requests: list[dict], competitions: list[dict],
    database_writes: int = 0, imports: int = 0, checkpoints: int = 0,
    canonical_merges: int = 0, prediction_publications: int = 0,
    catalogue_pages_fetched: int = 1, catalogue_pagination_complete: bool = True,
) -> dict:
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id_required")
    retrieved = _utc(retrieved_at, "retrieved_at")
    start, end = _utc(window_start_utc, "window_start_utc"), _utc(window_end_utc, "window_end_utc")
    if start >= end:
        raise ValueError("window_order_invalid")
    max_requests = _nonnegative_int(max_requests, "max_requests")
    actual_requests = _nonnegative_int(actual_requests, "actual_requests")
    if max_requests == 0 or actual_requests > max_requests:
        raise ValueError("request_budget_exceeded")
    if not isinstance(endpoint_requests, list) or not endpoint_requests:
        raise ValueError("endpoint_requests_required")
    endpoints = []
    endpoint_total = 0
    for item in endpoint_requests:
        if not isinstance(item, dict) or set(item) != _REQUIRED_ENDPOINT:
            raise ValueError("endpoint_accounting_shape_invalid")
        endpoint, count = item["endpoint"], _nonnegative_int(item["requests"], "endpoint_requests")
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("endpoint_name_invalid")
        endpoints.append({"endpoint": endpoint, "requests": count})
        endpoint_total += count
    if endpoint_total != actual_requests:
        raise ValueError("endpoint_request_accounting_mismatch")
    if not isinstance(competitions, list) or not competitions:
        raise ValueError("competitions_required")

    catalogue_pages_fetched = _nonnegative_int(catalogue_pages_fetched, "catalogue_pages_fetched")
    if not isinstance(catalogue_pagination_complete, bool):
        raise ValueError("catalogue_pagination_complete_invalid")
    cleaned, seen = [], set()
    fields = ("pages_fetched", "source_rows", "accepted_rows", "invalid_rows",
              "duplicate_ids", "missing_team_ids")
    for index, item in enumerate(competitions):
        if not isinstance(item, dict) or set(item) != _REQUIRED_COMPETITION:
            raise ValueError(f"competition_shape_invalid:{index}")
        cid, name = item["competition_id"], item["competition_name"]
        if not isinstance(cid, (str, int)) or isinstance(cid, bool) or not str(cid).strip():
            raise ValueError(f"competition_id_invalid:{index}")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"competition_name_invalid:{index}")
        key = str(cid)
        if key in seen:
            raise ValueError("duplicate_competition_id")
        seen.add(key)
        row = {"competition_id": key, "competition_name": name.strip()}
        for field in fields:
            row[field] = _nonnegative_int(item[field], field)
        if not isinstance(item["pagination_complete"], bool):
            raise ValueError(f"pagination_complete_invalid:{index}")
        row["pagination_complete"] = item["pagination_complete"]
        if row["accepted_rows"] + row["invalid_rows"] > row["source_rows"]:
            raise ValueError(f"competition_row_accounting_invalid:{index}")
        cleaned.append(row)
    cleaned.sort(key=lambda x: x["competition_id"])

    sums = {field: sum(row[field] for row in cleaned) for field in fields}
    side_effects = {
        "database_writes": _nonnegative_int(database_writes, "database_writes"),
        "imports": _nonnegative_int(imports, "imports"),
        "checkpoints": _nonnegative_int(checkpoints, "checkpoints"),
        "canonical_merges": _nonnegative_int(canonical_merges, "canonical_merges"),
        "prediction_publications": _nonnegative_int(prediction_publications, "prediction_publications"),
    }
    if any(value != 0 for value in side_effects.values()):
        raise ValueError("side_effect_boundary_invalid")
    complete = catalogue_pagination_complete and all(row["pagination_complete"] for row in cleaned)
    acceptance = (
        complete and sums["source_rows"] > 0
        and sums["accepted_rows"] > 0
        and all(row["accepted_rows"] > 0 for row in cleaned)
        and all(sums[key] == 0 for key in ("invalid_rows", "duplicate_ids", "missing_team_ids"))
        and all(value == 0 for value in side_effects.values())
    )
    report = {
        "schema_version": 1,
        "mode": "read_only_5dollar_competition_qualification",
        "provider": "5DollarFootballAPI",
        "run_id": run_id,
        "retrieved_at": retrieved,
        "window_start_utc": start,
        "window_end_utc": end,
        "request_budget": {
            "maximum_requests": max_requests,
            "actual_requests": actual_requests,
            "endpoint_accounting": sorted(endpoints, key=lambda x: x["endpoint"]),
        },
        "catalogue": {"pages_fetched": catalogue_pages_fetched, "pagination_complete": catalogue_pagination_complete},
        "competition_count": len(cleaned),
        "competitions": cleaned,
        "aggregates": sums,
        "side_effects": side_effects,
        "acceptance_pass": acceptance,
    }
    report["report_sha256"] = _hash(report)
    return report


def validate_fivedollar_qualification_report(report: Any) -> dict:
    if not isinstance(report, dict):
        raise ValueError("report_not_object")
    supplied = report.get("report_sha256")
    if not isinstance(supplied, str) or not _SHA256.fullmatch(supplied):
        raise ValueError("report_hash_invalid")
    unhashed = dict(report)
    unhashed.pop("report_sha256", None)
    if _hash(unhashed) != supplied:
        raise ValueError("report_hash_mismatch")
    if report.get("schema_version") != 1 or report.get("mode") != "read_only_5dollar_competition_qualification":
        raise ValueError("report_schema_invalid")
    if report.get("provider") != "5DollarFootballAPI":
        raise ValueError("provider_scope_invalid")
    catalogue = report.get("catalogue")
    if not isinstance(catalogue, dict) or not isinstance(catalogue.get("pages_fetched"), int) or catalogue.get("pagination_complete") not in (True, False):
        raise ValueError("catalogue_metadata_invalid")
    competitions = report.get("competitions")
    if not isinstance(competitions, list) or report.get("competition_count") != len(competitions):
        raise ValueError("competition_count_mismatch")
    ids = [str(item.get("competition_id")) for item in competitions if isinstance(item, dict)]
    if len(ids) != len(competitions) or len(ids) != len(set(ids)):
        raise ValueError("competition_identity_invalid")
    aggregates = report.get("aggregates")
    if not isinstance(aggregates, dict):
        raise ValueError("aggregates_invalid")
    for field in ("pages_fetched", "source_rows", "accepted_rows", "invalid_rows",
                  "duplicate_ids", "missing_team_ids"):
        expected = sum(item.get(field, -1) for item in competitions)
        if aggregates.get(field) != expected:
            raise ValueError(f"aggregate_mismatch:{field}")
    budget = report.get("request_budget")
    if not isinstance(budget, dict):
        raise ValueError("request_budget_invalid")
    entries = budget.get("endpoint_accounting")
    if not isinstance(entries, list) or sum(x.get("requests", -1) for x in entries) != budget.get("actual_requests"):
        raise ValueError("request_accounting_mismatch")
    if budget.get("actual_requests", -1) > budget.get("maximum_requests", -1):
        raise ValueError("request_budget_exceeded")
    effects = report.get("side_effects")
    required = ("database_writes", "imports", "checkpoints", "canonical_merges", "prediction_publications")
    if not isinstance(effects, dict) or any(effects.get(key) != 0 for key in required):
        raise ValueError("side_effect_boundary_invalid")
    recomputed = (
        catalogue.get("pagination_complete") is True
        and all(item.get("pagination_complete") is True for item in competitions)
        and aggregates.get("source_rows", 0) > 0
        and aggregates.get("accepted_rows", 0) > 0
        and all(item.get("accepted_rows", 0) > 0 for item in competitions)
        and all(aggregates.get(key) == 0 for key in ("invalid_rows", "duplicate_ids", "missing_team_ids"))
    )
    if report.get("acceptance_pass") is not recomputed:
        raise ValueError("acceptance_flag_mismatch")
    return {"valid": True, "report_sha256": supplied,
            "competition_count": len(competitions), "aggregates": aggregates,
            "acceptance_pass": recomputed}
