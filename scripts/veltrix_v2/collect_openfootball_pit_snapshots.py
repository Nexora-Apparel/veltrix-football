#!/usr/bin/env python3
"""Collect immutable, rights-qualified OpenFootball result snapshots."""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from veltrix_v2.providers.openfootball_archive import parse_archive

APPROVAL_ID = "approval-openfootball-cc0-archive-2026-11-15"
SPDX_REQUIRED = "CC0-1.0"
USER_AGENT = "VELTRIX-FOOTBALL-2.0 historical archive evidence collector"
SOURCE_SPECS = (
    ("openfootball/england", "2024-25/1-premierleague.txt", "OPENFOOTBALL_EPL_2024_25"),
    ("openfootball/england", "2025-26/1-premierleague.txt", "OPENFOOTBALL_EPL_2025_26"),
    ("openfootball/england", "2026-27/1-premierleague.txt", "OPENFOOTBALL_EPL_2026_27"),
    ("openfootball/espana", "2024-25/1-liga.txt", "OPENFOOTBALL_ESP_LALIGA_2024_25"),
    ("openfootball/espana", "2025-26/1-liga.txt", "OPENFOOTBALL_ESP_LALIGA_2025_26"),
    ("openfootball/espana", "2026-27/1-liga.txt", "OPENFOOTBALL_ESP_LALIGA_2026_27"),
    ("openfootball/deutschland", "2024-25/1-bundesliga.txt", "OPENFOOTBALL_DE_BUNDESLIGA_2024_25"),
    ("openfootball/deutschland", "2025-26/1-bundesliga.txt", "OPENFOOTBALL_DE_BUNDESLIGA_2025_26"),
    ("openfootball/deutschland", "2026-27/1-bundesliga.txt", "OPENFOOTBALL_DE_BUNDESLIGA_2026_27"),
    ("openfootball/italy", "2024-25/1-seriea.txt", "OPENFOOTBALL_IT_SERIE_A_2024_25"),
    ("openfootball/italy", "2025-26/1-seriea.txt", "OPENFOOTBALL_IT_SERIE_A_2025_26"),
    ("openfootball/italy", "2026-27/1-seriea.txt", "OPENFOOTBALL_IT_SERIE_A_2026_27"),
)

