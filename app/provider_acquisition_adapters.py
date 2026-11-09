"""Provider acquisition adapters; all network transports are injected by callers.

The adapters retain only sanitized normalized records and provenance. Raw
provider payloads are hashed during normalization and are not copied into the
output artifact.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.provider_fixture_pipeline import run_fixture_acquisition_pipeline
from app.provider_fixture_normalizer import normalize_fivedollar_fixture, normalize_striker_game
from app.provider_request_budget import RequestBudgetLedger


class AcquisitionAdapterError(RuntimeError):
    pass


def acquire_fivedollar_day(*, client, day: str, run_id: str,
                           retrieved_at: str | None = None,
                           max_pages: int = 5) -> dict:
    """Fetch one Lagos-local day through the verified 5Dollar client.

    The client is expected to expose the existing _local_day_window() and
    _get() methods. The raw rows are normalized immediately and never emitted.
    """
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 20:
        raise ValueError("max_pages_must_be_between_1_and_20")
    from datetime import date

    target = date.fromisoformat(day)
    start_ts, end_ts = client._local_day_window(target, "Africa/Lagos")
    retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
    observations = []
    page, pages, rate_remaining = 1, 0, None
    while True:
        payload, headers = client._get("fixtures", {
            "start_time": start_ts, "end_time": end_ts,
            "status": "all", "page": page, "per_page": 100,
        })
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise AcquisitionAdapterError("fivedollar_fixture_data_missing")
        rate_remaining = headers.get("X-RateLimit-Remaining", rate_remaining)
        pages += 1
        for row in rows:
            if not isinstance(row, dict):
                observations.append(None)
                continue
            observations.append({
                "provider": "fivedollar",
                "row": row,
                "options": {
                    "endpoint": "fixtures",
                    "retrieved_at": retrieved,
                    "run_id": run_id,
                },
            })
        pagination = payload.get("pagination") or {}
        if not isinstance(pagination, dict):
            raise AcquisitionAdapterError("fivedollar_pagination_invalid")
        if not pagination.get("has_more"):
            break
        if pages >= max_pages:
            raise AcquisitionAdapterError("fivedollar_pagination_truncated")
        page += 1

    pipeline_observations = []
    for item in observations:
        if item is None:
            pipeline_observations.append(None)
            continue
        row = item["row"]
        # The 5Dollar normalizer derives competition and season directly from
        # the source row; do not pass StrikerAPI-only keyword arguments.
        pipeline_observations.append(item)

    return run_fixture_acquisition_pipeline(
        observations=pipeline_observations,
        run_id=run_id,
        provider_scope=["fivedollar"],
        competition_scope=sorted({
            str((item.get("row") or {}).get("league", {}).get("id"))
            for item in pipeline_observations if isinstance(item, dict)
            and isinstance(item.get("row"), dict)
            and (item.get("row").get("league") or {}).get("id") is not None
        }),
        window={"local_date": day, "timezone": "Africa/Lagos"},
        retrieved_at=retrieved,
        request_budget={
            "provider": "fivedollar",
            "calls_made": pages,
            "requests_remaining_header": str(rate_remaining) if rate_remaining is not None else None,
            "max_pages": max_pages,
        },
    )


def acquire_strikerapi_competition(*, api_key: str, competition_key: str,
                                   competition_label: str, status: str,
                                   start: str, end: str, run_id: str,
                                   ledger: RequestBudgetLedger,
                                   transport: Callable[..., dict],
                                   retrieved_at: str | None = None,
                                   max_pages: int = 3) -> dict:
    """Acquire one StrikerAPI competition/status window under a preflight ledger.

    Every transport attempt is charged before invocation. This adapter performs
    no automatic retry; callers must separately budget and implement any retry.
    """
    if not api_key or not competition_key or not competition_label:
        raise ValueError("strikerapi_identity_and_key_required")
    if status not in {"final", "scheduled"}:
        raise ValueError("unsupported_strikerapi_status")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 3:
        raise ValueError("max_pages_must_be_between_1_and_3")
    retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
    rows, page_counts = [], []
    offset, pages, truncated = 0, 0, False
    while pages < max_pages:
        ledger.before_request()
        data = transport(api_key, competition_key, status, start, end, offset)
        games = data.get("games")
        if not isinstance(games, list):
            raise AcquisitionAdapterError("strikerapi_games_array_missing")
        rows.extend(games)
        page_counts.append(data.get("count"))
        pages += 1
        next_offset = data.get("next_offset")
        if next_offset is None:
            break
        if isinstance(next_offset, bool) or not isinstance(next_offset, int) or next_offset <= offset:
            raise AcquisitionAdapterError("strikerapi_next_offset_invalid")
        if not games:
            raise AcquisitionAdapterError("strikerapi_empty_page_continuation")
        offset = next_offset
    else:
        truncated = True

    if truncated:
        raise AcquisitionAdapterError("strikerapi_pagination_truncated")

    observations = [{
        "provider": "strikerapi",
        "row": row,
        "options": {
            "competition_key": competition_key,
            "endpoint": "list_games",
            "retrieved_at": retrieved,
            "run_id": run_id,
        },
    } for row in rows]
    return run_fixture_acquisition_pipeline(
        observations=observations,
        run_id=run_id,
        provider_scope=["strikerapi"],
        competition_scope=[competition_key],
        window={
            "competition_label": competition_label,
            "status": status,
            "from": start,
            "to": end,
        },
        retrieved_at=retrieved,
        request_budget={
            **ledger.report(),
            "pages_fetched": pages,
            "page_count_fields": page_counts,
        },
    )
