"""Fail-closed rolling-hour request ledger for 5Dollar provider calls."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class HourlyQuotaError(ValueError):
    pass


def _time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise HourlyQuotaError(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HourlyQuotaError(f"{field}_invalid") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HourlyQuotaError(f"{field}_timezone_missing")
    return parsed.astimezone(timezone.utc)


def _save(path: str | Path, ledger: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\\n", encoding="utf-8"
    )
    temporary.replace(destination)


def _load(path: str | Path) -> dict:
    try:
        ledger = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise HourlyQuotaError("hourly_ledger_unreadable") from None
    if not isinstance(ledger, dict) or ledger.get("schema_version") != 1:
        raise HourlyQuotaError("hourly_ledger_schema_invalid")
    if (ledger.get("provider") != "fivedollar" or ledger.get("window_seconds") != 3600
            or ledger.get("maximum_requests") != 60
            or not isinstance(ledger.get("reservations"), list)):
        raise HourlyQuotaError("hourly_ledger_policy_invalid")
    if len(ledger["reservations"]) > 1000:
        raise HourlyQuotaError("hourly_ledger_capacity_exceeded")
    return ledger


def _validate_reservations(ledger: dict, now: datetime) -> list[dict]:
    seen = set()
    valid = []
    for index, item in enumerate(ledger["reservations"]):
        if not isinstance(item, dict):
            raise HourlyQuotaError(f"hourly_reservation_invalid:{index}")
        run_id = item.get("run_id")
        if not isinstance(run_id, str) or not run_id or run_id in seen:
            raise HourlyQuotaError(f"hourly_reservation_run_id_invalid:{index}")
        seen.add(run_id)
        reserved_at = _time(item.get("reserved_at"), f"reservation_{index}_reserved_at")
        if reserved_at > now:
            raise HourlyQuotaError(f"hourly_reservation_from_future:{index}")
        reserved = item.get("reserved_requests")
        if isinstance(reserved, bool) or not isinstance(reserved, int) or not 1 <= reserved <= 60:
            raise HourlyQuotaError(f"hourly_reservation_amount_invalid:{index}")
        state = item.get("state")
        actual = item.get("actual_requests")
        if state == "reserved":
            if actual is not None:
                raise HourlyQuotaError(f"hourly_pending_reservation_has_actual:{index}")
            effective = reserved
        elif state == "settled":
            if isinstance(actual, bool) or not isinstance(actual, int) or not 0 <= actual <= reserved:
                raise HourlyQuotaError(f"hourly_settled_reservation_amount_invalid:{index}")
            if not item.get("settled_at"):
                raise HourlyQuotaError(f"hourly_settled_timestamp_missing:{index}")
            settled_time = _time(item["settled_at"], f"reservation_{index}_settled_at")
            if settled_time < reserved_at:
                raise HourlyQuotaError(f"hourly_settled_timestamp_precedes_reservation:{index}")
            if settled_time > now:
                raise HourlyQuotaError(f"hourly_settled_timestamp_from_future:{index}")
            effective = actual
        else:
            raise HourlyQuotaError(f"hourly_reservation_state_invalid:{index}")
        valid.append({
            **item,
            "_reserved_at": reserved_at,
            "_effective_requests": effective,
        })
    return valid


def reserve_hourly_quota(*, ledger_path: str | Path, run_id: str,
                         reserved_requests: int, now: str | None = None) -> dict:
    if not isinstance(run_id, str) or not run_id.strip():
        raise HourlyQuotaError("run_id_required")
    if isinstance(reserved_requests, bool) or not isinstance(reserved_requests, int) or not 5 <= reserved_requests <= 20:
        raise HourlyQuotaError("reservation_must_be_between_5_and_20")
    instant = _time(now, "now") if now is not None else datetime.now(timezone.utc)
    ledger = _load(ledger_path)
    existing = _validate_reservations(ledger, instant)
    if any(item["run_id"] == run_id for item in existing):
        raise HourlyQuotaError("run_id_already_reserved")
    active = [
        item for item in existing
        if instant - item["_reserved_at"] < timedelta(seconds=3600)
    ]
    used = sum(item["_effective_requests"] for item in active)
    if used + reserved_requests > 60:
        raise HourlyQuotaError(f"hourly_quota_exceeded:used={used}:requested={reserved_requests}:limit=60")
    ledger["reservations"].append({
        "run_id": run_id,
        "reserved_at": instant.isoformat().replace("+00:00", "Z"),
        "reserved_requests": reserved_requests,
        "actual_requests": None,
        "state": "reserved",
    })
    Path(ledger_path).write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "reserved": True,
        "run_id": run_id,
        "reserved_requests": reserved_requests,
        "active_hourly_requests_before": used,
        "hourly_capacity_after_reservation": 60 - used - reserved_requests,
    }


def settle_hourly_quota(*, ledger_path: str | Path, run_id: str,
                        actual_requests: int, settled_at: str | None = None) -> dict:
    if isinstance(actual_requests, bool) or not isinstance(actual_requests, int) or not 5 <= actual_requests <= 20:
        raise HourlyQuotaError("actual_request_count_must_be_between_5_and_20")
    instant = _time(settled_at, "settled_at") if settled_at is not None else datetime.now(timezone.utc)
    ledger = _load(ledger_path)
    reservations = _validate_reservations(ledger, instant)
    matches = [item for item in reservations if item["run_id"] == run_id]
    if len(matches) != 1:
        raise HourlyQuotaError("hourly_reservation_not_found_or_ambiguous")
    match = matches[0]
    if match["state"] != "reserved":
        raise HourlyQuotaError("hourly_reservation_not_pending")
    if actual_requests > match["reserved_requests"]:
        raise HourlyQuotaError("actual_requests_exceed_reserved_amount")
    for item in ledger["reservations"]:
        if item["run_id"] == run_id:
            item["actual_requests"] = actual_requests
            item["state"] = "settled"
            item["settled_at"] = instant.isoformat().replace("+00:00", "Z")
            break
    Path(ledger_path).write_text(
        json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "settled": True,
        "run_id": run_id,
        "actual_requests": actual_requests,
        "unused_reservation_released": match["reserved_requests"] - actual_requests,
    }
