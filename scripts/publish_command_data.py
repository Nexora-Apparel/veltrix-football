"""Publish safe report/ledger snapshots to the public command-data branch.

Quota-safe recovery runs may republish previously generated artifacts without
requesting new fixtures or creating forecasts.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path, PurePosixPath
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


def _publish_large_blob(path: str, data: bytes, repo: str, token: str) -> None:
    """Publish large snapshots through Git Data API, avoiding Contents API payload limits."""
    root = f"{API_ROOT}/repos/{repo}"
    ref_url = f"{root}/git/ref/heads/{quote(BRANCH, safe='')}"
    update_url = f"{root}/git/refs/heads/{quote(BRANCH, safe='')}"
    # Concurrent workflow publishers can advance command-data between the
    # initial ref read and the final non-force update. Rebuild on the latest
    # parent and retry only optimistic-concurrency conflicts.
    for attempt_number in range(3):
        ref = _github_json(ref_url, token)
        head_sha = ref.get("object", {}).get("sha")
        if not isinstance(head_sha, str) or not head_sha:
            raise ValueError("Could not resolve command-data branch head.")
        head = _github_json(f"{root}/git/commits/{head_sha}", token)
        base_tree = head.get("tree", {}).get("sha")
        if not isinstance(base_tree, str) or not base_tree:
            raise ValueError("Could not resolve command-data base tree.")
        blob = _github_json(f"{root}/git/blobs", token, method="POST",
            body={"content": base64.b64encode(data).decode("ascii"), "encoding": "base64"})
        blob_sha = blob.get("sha")
        if not isinstance(blob_sha, str) or not blob_sha:
            raise ValueError("GitHub did not return a blob SHA.")
        tree = _github_json(f"{root}/git/trees", token, method="POST",
            body={"base_tree": base_tree, "tree": [
                {"path": path, "mode": "100644", "type": "blob", "sha": blob_sha}]})
        tree_sha = tree.get("sha")
        if not isinstance(tree_sha, str) or not tree_sha:
            raise ValueError("GitHub did not return a tree SHA.")
        commit = _github_json(f"{root}/git/commits", token, method="POST",
            body={"message": f"Publish latest Veltrix command data: {Path(path).name}",
                  "tree": tree_sha, "parents": [head_sha]})
        commit_sha = commit.get("sha")
        if not isinstance(commit_sha, str) or not commit_sha:
            raise ValueError("GitHub did not return a commit SHA.")
        try:
            _github_json(update_url, token, method="PATCH",
                body={"sha": commit_sha, "force": False})
            return
        except HTTPError as exc:
            if exc.code not in {409, 422} or attempt_number == 2:
                raise


def publish(path: str, local_file: Path, repo: str, token: str) -> None:
    pure_path = PurePosixPath(path)
    if pure_path.is_absolute() or ".." in pure_path.parts:
        raise ValueError("COMMAND_DATA_PATH_INVALID")
    canonical_path = pure_path.as_posix()
    if canonical_path in {
        "public-data/daily_predictions.json",
        "public-data/dashboard_snapshot.json",
    }:
        raise PermissionError(
            "LEGACY_PREDICTION_PUBLICATION_DISABLED; use the certified V2 bundle publisher"
        )
    data = local_file.read_bytes()
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    if len(data) > 900_000:
        _publish_large_blob(path, data, repo, token)
    else:
        encoded_path = quote(path, safe="/")
        url = f"{API_ROOT}/repos/{repo}/contents/{encoded_path}"
        current_sha = None
        try:
            existing = _github_json(f"{url}?ref={quote(BRANCH, safe='')}", token)
            if isinstance(existing.get("sha"), str):
                current_sha = existing["sha"]
                encoded_existing = existing.get("content")
                if existing.get("encoding") == "base64" and isinstance(encoded_existing, str):
                    try:
                        existing_bytes = base64.b64decode(encoded_existing, validate=False)
                    except (ValueError, TypeError):
                        raise ValueError("EXISTING_COMMAND_DATA_FILE_CONTENT_INVALID") from None
                    if existing_bytes == data:
                        print(f"Already published {path}; exact bytes match.")
                        return
        except HTTPError as exc:
            if exc.code != 404:
                raise
        payload = {"message": f"Publish latest Veltrix command data: {Path(path).name}",
                   "content": base64.b64encode(data).decode("ascii"), "branch": BRANCH}
        if current_sha:
            payload["sha"] = current_sha
        _github_json(url, token, method="PUT", body=payload)
    print(f"Published {path} ({len(data)} bytes).")

def _mark_report_publication(report: dict, published_at: datetime) -> None:
    """Record transport publication without erasing a reused-snapshot warning."""
    report["command_data_publication"] = "PUBLISHED"
    report["command_data_published_at_utc"] = published_at.isoformat()
    if report.get("publication_status") == "LIVE_REPORT_GENERATED_PENDING_PUBLICATION":
        report["publication_status"] = "PUBLISHED"
        report["publication_notice"] = (
            "Generated from this run's live fixture response; publication to command-data is confirmed."
        )


def _archive_report_path(report: dict, published_at: datetime) -> str:
    """Return an immutable UTC-stamped archive path for a dated report snapshot."""
    report_date = date.fromisoformat(str(report.get("as_of_date"))).isoformat()
    timestamp = published_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"public-data/archive/{report_date}/daily_predictions_{timestamp}.json"


def _archive_content_path(report: dict, report_bytes: bytes) -> str:
    """Return a content-addressed archive path so retries cannot create duplicates."""
    report_date = date.fromisoformat(str(report.get("as_of_date"))).isoformat()
    digest = hashlib.sha256(report_bytes).hexdigest()
    return f"public-data/archive/{report_date}/daily_predictions_{digest}.json"


def _valid_recent_cache(cache: object) -> bool:
    """Accept the active v2 resumable cache and legacy v1 caches during migration."""
    return (
        isinstance(cache, dict)
        and cache.get("version") in (1, 2)
        and isinstance(cache.get("matches"), list)
        and isinstance(cache.get("state"), dict)
    )


def _dashboard_snapshot(report: dict) -> dict:
    """Create a compact projection of the published report."""
    top_level = (
        "as_of_date", "generated_at_utc", "command_data_publication",
        "command_data_published_at_utc", "publication_status", "publication_notice",
        "primary_provider_request", "fixture_discovery", "multi_source_odds_sync",
        "live_odds_sync", "historical_data_coverage", "fixtures_received",
        "fixtures_with_market_odds", "goal_market_calibration", "value_bet_screen",
        "value_validation_certificate",
    )
    row_fields = (
        "fixture_id", "id", "match_id", "league", "country", "competition", "status", "fixture_phase", "fixture_visibility_note",
        "home_team", "away_team", "home_team_id", "away_team_id",
        "kickoff", "kickoff_local", "status", "fixture_phase",
        "fixture_visibility_note", "probabilities", "btts_yes", "over_2_5",
        "expected_goals", "prediction_basis", "five_dollar_market_odds",
        "the_odds_api_market_odds", "infer_sports_market_odds", "odds", "market_odds",
    )
    rows = report.get("predictions") if isinstance(report.get("predictions"), list) else []
    compact_rows = [{key: row[key] for key in row_fields if key in row} for row in rows if isinstance(row, dict)]
    payload = {key: report[key] for key in top_level if key in report}
    payload["predictions"] = compact_rows
    payload["snapshot_schema"] = "VELTRIX_DASHBOARD_V1"
    return payload

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Generated daily_predictions.json")
    parser.add_argument("--ledger", default=None, help="Validated paper_tracking_ledger.json (optional)")
    parser.add_argument("--recent-cache", default=None, help="Resumable recent-results cache (optional)")
    parser.add_argument("--value-evidence", default=None, help="Append-only shadow value evidence ledger (optional)")
    parser.add_argument("--archive-only", action="store_true", help="Preserve one historical report snapshot without publishing live report/dashboard pointers.")
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

    if args.archive_only:
        try:
            archive_path = _archive_content_path(report, report_path.read_bytes())
            publish(archive_path, report_path, repo, token)
            return 0
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Historical archive publication failed: {type(exc).__name__}", file=sys.stderr)
            return 1

    print(
        "LEGACY_COMMAND_DATA_PUBLISHER_DISABLED; use the certified V2 bundle publisher. "
        "Historical preservation is available only with --archive-only.",
        file=sys.stderr,
    )
    return 2



if __name__ == "__main__":
    raise SystemExit(main())
