"""Publish safe report/ledger snapshots to the public command-data branch.

Quota-safe recovery runs may republish previously generated artifacts without
requesting new fixtures or creating forecasts.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
BRANCH = os.getenv("VELTRIX_DATA_BRANCH", "command-data")


def _github_json(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Veltrix-Command-Data-Publisher",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub returned an unexpected response.")
    return payload


def publish(path: str, local_file: Path, repo: str, token: str) -> None:
    data = local_file.read_bytes()
    if len(data) > 4_000_000:
        raise ValueError(f"{path} exceeds the 4 MB publication limit.")
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    encoded_path = quote(path, safe="/")
    url = f"{API_ROOT}/repos/{repo}/contents/{encoded_path}"
    current_sha = None
    try:
        existing = _github_json(f"{url}?ref={quote(BRANCH, safe='')}", token)
        if isinstance(existing.get("sha"), str):
            current_sha = existing["sha"]
    except HTTPError as exc:
        if exc.code != 404:
            raise

    payload = {
        "message": f"Publish latest Veltrix command data: {Path(path).name}",
        "content": base64.b64encode(data).decode("ascii"),
        "branch": BRANCH,
    }
    if current_sha:
        payload["sha"] = current_sha
    _github_json(url, token, method="PUT", body=payload)
    print(f"Published {path} ({len(data)} bytes).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Generated daily_predictions.json")
    parser.add_argument("--ledger", default=None, help="Validated paper_tracking_ledger.json (optional)")
    parser.add_argument("--recent-cache", default=None, help="Resumable recent-results cache (optional)")
    args = parser.parse_args()

    repo = (os.getenv("GITHUB_REPOSITORY") or "").strip()
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
        print("Publication skipped: GitHub repository/token context is unavailable.", file=sys.stderr)
        return 2

    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not isinstance(report.get("predictions"), list) or not report.get("as_of_date"):
        print("Publication refused: report failed structural validation.", file=sys.stderr)
        return 2

    try:
        # Separate transport publication from snapshot freshness: reused reports
        # must retain their explicit reuse warning while still reporting that the
        # command-data branch received this exact snapshot.
        report["command_data_publication"] = "PUBLISHED"
        report["command_data_published_at_utc"] = datetime.now(timezone.utc).isoformat()
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        publish("public-data/daily_predictions.json", report_path, repo, token)
        if args.ledger:
            ledger_path = Path(args.ledger)
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            if (
                not isinstance(ledger, dict)
                or ledger.get("model_status") != "PAPER_TRACKING_ONLY"
                or not isinstance(ledger.get("cumulative_metrics_by_model"), dict)
            ):
                # Keep the last known-good published ledger rather than replacing
                # it with an incomplete first-run/error document.
                print("Ledger publication skipped: ledger failed structural validation.", file=sys.stderr)
            else:
                publish("public-data/paper_tracking_ledger.json", ledger_path, repo, token)
        if args.recent_cache:
            cache_path = Path(args.recent_cache)
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                isinstance(cache, dict)
                and cache.get("version") == 1
                and isinstance(cache.get("matches"), list)
                and isinstance(cache.get("state"), dict)
            ):
                publish("public-data/recent_results_cache.json", cache_path, repo, token)
            else:
                print("Recent-results cache publication skipped: cache schema validation failed.", file=sys.stderr)
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        # Never print request headers or the GitHub token.
        print(f"Command-data publication failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