def aware(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("SOURCE_COMMIT_TIMESTAMP_MISSING")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("SOURCE_COMMIT_TIMESTAMP_MUST_BE_AWARE")
    return parsed.astimezone(timezone.utc)

def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()

def valid_sha(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{40}", value))

class RequestBudget:
    def __init__(self, maximum: int):
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
            raise ValueError("MAX_REQUESTS_INVALID")
        self.maximum, self.used = maximum, 0
    def consume(self):
        if self.used >= self.maximum:
            raise RuntimeError("ARCHIVE_REQUEST_BUDGET_EXCEEDED")
        self.used += 1

def http_get(url: str, *, token: str | None, budget: RequestBudget):
    budget.consume()
    headers = {"User-Agent": USER_AGENT}
    if "api.github.com/" in url:
        headers["Accept"] = "application/vnd.github+json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return response.read(), {k.casefold(): v for k, v in response.headers.items()}

def read_json(url: str, *, token: str | None, budget: RequestBudget):
    raw, headers = http_get(url, token=token, budget=budget)
    try:
        return json.loads(raw.decode("utf-8")), headers
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("GITHUB_JSON_RESPONSE_INVALID") from None

def list_path_commits(repo: str, path: str, *, token: str | None, budget: RequestBudget, maximum: int):
    commits, page, complete = [], 1, False
    while len(commits) < maximum:
        url = f"https://api.github.com/repos/{repo}/commits?path={quote(path, safe='/')}&per_page=100&page={page}"
        payload, headers = read_json(url, token=token, budget=budget)
        if not isinstance(payload, list):
            raise RuntimeError("GITHUB_COMMIT_HISTORY_RESPONSE_INVALID")
        commits.extend(payload)
        has_next = "rel=\"next\"" in headers.get("link", "")
        if len(payload) < 100 or not has_next:
            complete = True
            break
        page += 1
    if len(commits) >= maximum and not complete:
        raise RuntimeError("COMMIT_HISTORY_LIMIT_REACHED_REFUSING_PARTIAL_HISTORY")
    return commits, complete

def collect_snapshots(
    *, output_dir: Path, imported_at: datetime, max_requests: int = 500,
    max_commits_per_source: int = 100, token: str | None = None,
    sources: tuple[tuple[str, str, str], ...] = SOURCE_SPECS,
    read_json: Callable | None = None, read_bytes: Callable | None = None,
) -> dict:
    if imported_at.tzinfo is None or imported_at.utcoffset() is None:
        raise ValueError("IMPORT_TIMESTAMP_MUST_BE_AWARE")
    if not 1 <= max_commits_per_source <= 100:
        raise ValueError("MAX_COMMITS_PER_SOURCE_OUT_OF_RANGE")
    budget = RequestBudget(max_requests)
    custom_transport = read_json is not None or read_bytes is not None
    if read_json is None:
        read_json = lambda url: read_json_default(url, token, budget)
    if read_bytes is None:
        read_bytes = lambda url: http_get(url, token=token, budget=budget)[0]

    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    repo_metadata, versions, snapshots = {}, {}, []
    source_reports, failures = [], []

    for repo, source_path, competition_id in sources:
        try:
            if repo not in repo_metadata:
                metadata = read_json(f"https://api.github.com/repos/{repo}")
                license_info = metadata.get("license") if isinstance(metadata, dict) else None
                if not isinstance(license_info, dict) or license_info.get("spdx_id") != SPDX_REQUIRED:
                    raise RuntimeError("SOURCE_LICENSE_NOT_CC0_1_0")
                repo_metadata[repo] = {
                    "spdx_id": SPDX_REQUIRED,
                    "license_name": license_info.get("name"),
                    "license_url": license_info.get("url"),
                    "repository_html_url": metadata.get("html_url"),
                }
            if custom_transport:
                commits = read_json(
                    f"https://api.github.com/repos/{repo}/commits?path={quote(source_path, safe='/')}&per_page=100"
                )
                history_complete = len(commits) < max_commits_per_source
            else:
                commits, history_complete = list_path_commits(
                    repo, source_path, token=token, budget=budget, maximum=max_commits_per_source
                )
            if not isinstance(commits, list):
                raise RuntimeError("SOURCE_COMMIT_LIST_INVALID")
            if not commits:
                raise RuntimeError("SOURCE_COMMIT_HISTORY_EMPTY")
            if len(commits) >= max_commits_per_source and not history_complete:
                raise RuntimeError("COMMIT_HISTORY_LIMIT_REACHED_REFUSING_PARTIAL_HISTORY")

            ordered = sorted(commits, key=lambda row: (
                aware(row.get("commit", {}).get("committer", {}).get("date", "")).timestamp(),
                row.get("sha", ""),
            ))
            accepted_snapshots = parsed_versions = 0
            for revision_order, commit in enumerate(ordered):
                sha = commit.get("sha")
                if not valid_sha(sha):
                    raise RuntimeError("SOURCE_COMMIT_SHA_INVALID")
                commit_obj = commit.get("commit")
                committer = commit_obj.get("committer") if isinstance(commit_obj, dict) else None
                snapshot_at = aware(committer.get("date", "") if isinstance(committer, dict) else "")
                raw_url = f"https://raw.githubusercontent.com/{repo}/{sha}/{source_path}"
                raw = read_bytes(raw_url)
                if not isinstance(raw, bytes) or not raw:
                    raise RuntimeError("SOURCE_SNAPSHOT_EMPTY")
                try:
                    source_text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raise RuntimeError("SOURCE_SNAPSHOT_NOT_UTF8") from None
                content_sha = hashlib.sha256(raw).hexdigest()
                archive = parse_archive(
                    source_text, competition_id=competition_id, source_path=source_path,
                    source_id=repo, snapshot_commit_sha=sha, snapshot_available_at=snapshot_at,
                    imported_at=imported_at,
                )
                if not archive.observations:
                    continue
                proof = {
                    "source_repository": repo, "source_path": source_path,
                    "competition_id": competition_id,
                    "source_commit_sha": sha,
                    "source_snapshot_available_at": snapshot_at.isoformat(),
                    "source_content_sha256": content_sha,
                    "source_license_spdx": SPDX_REQUIRED,
                    "source_license_url": repo_metadata[repo]["license_url"],
                    "rights_approval_id": APPROVAL_ID,
                }
                proof_id = canonical_hash(proof)
                safe_name = (
                    f"{repo.replace('/', '__')}--{hashlib.sha256(source_path.encode()).hexdigest()[:12]}--{sha}.txt"
                )
                stored_path = snapshot_dir / safe_name
                stored_path.write_bytes(raw)
                snapshots.append({
                    **proof, "archive_proof_id": proof_id,
                    "stored_snapshot_path": str(stored_path.relative_to(output_dir)),
                    "fixture_line_count": archive.fixture_line_count,
                    "result_count": archive.result_count,
                    "rejected_result_count": archive.rejected_result_count,
                    "rejected_annotations": list(archive.rejected_annotations),
                    "revision_history_complete": history_complete,
                    "source_revision_order": revision_order,
                })
                accepted_snapshots += 1
                parsed_versions += archive.result_count
                for item in archive.observations:
                    row = {
                        "fixture_id": item.fixture_id,
                        "competition_id": item.competition_id,
                        "home_team_id": item.home_team_id,
                        "away_team_id": item.away_team_id,
                        "kickoff_at": None,
                        "kickoff_date": item.kickoff_date.isoformat(),
                        "home_goals": item.home_goals,
                        "away_goals": item.away_goals,
                        "provider": item.provider,
                        "source_id": item.source_id,
                        "availability_basis": item.availability_basis,
                        "available_at": item.available_at.isoformat(),
                        "recorded_at": item.recorded_at.isoformat(),
                        "point_in_time_certifiable": item.point_in_time_certifiable,
                        "payload_sha256": item.payload_sha256,
                        "source_repository": repo,
                        "source_path": source_path,
                        "source_commit_sha": sha,
                        "source_commit_timestamp": snapshot_at.isoformat(),
                        "source_content_sha256": content_sha,
                        "source_license_spdx": SPDX_REQUIRED,
                        "rights_approval_id": APPROVAL_ID,
                        "archive_proof_id": proof_id,
                        "source_published_at": snapshot_at.isoformat(),
                        "source_timestamp_basis": "archival_snapshot_timestamp",
                        "retrieved_at": imported_at.isoformat(),
                        "temporal_semantics": "state_as_of_cutoff",
                        "revision_history_complete": history_complete,
                        "source_revision_order": revision_order,
                    }
                    key = (item.fixture_id, item.payload_sha256)
                    prior = versions.get(key)
                    if prior is None or (row["available_at"], row["source_commit_sha"]) < (
                        prior["available_at"], prior["source_commit_sha"]
                    ):
                        versions[key] = row

            source_reports.append({
                "repository": repo, "source_path": source_path,
                "competition_id": competition_id,
                "source_license_spdx": SPDX_REQUIRED,
                "commit_history_complete": history_complete,
                "commit_count_seen": len(commits),
                "snapshot_count_with_eligible_results": accepted_snapshots,
                "parsed_result_versions_before_dedup": parsed_versions,
            })
        except Exception as exc:
            failures.append({
                "repository": repo, "source_path": source_path,
                "competition_id": competition_id,
                "error_code": str(exc).split(":", 1)[0][:120],
            })

    observations = sorted(versions.values(), key=lambda row: (
        row["competition_id"], row["kickoff_date"], row["fixture_id"],
        row["available_at"], row["source_commit_sha"],
    ))
    payload = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        for row in observations
    ).encode("utf-8")
    (output_dir / "observations.jsonl").write_bytes(payload)
    manifest = {
        "schema_version": "veltrix-openfootball-pit-snapshot-pack-v1",
        "generated_at": imported_at.isoformat(),
        "rights_approval_id": APPROVAL_ID,
        "rights_basis": "OPEN_LICENSE_CC0_1_0",
        "permitted_uses": ["COLLECTION", "STORAGE", "HISTORICAL_IMPORT", "MODEL_TRAINING", "BENCHMARKING"],
        "raw_redistribution_allowed": False,
        "attribution_required_by_license": False,
        "source_count": len(sources),
        "source_reports": source_reports,
        "failed_sources": failures,
        "snapshot_count": len(snapshots),
        "observation_version_count": len(observations),
        "observations_sha256": hashlib.sha256(payload).hexdigest(),
        "snapshots": snapshots,
        "request_count": budget.used,
        "request_budget": budget.maximum,
        "all_sources_succeeded": not failures and len(source_reports) == len(sources),
        "historical_walk_forward_note": (
            "Verify each archive_proof_id and exact source bytes. The current model evaluator "
            "still requires recorded_at <= cutoff; retrospective archive-proof integration is separate."
        ),
        "provider_crosswalk_note": (
            "Competition and team IDs are source-scoped. Do not join to 5Dollar until exact "
            "evidence-backed competition and team crosswalks exist."
        ),
        "database_written": False, "production_written": False,
        "telegram_sent": False, "schedule_activated": False, "public_publication": False,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest

def read_json_default(url: str, token: str | None, budget: RequestBudget):
    return read_json_http(url, token, budget)

def read_json_http(url: str, token: str | None, budget: RequestBudget):
    raw, _ = http_get(url, token=token, budget=budget)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("GITHUB_JSON_RESPONSE_INVALID") from None

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-requests", type=int, default=500)
    parser.add_argument("--max-commits-per-source", type=int, default=100)
    args = parser.parse_args()
    manifest = collect_snapshots(
        output_dir=Path(args.output_dir), imported_at=datetime.now(timezone.utc),
        max_requests=args.max_requests, max_commits_per_source=args.max_commits_per_source,
        token=os.getenv("GITHUB_TOKEN"),
    )
    print(json.dumps({
        "manifest": str(Path(args.output_dir) / "manifest.json"),
        "observations": str(Path(args.output_dir) / "observations.jsonl"),
        "snapshot_count": manifest["snapshot_count"],
        "observation_version_count": manifest["observation_version_count"],
        "failed_source_count": len(manifest["failed_sources"]),
        "request_count": manifest["request_count"],
        "all_sources_succeeded": manifest["all_sources_succeeded"],
    }, sort_keys=True))
    return 0 if manifest["all_sources_succeeded"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
