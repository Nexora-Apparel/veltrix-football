"""Publish a small CI/live verification receipt to the command-data branch."""
from __future__ import annotations

import argparse
import base64
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


BRANCH = "command-data"
PATH = "public-data/verification_status.json"


def build_status(env: dict[str, str]) -> dict:
    keys = (
        "unit_tests", "dashboard_js", "fixture_generation", "fixture_visibility",
        "value_evidence_update", "telegram_delivery", "command_data_publication",
        "paper_tracking",
    )
    steps = {key: env.get("VELTRIX_STEP_" + key.upper(), "not_run") for key in keys}
    critical = ("unit_tests", "dashboard_js")
    passed = all(steps[key] == "success" for key in critical)
    live = steps["fixture_generation"] == "success"
    if steps["fixture_generation"] not in {"success", "skipped"}:
        passed = False
    if live:
        passed = passed and steps["fixture_visibility"] == "success"
        passed = passed and steps["value_evidence_update"] == "success"
        passed = passed and steps["command_data_publication"] == "success"
        passed = passed and steps["paper_tracking"] in {"success", "skipped"}
        passed = passed and steps["telegram_delivery"] in {"success", "skipped"}
    return {
        "schema_version": 1,
        "workflow": env.get("GITHUB_WORKFLOW"),
        "run_id": env.get("GITHUB_RUN_ID"),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "event": env.get("GITHUB_EVENT_NAME"),
        "commit_sha": env.get("GITHUB_SHA"),
        "branch": env.get("GITHUB_REF_NAME"),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_status": ("PASSED" if live else "TESTS_PASSED") if passed else "NEEDS_REVIEW",
        "validation_scope": "LIVE_PIPELINE" if live else "TESTS_ONLY",
        "steps": steps,
        "release_status": "LOCKED_SHADOW_MODE",
        "betting_alerts_enabled": False,
    }


def publish_status(status: dict, repo: str, token: str) -> None:
    api = f"https://api.github.com/repos/{repo}/contents/{quote(PATH, safe='/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Veltrix-Verification-Receipt",
        "Content-Type": "application/json",
    }
    sha = None
    request = Request(api + "?ref=" + quote(BRANCH, safe=""), headers=headers)
    try:
        with urlopen(request, timeout=15) as response:
            current = json.loads(response.read().decode("utf-8"))
            sha = current.get("sha")
    except HTTPError as exc:
        if exc.code != 404:
            raise
    data = json.dumps(status, indent=2, ensure_ascii=False).encode("utf-8")
    body = {
        "message": f"Record VELTRIX verification run {status.get('run_id')}",
        "content": base64.b64encode(data).decode("ascii"),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    request = Request(api, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
    with urlopen(request, timeout=20) as response:
        json.loads(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    token = os.getenv("GITHUB_TOKEN", "")
    if not args.repo or not token:
        raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required.")
    status = build_status(dict(os.environ))
    publish_status(status, args.repo, token)
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
