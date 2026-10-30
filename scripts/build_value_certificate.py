"""Build a fail-closed value-validation certificate from archived evidence."""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.value_bets import build_value_validation_certificate, attach_value_bet_screens

API_ROOT = "https://api.github.com"


def _github_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "VeltrixFootball-Validation",
    })
    return session


def _json(session: requests.Session, url: str) -> dict[str, Any]:
    response = session.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub returned an unexpected JSON document.")
    return payload


def latest_backtest_report(repo: str, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the newest successful historical backtest artifact."""
    with _github_session(token) as session:
        url = f"{API_ROOT}/repos/{repo}/actions/workflows/historical-model-backtest.yml/runs?status=success&per_page=30"
        runs = _json(session, url).get("workflow_runs", [])
        for run in runs:
            if not isinstance(run, dict) or not isinstance(run.get("id"), int):
                continue
            artifacts_url = f"{API_ROOT}/repos/{repo}/actions/runs/{run['id']}/artifacts?per_page=100"
            artifacts = _json(session, artifacts_url).get("artifacts", [])
            artifact = next((row for row in artifacts if row.get("name") == "veltrix-backtest-report" and not row.get("expired")), None)
            if not artifact:
                continue
            response = session.get(artifact["archive_download_url"], timeout=60)
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith(".json")]
                if not names:
                    continue
                report = json.loads(archive.read(names[0]).decode("utf-8"))
            if isinstance(report, dict) and isinstance(report.get("live_pipeline"), dict):
                return report, {
                    "workflow_run_id": run["id"],
                    "commit_sha": run.get("head_sha"),
                    "created_at": run.get("created_at"),
                    "dataset_provenance": report.get("dataset_provenance"),
                }
    raise RuntimeError("No successful historical backtest artifact with a compatible report was found.")


def build(report_path: str, ledger_path: str, certificate_path: str, *, backtest_path: str | None = None,
          repo: str | None = None, token: str | None = None) -> dict[str, Any]:
    if backtest_path:
        backtest = json.loads(Path(backtest_path).read_text(encoding="utf-8"))
        provenance = {"source": "local_artifact", "dataset_provenance": backtest.get("dataset_provenance")}
    else:
        repo = (repo or os.getenv("GITHUB_REPOSITORY") or "").strip()
        token = (token or os.getenv("GITHUB_TOKEN") or "").strip()
        if not repo or not token:
            raise RuntimeError("GitHub repository/token context is unavailable for backtest retrieval.")
        backtest, provenance = latest_backtest_report(repo, token)

    ledger_file = Path(ledger_path)
    if ledger_file.exists():
        ledger = json.loads(ledger_file.read_text(encoding="utf-8"))
        if not isinstance(ledger, dict) or ledger.get("model_status") != "PAPER_TRACKING_ONLY":
            raise RuntimeError("Paper ledger failed structural validation; refusing to certify.")
    else:
        ledger = {"markets": {}, "value_validation_markets": {}}

    certificate = build_value_validation_certificate(backtest, ledger)
    certificate["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    certificate["backtest_provenance"] = provenance
    certificate["paper_ledger_present"] = ledger_file.exists()
    certificate["paper_ledger_dates"] = ledger.get("evaluated_report_dates", 0)
    Path(certificate_path).parent.mkdir(parents=True, exist_ok=True)
    Path(certificate_path).write_text(json.dumps(certificate, indent=2, ensure_ascii=False), encoding="utf-8")

    report_file = Path(report_path)
    if report_file.exists():
        report = json.loads(report_file.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise RuntimeError("Daily report has an unexpected structure.")
        report["value_validation_certificate"] = certificate
        attach_value_bet_screens(report, validation_certificate=certificate)
        report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return certificate


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a market-specific, fail-closed value-validation certificate.")
    parser.add_argument("--report", default="reports/daily_predictions.json")
    parser.add_argument("--ledger", default="reports/paper_tracking_ledger.json")
    parser.add_argument("--backtest", default=None, help="Optional local backtest JSON; otherwise fetch latest successful artifact.")
    parser.add_argument("--output", default="reports/value_validation_certificate.json")
    args = parser.parse_args()
    try:
        certificate = build(args.report, args.ledger, args.output, backtest_path=args.backtest)
    except (OSError, ValueError, RuntimeError, requests.RequestException, zipfile.BadZipFile) as exc:
        print(f"Certificate generation failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": certificate["status"],
        "approved_markets": certificate["approved_markets"],
        "alerts_enabled": certificate["alerts_enabled"],
        "market_diagnostics": certificate["market_diagnostics"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
