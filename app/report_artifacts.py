"""Read the latest published command data from the public data branch.

This reads existing JSON snapshots only. It does not start prediction workflows,
download GitHub Actions artifacts, or call the football provider.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_REPOSITORY = "Nexora-Apparel/veltrix-football"
DEFAULT_BRANCH = "command-data"
CACHE_SECONDS = 30
# Vercel Hobby functions have a short execution budget. The report is required;
# ledger and model-validation snapshots are optional enrichments.
_REPORT_TIMEOUT_SECONDS = 3.0
_OPTIONAL_TIMEOUT_SECONDS = 1.25
_API_FALLBACK_TIMEOUT_SECONDS = 1.0
_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}


def _parse_snapshot(raw: bytes, kind: str) -> dict[str, Any] | None:
    if len(raw) > 4_000_000:
        return None
    parsed: Any = json.loads(raw.decode("utf-8"))
    if isinstance(parsed, dict) and isinstance(parsed.get("content"), str) and parsed.get("encoding") == "base64":
        parsed = json.loads(base64.b64decode(parsed["content"]).decode("utf-8"))
    if not isinstance(parsed, dict):
        return None
    if kind == "report":
        if not isinstance(parsed.get("predictions"), list) or parsed.get("status") == "NOT_YET_PUBLISHED":
            return None
        if parsed.get("schema") == REPORT_SCHEMA:
            try:
                verify_report_identity(parsed)
            except (TypeError, ValueError):
                return None
        return parsed
    if kind == "dashboard":
        return parsed if parsed.get("snapshot_schema") == "VELTRIX_DASHBOARD_V1" and isinstance(parsed.get("predictions"), list) and parsed.get("as_of_date") else None
    if kind == "ledger":
        return parsed if isinstance(parsed.get("cumulative_metrics_by_model"), dict) and parsed.get("model_status") == "PAPER_TRACKING_ONLY" else None
    if kind == "model_validation":
        return parsed if parsed.get("status") == "RESEARCH_DIAGNOSTIC_ONLY" and isinstance(parsed.get("dataset"), dict) else None
    return None


def _load(kind: str) -> dict[str, Any] | None:
    now = time.monotonic()
    cached = _cache.get(kind)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]

    repo = (os.environ.get("VELTRIX_DATA_REPOSITORY") or DEFAULT_REPOSITORY).strip()
    branch = (os.environ.get("VELTRIX_DATA_BRANCH") or DEFAULT_BRANCH).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not re.fullmatch(r"[A-Za-z0-9_.-]+", branch):
        _cache[kind] = (now, None)
        return None

    filenames = {
        "report": "daily_predictions.json",
        "dashboard": "dashboard_snapshot.json",
        "ledger": "paper_tracking_ledger.json",
        "model_validation": "model_validation_report.json",
    }
    filename = filenames.get(kind)
    if not filename:
        _cache[kind] = (now, None)
        return None

    cache_buster = int(time.time())
    headers = {
        "User-Agent": "Veltrix-Football-Command-Centre",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    value: dict[str, Any] | None = None

    # Public raw snapshots avoid GitHub Contents API's low anonymous rate limit.
    # This is one bounded request rather than a 5s API call followed by a
    # second 5s CDN fallback, which could exceed Vercel's function time budget.
    raw_url = (
        f"https://raw.githubusercontent.com/{repo}/{branch}/public-data/{filename}"
        f"?v={cache_buster}"
    )
    timeout = _REPORT_TIMEOUT_SECONDS if kind == "report" else _OPTIONAL_TIMEOUT_SECONDS
    try:
        request = Request(raw_url, headers=headers)
        with urlopen(request, timeout=timeout) as response:
            value = _parse_snapshot(response.read(4_000_001), kind)
    except (HTTPError, URLError, OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        value = None

    # Short, bounded Contents API fallback for transient raw-CDN failures.
    # Never let optional panels consume the report endpoint's execution budget.
    if value is None:
        api_url = (
            f"https://api.github.com/repos/{repo}/contents/public-data/{filename}"
            f"?ref={branch}&v={cache_buster}"
        )
        try:
            request = Request(api_url, headers={
                **headers,
                "Accept": "application/vnd.github.raw+json",
            })
            with urlopen(request, timeout=_API_FALLBACK_TIMEOUT_SECONDS) as response:
                value = _parse_snapshot(response.read(4_000_001), kind)
        except (HTTPError, URLError, OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            value = None

    _cache[kind] = (now, value)
    return value


def load_latest_report() -> dict[str, Any] | None:
    """Load the most recently published prediction report, if one exists."""
    return _load("report")


def load_paper_ledger() -> dict[str, Any] | None:
    """Load the published cumulative paper-tracking ledger, if one exists."""
    return _load("ledger")


def load_model_validation_report() -> dict[str, Any] | None:
    """Load the published chronological model-validation evidence snapshot."""
    return _load("model_validation")


def load_dashboard_snapshot() -> dict[str, Any] | None:
    """Load dashboard projection and reject V2 report-identity drift."""
    snapshot = _load("dashboard")
    if snapshot is None:
        return None
    if "report_id" in snapshot or "report_sha256" in snapshot:
        report = _load("report")
        if report is None or report.get("schema") != REPORT_SCHEMA:
            return None
        try:
            identity = verify_report_identity(report)
        except (TypeError, ValueError):
            return None
        if (
            snapshot.get("report_id") != identity.report_id
            or snapshot.get("report_sha256") != identity.report_sha256
        ):
            return None
    return snapshot


def load_v2_report_bundle() -> dict[str, Any] | None:
    """Return one V2 report plus its dashboard projection only when hashes match."""
    report = _load("report")
    dashboard = _load("dashboard")
    if report is None or dashboard is None or report.get("schema") != REPORT_SCHEMA:
        return None
    try:
        identity = verify_report_identity(report)
        if (
            dashboard.get("report_id") != identity.report_id
            or dashboard.get("report_sha256") != identity.report_sha256
        ):
            return None
        assert_same_report([report, {
            "schema": REPORT_SCHEMA,
            "report_id": dashboard["report_id"],
            "as_of_date": identity.as_of_date,
            "report_sha256": dashboard["report_sha256"],
        }])
    except (KeyError, TypeError, ValueError):
        return None
    return {"report": report, "dashboard": dashboard, "identity": identity}
