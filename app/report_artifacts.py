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
_TIMEOUT_SECONDS = 5
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
    # Query the GitHub Contents API with its raw media type. Unlike the raw
    # branch CDN URL, this avoids stale CDN snapshots after publication.
    cache_buster = int(time.time())
    url = (
        f"https://api.github.com/repos/{repo}/contents/public-data/{filename}"
        f"?ref={branch}&v={cache_buster}"
    )
    request = Request(url, headers={
        "User-Agent": "Veltrix-Football-Command-Centre",
        "Accept": "application/vnd.github.raw+json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    value: dict[str, Any] | None = None
    try:
        with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read(4_000_001)
        if len(raw) <= 4_000_000:
            # The raw media type normally returns JSON bytes. Keep a fallback
            # for GitHub/API proxies that return the standard base64 envelope.
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict) and isinstance(parsed.get("content"), str) and parsed.get("encoding") == "base64":
                decoded = base64.b64decode(parsed["content"])
                parsed = json.loads(decoded.decode("utf-8"))
            if isinstance(parsed, dict):
                if kind == "report" and isinstance(parsed.get("predictions"), list) and parsed.get("status") != "NOT_YET_PUBLISHED":
                    value = parsed
                elif kind == "ledger" and isinstance(parsed.get("cumulative_metrics_by_model"), dict) and parsed.get("model_status") == "PAPER_TRACKING_ONLY":
                    value = parsed
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
