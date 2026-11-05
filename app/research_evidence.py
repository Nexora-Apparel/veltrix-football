"""Source-discovery adapter for VELTRIX fixture research.

Search results are evidence leads only. This module deliberately does not
extract match statistics, alter historical datasets, or feed model features.
A separate identity and source-verification stage must approve any fact before
it can enter the pre-kickoff training/inference store.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT_SECONDS = 12
MAX_RESULTS_PER_FIXTURE = 8
RESEARCHABLE_STATUSES = {"INSUFFICIENT_HISTORY", "LOW_HISTORY_FORECAST"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_https_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = urlparse(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        host = parsed.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return True
        return address.is_global
    except (TypeError, ValueError):
        return False


def _fixture_query(fixture: dict[str, Any]) -> str:
    home = str(fixture.get("home_team") or "").strip()
    away = str(fixture.get("away_team") or "").strip()
    competition = str(fixture.get("competition") or fixture.get("league") or "").strip()
    kickoff = str(fixture.get("kickoff") or fixture.get("kickoff_utc") or "").strip()
    squad = str(fixture.get("squad_category") or "").strip()
    parts = [f'"{home}" vs "{away}"']
    if competition:
        parts.append(f'"{competition}"')
    if squad:
        parts.append(squad)
    if kickoff:
        parts.append(kickoff[:10])
    parts.append("completed match results recent form goals")
    return " ".join(parts)[:500]


def search_fixture_evidence(
    fixture: dict[str, Any],
    *,
    api_key: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    session: Any = requests,
) -> dict[str, Any]:
    """Return timestamped source leads; never return model-ready statistics."""
    if not isinstance(fixture, dict):
        return {"status": "INVALID_FIXTURE", "sources": [], "model_eligible": False}
    home = str(fixture.get("home_team") or "").strip()
    away = str(fixture.get("away_team") or "").strip()
    if not home or not away:
        return {"status": "INVALID_FIXTURE", "sources": [], "model_eligible": False}

    credential = api_key or os.getenv("TAVILY_API_KEY")
    if not credential:
        return {
            "status": "DISABLED_MISSING_CREDENTIAL",
            "sources": [],
            "model_eligible": False,
        }

    payload = {
        "api_key": credential,
        "query": _fixture_query(fixture),
        "topic": "general",
        "search_depth": "advanced",
        "max_results": MAX_RESULTS_PER_FIXTURE,
        "include_answer": False,
        "include_raw_content": False,
    }
    try:
        response = session.post(TAVILY_SEARCH_URL, json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return {
            "status": "PROVIDER_UNAVAILABLE",
            "sources": [],
            "model_eligible": False,
        }

    retrieved_at = _utc_now()
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    results = body.get("results", []) if isinstance(body, dict) else []
    for item in (results[:MAX_RESULTS_PER_FIXTURE] if isinstance(results, list) else []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not _public_https_url(url) or url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        sources.append({
            "url": url,
            "domain": (parsed.hostname or "").lower(),
            "title": str(item.get("title") or "")[:300],
            "snippet": str(item.get("content") or "")[:2000],
            "published_at": item.get("published_date"),
            "search_score": item.get("score"),
            "retrieved_at_utc": retrieved_at,
            "verification_status": "SOURCE_CANDIDATE_UNVERIFIED",
            "model_eligible": False,
        })

    return {
        "status": "SOURCES_FOUND" if sources else "NO_SOURCES_FOUND",
        "fixture_identity": {
            "provider_fixture_id": fixture.get("fixture_id") or fixture.get("id"),
            "home_team": home,
            "away_team": away,
            "competition": fixture.get("competition") or fixture.get("league"),
            "squad_category": fixture.get("squad_category"),
            "kickoff": fixture.get("kickoff") or fixture.get("kickoff_utc"),
        },
        "sources": sources,
        "source_count": len(sources),
        "model_eligible": False,
        "policy": "Search snippets are leads only; verify source, fixture identity, squad and result before ingestion.",
    }


def research_missing_fixtures(
    fixtures: Iterable[dict[str, Any]],
    *,
    api_key: str | None = None,
    max_fixtures: int = 25,
) -> dict[str, Any]:
    """Search only fixtures whose history is incomplete; preserve all identities."""
    results = []
    for fixture in fixtures:
        if len(results) >= max(0, min(int(max_fixtures), 25)):
            break
        if not isinstance(fixture, dict):
            continue
        status = str(fixture.get("status") or "").upper()
        if status not in RESEARCHABLE_STATUSES:
            continue
        results.append(search_fixture_evidence(fixture, api_key=api_key))
    return {
        "status": "DISABLED_MISSING_CREDENTIAL" if not api_key and not os.getenv("TAVILY_API_KEY") else "RESEARCH_COMPLETE",
        "fixtures_searched": len(results),
        "model_eligible_facts": 0,
        "results": results,
        "safety": "No search result is automatically imported into historical data or prediction features.",
    }


def annotate_report_file(report_path: str, output_path: str | None = None) -> dict[str, Any]:
    """Attach source leads to a report without changing prediction probabilities."""
    source = Path(report_path)
    report = json.loads(source.read_text(encoding="utf-8"))
    fixtures = report.get("predictions", []) if isinstance(report, dict) else []
    report["research_evidence"] = research_missing_fixtures(fixtures)
    destination = Path(output_path) if output_path else source
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report["research_evidence"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach quarantined research source leads to a VELTRIX report.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = annotate_report_file(args.report, args.output)
    print(json.dumps({
        "status": result.get("status"),
        "fixtures_searched": result.get("fixtures_searched", 0),
        "model_eligible_facts": result.get("model_eligible_facts", 0),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
