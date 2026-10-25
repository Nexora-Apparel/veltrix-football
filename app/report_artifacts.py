"""Read the latest published command data from the public data branch.

This reads existing JSON snapshots only. It does not start prediction workflows,
download GitHub Actions artifacts, or call the football provider.
"""
from __future__ import annotations

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
_TIMEOUT_SECONDS = 3
_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}


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

    filename = "daily_predictions.json" if kind == "report" else "paper_tracking_ledger.json"
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/public-data/{filename}"
    request = Request(url, headers={"User-Agent": "Veltrix-Football-Command-Centre"})
    value: dict[str, Any] | None = None
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read(4_000_001)
        if len(raw) <= 4_000_000:
            parsed = json.loads(raw.decode("utf-8"))
            if isinstance(parsed, dict):
                if kind == "report" and isinstance(parsed.get("predictions"), list) and parsed.get("status") != "NOT_YET_PUBLISHED":
                    value = parsed
                elif kind == "ledger" and isinstance(parsed.get("cumulative_metrics_by_model"), dict) and parsed.get("model_status") == "PAPER_TRACKING_ONLY":
                    value = parsed
    except (HTTPError, URLError, OSError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        value = None

    _cache[kind] = (time.monotonic(), value)
    return value


def load_latest_report() -> dict[str, Any] | None:
    """Load the most recently published prediction report, if one exists."""
    return _load("report")


def load_paper_ledger() -> dict[str, Any] | None:
    """Load the published cumulative paper-tracking ledger, if one exists."""
    return _load("ledger")
