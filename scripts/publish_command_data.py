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
from datetime import date, datetime, timezone
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
    data = local_file.read_bytes()
    parsed = json.loads(data.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    normalized_path = path.replace("\\", "/").rsplit("/", 1)[-1]
    if normalized_path in {"daily_predictions.json", "dashboard_snapshot.json"}:
        if not is_publishable_independent_report(parsed):
            raise ValueError("LEGACY_OR_UNCERTIFIED_REPORT_PUBLICATION_BLOCKED")
        if not is_value_betting_authorized_report(parsed):
            parsed.pop("value_bet_screen", None)
            parsed.pop("value_validation_certificate", None)
            rows = parsed.get("predictions")
            if isinstance(rows, list):
                parsed["predictions"] = [
                    {key: value for key, value in row.items() if key != "value_bet_screen"}
                    if isinstance(row, dict) else row
                    for row in rows
                ]
    elif normalized_path == "paper_tracking_ledger.json" and not is_independent_paper_ledger(parsed):
        raise ValueError("LEGACY_PAPER_LEDGER_PUBLICATION_BLOCKED")
    elif normalized_path == "model_validation_report.json" and not is_independent_model_validation(parsed):
        raise ValueError("LEGACY_MODEL_VALIDATION_PUBLICATION_BLOCKED")
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
        "report_schema", "model_portfolio_id", "legacy_model_dependency",
        "publication_allowed", "release_certificate", "value_betting_authorized",
        "as_of_date", "generated_at_utc", "command_data_publication",
        "command_data_published_at_utc", "publication_status", "publication_notice",
        "primary_provider_request", "fixture_discovery", "multi_source_odds_sync",
        "live_odds_sync", "historical_data_coverage", "fixtures_received",
        "fixtures_with_market_odds", "goal_market_calibration",
    )
    row_fields = (
        "fixture_id", "id", "match_id", "league", "country", "competition", "status", "fixture_phase", "fixture_visibility_note",
        "home_team", "away_team", "home_team_id", "away_team_id",
        "kickoff", "kickoff_local", "status", "fixture_phase",
        "fixture_visibility_note", "probabilities", "btts_yes", "over_2_5",
        "expected_goals", "prediction_basis", "five_dollar_market_odds",
        "the_odds_api_market_odds", "infer_sports_market_odds", "odds", "market_odds",
    )
    value_authorized = is_value_betting_authorized_report(report)
    if value_authorized:
        top_level = top_level + ("value_bet_screen", "value_validation_certificate")
        row_fields = row_fields + ("value_bet_screen",)
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
    if not is_publishable_independent_report(report):
        print("Publication refused: legacy or uncertified independent report.", file=sys.stderr)
        return 2

    errors: list[str] = []

    def attempt(label: str, action) -> None:
        try:
            action()
        except HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", "replace")[:500]
            except Exception:
                detail = ""
            errors.append(f"{label}: HTTP {exc.code} {detail}".strip())
            print(f"Publication failed for {label}: HTTP {exc.code} {detail}".strip(), file=sys.stderr)
        except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{label}: {type(exc).__name__}")
            print(f"Publication failed for {label}: {type(exc).__name__}", file=sys.stderr)

    try:
        # Separate transport publication from snapshot freshness: reused reports
        # must retain their explicit reuse warning while still reporting that the
        # command-data branch received this exact snapshot.
        published_at = datetime.now(timezone.utc)
        _mark_report_publication(report, published_at)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        attempt("daily report", lambda: publish("public-data/daily_predictions.json", report_path, repo, token))
        dashboard_path = report_path.parent / "dashboard_snapshot.json"
        dashboard_path.write_text(json.dumps(_dashboard_snapshot(report), separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        attempt("compact dashboard snapshot", lambda: publish("public-data/dashboard_snapshot.json", dashboard_path, repo, token))
        archive_path = _archive_report_path(report, published_at)
        attempt("report archive", lambda: publish(archive_path, report_path, repo, token))
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
                attempt("paper tracking ledger", lambda: publish("public-data/paper_tracking_ledger.json", ledger_path, repo, token))
        if args.value_evidence:
            evidence_path = Path(args.value_evidence)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            if (
                isinstance(evidence, dict)
                and evidence.get("version") == "VELTRIX_VALUE_EVIDENCE_V1"
                and evidence.get("release_status") == "LOCKED_SHADOW_MODE"
                and isinstance(evidence.get("observations"), list)
            ):
                attempt("value evidence ledger", lambda: publish("public-data/value_evidence_ledger.json", evidence_path, repo, token))
            else:
                print("Value evidence publication skipped: ledger schema or release lock validation failed.", file=sys.stderr)
        if args.recent_cache:
            cache_path = Path(args.recent_cache)
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            # Recent-results cache v2 is the active resumable schema. Accept v1
            # only for backward-compatible migration; otherwise the cursor and
            # historical matches would never be published for the next run.
            if _valid_recent_cache(cache):
                attempt("recent-results cache", lambda: publish("public-data/recent_results_cache.json", cache_path, repo, token))
            else:
                print("Recent-results cache publication skipped: cache schema validation failed.", file=sys.stderr)
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Command-data publication failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    if errors:
        print(f"Command-data publication completed with {len(errors)} failed snapshot(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
