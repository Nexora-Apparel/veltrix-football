"""Quota-free retrieval of saved GitHub Actions prediction artifacts.

Requires GITHUB_TOKEN (Actions: read) and GITHUB_REPOSITORY in the Vercel
environment. It reads existing artifacts only; it never runs a workflow or calls
the football provider. Results are cached briefly per warm function instance.
"""
from __future__ import annotations

import io
import json
import os
import time
import zipfile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
REPORT_NAMES = ("veltrix-daily-predictions", "daily-predictions", "daily_predictions", "daily-prediction-report", "prediction-report")
LEDGER_NAMES = ("veltrix-paper-ledger", "paper-tracking-ledger", "paper_tracking_ledger")
CACHE_SECONDS = 45
_cache: dict[str, tuple[float, dict[str, Any] | None]] = {}


def _request_json(url: str, token: str) -> dict[str, Any]:
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Veltrix-Football-Command-Centre",
    })
    with urlopen(request, timeout=4) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Unexpected GitHub API response")
    return value


def _read_artifact(repo: str, token: str, artifact_id: int) -> dict[str, Any] | None:
    request = Request(
        f"{API_ROOT}/repos/{repo}/actions/artifacts/{artifact_id}/zip",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Veltrix-Football-Command-Centre",
        },
    )
    with urlopen(request, timeout=6) as response:
        archive_bytes = response.read(8_000_001)
    if len(archive_bytes) > 8_000_000:
        return None
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        candidates = [name for name in archive.namelist() if name.lower().endswith(".json")]
        # Prefer the expected canonical report/ledger filename.
        preferred = ("daily_predictions.json", "paper_tracking_ledger.json")
        candidates.sort(key=lambda name: (0 if name.rsplit("/", 1)[-1] in preferred else 1, name))
        for name in candidates:
            try:
                payload = json.loads(archive.read(name).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError):
                continue
            if isinstance(payload, dict):
                return payload
    return None


def _load(kind: str) -> dict[str, Any] | None:
    now = time.monotonic()
    cached = _cache.get(kind)
    if cached and now - cached[0] < CACHE_SECONDS:
        return cached[1]

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    repo = (os.environ.get("GITHUB_REPOSITORY") or "Nexora-Apparel/veltrix-football").strip()
    if not token or "/" not in repo or any(part in repo for part in ("..", " ", "\\")):
        _cache[kind] = (now, None)
        return None

    names = REPORT_NAMES if kind == "report" else LEDGER_NAMES
    found: dict[str, Any] | None = None
    try:
        runs = _request_json(
            f"{API_ROOT}/repos/{repo}/actions/runs?branch=main&status=success&per_page=12",
            token,
        ).get("workflow_runs", [])
        if not isinstance(runs, list):
            runs = []
        for run in runs:
            run_id = run.get("id")
            if not isinstance(run_id, int):
                continue
            artifacts = _request_json(
                f"{API_ROOT}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
                token,
            ).get("artifacts", [])
            if not isinstance(artifacts, list):
                continue
            eligible = [
                artifact for artifact in artifacts
                if not artifact.get("expired")
                and str(artifact.get("name", "")).casefold() in names
                and isinstance(artifact.get("id"), int)
            ]
            for artifact in eligible:
                try:
                    found = _read_artifact(repo, token, artifact["id"])
                except (HTTPError, URLError, OSError, ValueError, zipfile.BadZipFile, json.JSONDecodeError):
                    found = None
                if found is not None and (
                    kind != "report" or isinstance(found.get("predictions"), list)
                ) and (
                    kind != "ledger" or isinstance(found.get("cumulative_metrics_by_model"), dict)
                ):
                    break
                found = None
            if found is not None:
                break
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError, TimeoutError):
        found = None

    _cache[kind] = (time.monotonic(), found)
    return found


def load_latest_report() -> dict[str, Any] | None:
    """Load the latest successful, unexpired daily prediction report artifact."""
    return _load("report")


def load_paper_ledger() -> dict[str, Any] | None:
    """Load the latest successful, unexpired cumulative paper ledger artifact."""
    return _load("ledger")
