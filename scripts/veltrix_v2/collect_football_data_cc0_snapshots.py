#!/usr/bin/env python3
"""Collect CC0 Brazil Serie B JSON snapshots by immutable Git commit."""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.veltrix_v2.collect_openfootball_pit_snapshots import (
    RequestBudget, aware, canonical_hash, http_get, list_path_commits, read_json_default,
)
from veltrix_v2.providers.football_data_cc0.parser import parse_json_archive

APPROVAL_ID = "approval-ferrerasrp-footballdata-cc0-2026-11-15"
REPOSITORY = "FerrerasRP/FootballData"
SPDX_REQUIRED = "CC0-1.0"
SOURCE_SPECS = (
    (REPOSITORY, "database/brasil-serie-b/brasil-serie-b 2025.json", "FOOTBALLDATA_BR_SERIE_B_2025"),
    (REPOSITORY, "database/brasil-serie-b/brasil-serie-b 2026.json", "FOOTBALLDATA_BR_SERIE_B_2026"),
)

def _aware_datetime(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("IMPORT_TIMESTAMP_MUST_BE_AWARE")
    return value.astimezone(timezone.utc)

def collect(*, output_dir: Path, imported_at: datetime, max_requests: int = 100,
            max_commits_per_source: int = 100, token: str | None = None) -> dict:
    imported_at = _aware_datetime(imported_at)
    budget = RequestBudget(max_requests)
    metadata = read_json_default(f"https://api.github.com/repos/{REPOSITORY}", token, budget)
    license_info = metadata.get("license") if isinstance(metadata, dict) else None
    if not isinstance(license_info, dict) or license_info.get("spdx_id") != SPDX_REQUIRED:
        raise RuntimeError("SOURCE_LICENSE_NOT_CC0_1_0")
    license_url = license_info.get("url")
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    versions, snapshots, reports, failures = {}, [], [], []

    for repo, path, comp in SOURCE_SPECS:
        try:
            commits, history_complete = list_path_commits(
                repo, path, token=token, budget=budget, maximum=max_commits_per_source
            )
            if not commits:
                raise RuntimeError("SOURCE_COMMIT_HISTORY_EMPTY")
            ordered = sorted(commits, key=lambda x: (
                aware(x.get("commit", {}).get("committer", {}).get("date", "")),
                x.get("sha", ""),
            ))
            parsed_total = rejected_total = not_yet_total = stored_count = 0
            for revision_order, commit in enumerate(ordered):
                sha = commit.get("sha")
                if not isinstance(sha, str) or len(sha) != 40:
                    raise RuntimeError("SOURCE_COMMIT_SHA_INVALID")
                snapshot_at = aware(commit.get("commit", {}).get("committer", {}).get("date", ""))
                raw_url = f"https://raw.githubusercontent.com/{repo}/{sha}/{quote(path, safe='/')}"
                raw, _ = http_get(raw_url, token=token, budget=budget)
                if not raw:
                    raise RuntimeError("SOURCE_SNAPSHOT_EMPTY")
                try:
                    source_text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    raise RuntimeError("SOURCE_SNAPSHOT_NOT_UTF8") from None
                content_sha = hashlib.sha256(raw).hexdigest()
                archive = parse_json_archive(
                    source_text, competition_id=comp, source_path=path,
                    snapshot_commit_sha=sha, snapshot_available_at=snapshot_at,
                    imported_at=imported_at,
                )
                parsed_total += archive.result_count
                rejected_total += archive.rejected_result_count
                not_yet_total += archive.not_yet_eligible_count
                if not archive.observations:
                    continue
                proof = {
                    "source_repository": repo, "source_path": path, "competition_id": comp,
                    "source_commit_sha": sha, "source_snapshot_available_at": snapshot_at.isoformat(),
                    "source_content_sha256": content_sha, "source_license_spdx": SPDX_REQUIRED,
                    "source_license_url": license_url, "rights_approval_id": APPROVAL_ID,
                    "source_format": "football_data_json",
                }
                proof_id = canonical_hash(proof)
                filename = f"ferrerasrp-footballdata--{hashlib.sha256(path.encode()).hexdigest()[:12]}--{sha}.json"
                stored = snapshot_dir / filename
                stored.write_bytes(raw)
                snapshots.append({
                    **proof, "archive_proof_id": proof_id,
                    "stored_snapshot_path": str(stored.relative_to(output_dir)),
                    "fixture_line_count": archive.fixture_line_count,
                    "result_count": archive.result_count,
                    "rejected_result_count": archive.rejected_result_count,
                    "not_yet_eligible_count": archive.not_yet_eligible_count,
                    "rejected_annotations": list(archive.rejected_annotations),
                    "team_name_normalizations": list(archive.team_name_normalizations),
                    "revision_history_complete": history_complete,
                    "source_revision_order": revision_order,
                    "snapshot_age_days_at_collection": max(0, (imported_at - snapshot_at).days),
                })
                stored_count += 1
                for item in archive.observations:
                    row = {
                        "fixture_id": item.fixture_id, "competition_id": item.competition_id,
                        "home_team_id": item.home_team_id, "away_team_id": item.away_team_id,
                        "home_team_name": item.home_team_name, "away_team_name": item.away_team_name,
                        "kickoff_at": None, "kickoff_date": item.kickoff_date.isoformat(),
                        "source_reported_local_time": item.source_reported_local_time,
                        "source_timezone": item.source_timezone,
                        "home_goals": item.home_goals, "away_goals": item.away_goals,
                        "round_name": item.round_name, "provider": item.provider, "source_id": item.source_id,
                        "availability_basis": item.availability_basis,
                        "available_at": item.available_at.isoformat(), "recorded_at": item.recorded_at.isoformat(),
                        "point_in_time_certifiable": item.point_in_time_certifiable,
                        "payload_sha256": item.payload_sha256, "source_row_index": item.source_row_index,
                        "team_name_normalizations": list(item.team_name_normalizations),
                        "source_repository": repo, "source_path": path, "source_commit_sha": sha,
                        "source_commit_timestamp": snapshot_at.isoformat(), "source_content_sha256": content_sha,
                        "source_license_spdx": SPDX_REQUIRED, "rights_approval_id": APPROVAL_ID,
                        "archive_proof_id": proof_id, "source_published_at": None,
                        "source_timestamp_basis": "unverified_repository_commit_timestamp",
                        "retrieved_at": imported_at.isoformat(), "temporal_semantics": "state_as_of_cutoff",
                        "revision_history_complete": history_complete, "source_revision_order": revision_order,
                    }
                    key = (item.fixture_id, item.payload_sha256)
                    previous = versions.get(key)
                    if previous is None or (row["available_at"], row["source_commit_sha"]) < (
                        previous["available_at"], previous["source_commit_sha"]
                    ):
                        versions[key] = row
            reports.append({
                "repository": repo, "source_path": path, "competition_id": comp,
                "source_license_spdx": SPDX_REQUIRED, "commit_history_complete": history_complete,
                "commit_count_seen": len(commits), "snapshot_count_with_eligible_results": stored_count,
                "parsed_result_versions_before_dedup": parsed_total,
                "rejected_result_count": rejected_total, "not_yet_eligible_count": not_yet_total,
            })
        except Exception as exc:
            failures.append({"repository": repo, "source_path": path, "competition_id": comp,
                             "error_code": str(exc).split(":", 1)[0][:120]})

    observations = sorted(versions.values(), key=lambda x: (
        x["competition_id"], x["kickoff_date"], x["fixture_id"], x["available_at"], x["source_commit_sha"]
    ))
    payload = "".join(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
                      for x in observations).encode("utf-8")
    (output_dir / "observations.jsonl").write_bytes(payload)
    manifest = {
        "schema_version": "veltrix-footballdata-cc0-snapshot-pack-v1",
        "generated_at": imported_at.isoformat(), "rights_approval_id": APPROVAL_ID,
        "rights_basis": "OPEN_LICENSE_CC0_1_0",
        "permitted_uses": ["COLLECTION", "STORAGE", "HISTORICAL_IMPORT", "MODEL_TRAINING", "BENCHMARKING"],
        "source_count": len(SOURCE_SPECS), "source_reports": reports, "failed_sources": failures,
        "snapshot_count": len(snapshots), "observation_version_count": len(observations),
        "observations_sha256": hashlib.sha256(payload).hexdigest(), "snapshots": snapshots,
        "request_count": budget.used, "request_budget": budget.maximum,
        "all_sources_succeeded": not failures and len(reports) == len(SOURCE_SPECS),
        "source_timezone_note": "match_date contains a reported clock string but no timezone; kickoff_at remains null and the clock is preserved as source_reported_local_time only.",
        "source_freshness_note": "2025 source file has two revisions; 2026 file has one snapshot dated 2026-07-08. Freshness must be evaluated before current-form use.",
        "provider_crosswalk_note": "Source-scoped team/competition IDs; no cross-provider joins until evidence-backed crosswalks exist.",
        "database_written": False, "production_written": False, "telegram_sent": False,
        "schedule_activated": False, "public_publication": False,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-requests", type=int, default=100)
    parser.add_argument("--max-commits-per-source", type=int, default=100)
    args = parser.parse_args()
    manifest = collect(
        output_dir=Path(args.output_dir), imported_at=datetime.now(timezone.utc),
        max_requests=args.max_requests, max_commits_per_source=args.max_commits_per_source,
        token=os.getenv("GITHUB_TOKEN"),
    )
    print(json.dumps({
        "snapshot_count": manifest["snapshot_count"],
        "observation_version_count": manifest["observation_version_count"],
        "failed_source_count": len(manifest["failed_sources"]),
        "request_count": manifest["request_count"],
        "all_sources_succeeded": manifest["all_sources_succeeded"],
    }, sort_keys=True))
    return 0 if manifest["all_sources_succeeded"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
