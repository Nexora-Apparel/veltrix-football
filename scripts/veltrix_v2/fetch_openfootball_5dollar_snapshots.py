"""Fetch immutable, read-only OpenFootball and 5Dollar EPL snapshots for reconciliation.

This script never imports the legacy prediction package and never writes to a database.
It stores source bytes, SHA-256 hashes, retrieval timestamps, pagination accounting and
sanitized provider errors for an auditable GitHub Actions artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, time as daytime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.5dollarfootballapi.com/v1"
OPENFOOTBALL_REPO = "openfootball/football.json"
OPENFOOTBALL_PATH = "2026-27/en.1.json"
USER_AGENT = "VELTRIX-FOOTBALL-READONLY-QUALIFIER/1.0"


class SafeFetchError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_bytes(url: str, headers: dict[str, str] | None = None) -> tuple[bytes, dict[str, str]]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
            return body, {
                "http_status": str(response.status),
                "content_type": response.headers.get("Content-Type", ""),
                "etag": response.headers.get("ETag", ""),
                "last_modified": response.headers.get("Last-Modified", ""),
            }
    except HTTPError as exc:
        # Never print URLs, authorization headers, or raw provider error bodies.
        raise SafeFetchError(f"HTTP_{exc.code}", exc.code) from None
    except (URLError, TimeoutError, OSError):
        raise SafeFetchError("NETWORK_ERROR") from None


def get_json(url: str, headers: dict[str, str] | None = None) -> tuple[dict | list, bytes, dict[str, str]]:
    body, headers_out = request_bytes(url, headers)
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SafeFetchError("INVALID_JSON") from None
    return payload, body, headers_out


def write_json(path: Path, value: object) -> tuple[str, int]:
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path.write_bytes(data)
    return sha256(data), len(data)


def fetch_openfootball(out: Path, manifest: dict) -> None:
    api_url = f"https://api.github.com/repos/{OPENFOOTBALL_REPO}/commits?{urlencode({'path': OPENFOOTBALL_PATH, 'per_page': 1})}"
    commits, _, commit_headers = get_json(api_url, {"Accept": "application/vnd.github+json"})
    if not isinstance(commits, list) or not commits or not isinstance(commits[0], dict):
        raise SafeFetchError("OPENFOOTBALL_COMMIT_NOT_FOUND")
    commit = commits[0].get("sha")
    if not isinstance(commit, str) or len(commit) != 40:
        raise SafeFetchError("OPENFOOTBALL_COMMIT_SHA_INVALID")
    raw_url = f"https://raw.githubusercontent.com/{OPENFOOTBALL_REPO}/{commit}/{OPENFOOTBALL_PATH}"
    body, response_headers = request_bytes(raw_url)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        raise SafeFetchError("OPENFOOTBALL_SCHEMA_INVALID")
    target = out / "openfootball_epl_2026-27.json"
    target.write_bytes(body)
    manifest["openfootball"] = {
        "status": "FETCHED",
        "repository": OPENFOOTBALL_REPO,
        "path": OPENFOOTBALL_PATH,
        "source_commit": commit,
        "commit_api_etag": commit_headers.get("etag", ""),
        "retrieved_at_utc": utc_now(),
        "http_status": response_headers.get("http_status"),
        "content_type": response_headers.get("content_type"),
        "etag": response_headers.get("etag"),
        "last_modified": response_headers.get("last_modified"),
        "payload_sha256": sha256(body),
        "payload_bytes": len(body),
        "dataset_name": payload.get("name"),
        "source_rows": len(payload["matches"]),
        "scored_rows": sum(
            1 for row in payload["matches"]
            if isinstance(row, dict)
            and isinstance(row.get("score"), dict)
            and isinstance(row["score"].get("ft"), list)
            and len(row["score"]["ft"]) == 2
        ),
    }


def fetch_5dollar(out: Path, start: date, end_exclusive: date, manifest: dict) -> None:
    key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not key:
        raise SafeFetchError("MISSING_FIVEDOLLARFOOTBALL_API_KEY")
    auth = {"Authorization": f"Bearer {key}"}

    # Prefer the documented country filter. Search fallback handles provider
    # catalogue changes without guessing an ID or weakening exact identity checks.
    league_rows: list[dict] = []
    league_pages = 0
    discovery_queries = [
        {"country": "GB-ENG", "per_page": 50},
        {"search": "Premier League", "per_page": 50},
        {"popular": 1, "per_page": 50},
    ]
    discovery_evidence: list[dict] = []
    seen_league_ids: set[str] = set()
    for discovery in discovery_queries:
        query_rows: list[dict] = []
        for page in range(1, 11):
            params = {**discovery, "page": page}
            payload, _, _ = get_json(f"{API}/leagues?{urlencode(params)}", auth)
            if not isinstance(payload, dict) or payload.get("success") != 1 or not isinstance(payload.get("data"), list):
                raise SafeFetchError("FIVEDOLLAR_LEAGUE_SCHEMA_INVALID")
            page_rows = [x for x in payload["data"] if isinstance(x, dict)]
            query_rows.extend(page_rows)
            league_pages += 1
            if not (payload.get("pagination") or {}).get("has_more"):
                break
            time.sleep(3.1)
        else:
            raise SafeFetchError("FIVEDOLLAR_LEAGUE_PAGINATION_LIMIT")

        for row in query_rows:
            identity = str(row.get("id", ""))
            if identity and identity not in seen_league_ids:
                seen_league_ids.add(identity)
                league_rows.append(row)

        candidates = []
        for row in query_rows:
            country = row.get("country") or {}
            name = str(row.get("name", "")).strip().casefold()
            short_name = str(row.get("short_name", "")).strip().casefold()
            country_code = str(country.get("code", "")).strip().upper()
            country_name = str(country.get("name", "")).strip().casefold()
            # The account-qualified catalogue historically labels EPL as
            # "England Premier League" (ID 4160026622), while current docs
            # examples use "Premier League". Accept only these exact aliases,
            # with an explicit England/EPL identity signal.
            exact_name = name in {"premier league", "england premier league"}
            exact_country = country_code == "GB-ENG" or country_name == "england"
            exact_short_name = short_name == "epl"
            qualified_id_match = str(row.get("id", "")) == "4160026622"
            explicit_england_name = name == "england premier league"
            if exact_name and (exact_country or exact_short_name or qualified_id_match or explicit_england_name):
                candidates.append(row)

        discovery_evidence.append({
            "query": discovery,
            "rows": len(query_rows),
            "candidate_count": len(candidates),
        })
        if len(candidates) == 1:
            break

    if len(candidates) != 1:
        diagnostic = [
            {
                "id": str(row.get("id", "")),
                "name": row.get("name"),
                "short_name": row.get("short_name"),
                "country_code": (row.get("country") or {}).get("code"),
                "country_name": (row.get("country") or {}).get("name"),
            }
            for row in league_rows[:100]
        ]
        manifest["fivedollar_discovery"] = {
            "queries": discovery_evidence,
            "catalogue_rows": len(league_rows),
            "catalogue_preview": diagnostic,
        }
        raise SafeFetchError(f"FIVEDOLLAR_EPL_LEAGUE_IDENTITY_COUNT_{len(candidates)}")
    league = candidates[0]
    league_id = league.get("id")
    if league_id is None:
        raise SafeFetchError("FIVEDOLLAR_EPL_LEAGUE_ID_MISSING")

    start_ts = int(datetime.combine(start, daytime.min, tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.combine(end_exclusive, daytime.min, tzinfo=timezone.utc).timestamp())
    rows: list[dict] = []
    page_hashes: list[dict] = []
    pages = 0
    for page in range(1, 21):
        query = urlencode({
            "start_time": start_ts,
            "end_time": end_ts,
            "status": "finished",
            "order": "asc",
            "page": page,
            "per_page": 100,
        })
        payload, raw, response_headers = get_json(f"{API}/leagues/{league_id}/fixtures?{query}", auth)
        if not isinstance(payload, dict) or payload.get("success") != 1 or not isinstance(payload.get("data"), list):
            raise SafeFetchError("FIVEDOLLAR_FIXTURE_SCHEMA_INVALID")
        page_file = out / f"fivedollar_epl_page_{page:02d}.json"
        page_file.write_bytes(raw)
        page_hashes.append({
            "page": page,
            "sha256": sha256(raw),
            "bytes": len(raw),
            "etag": response_headers.get("etag", ""),
        })
        rows.extend(x for x in payload["data"] if isinstance(x, dict))
        pages += 1
        if not (payload.get("pagination") or {}).get("has_more"):
            break
        time.sleep(3.1)  # Stay below the documented 20/minute burst limit.
    else:
        raise SafeFetchError("FIVEDOLLAR_FIXTURE_PAGINATION_LIMIT")

    aggregate = {
        "provider": "5DollarFootballAPI",
        "league": league,
        "window_start_utc": start.isoformat() + "T00:00:00+00:00",
        "window_end_exclusive_utc": end_exclusive.isoformat() + "T00:00:00+00:00",
        "status_filter": "finished",
        "rows": rows,
    }
    aggregate_hash, aggregate_bytes = write_json(out / "fivedollar_epl_fixtures.json", aggregate)
    manifest["fivedollar"] = {
        "status": "FETCHED",
        "retrieved_at_utc": utc_now(),
        "league_id": str(league_id),
        "league_name": league.get("name"),
        "country_code": (league.get("country") or {}).get("code"),
        "league_catalogue_rows": len(league_rows),
        "league_catalogue_pages": league_pages,
        "window_start_utc": aggregate["window_start_utc"],
        "window_end_exclusive_utc": aggregate["window_end_exclusive_utc"],
        "status_filter": "finished",
        "fixture_pages": pages,
        "fixture_rows": len(rows),
        "page_payloads": page_hashes,
        "aggregate_sha256": aggregate_hash,
        "aggregate_bytes": aggregate_bytes,
    }



def fetch_fpl(out: Path, manifest: dict) -> None:
    """Read the public EPL Fantasy Premier League player/fixture snapshots."""
    base = "https://fantasy.premierleague.com/api"
    bootstrap, bootstrap_raw, bootstrap_headers = get_json(f"{base}/bootstrap-static/")
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("elements"), list) or not isinstance(bootstrap.get("teams"), list):
        raise SafeFetchError("FPL_BOOTSTRAP_SCHEMA_INVALID")
    fixtures, fixtures_raw, fixtures_headers = get_json(f"{base}/fixtures/")
    if not isinstance(fixtures, list):
        raise SafeFetchError("FPL_FIXTURES_SCHEMA_INVALID")
    (out / "fpl_bootstrap_static.json").write_bytes(bootstrap_raw)
    (out / "fpl_fixtures.json").write_bytes(fixtures_raw)
    players = bootstrap["elements"]
    manifest["fpl"] = {
        "status": "FETCHED",
        "retrieved_at_utc": utc_now(),
        "source": "Fantasy Premier League public JSON API (undocumented)",
        "bootstrap_http_status": bootstrap_headers.get("http_status"),
        "bootstrap_sha256": sha256(bootstrap_raw),
        "bootstrap_bytes": len(bootstrap_raw),
        "player_rows": len(players),
        "team_rows": len(bootstrap["teams"]),
        "players_with_expected_goals_field": sum(1 for p in players if isinstance(p, dict) and "expected_goals" in p),
        "players_with_expected_assists_field": sum(1 for p in players if isinstance(p, dict) and "expected_assists" in p),
        "players_with_availability_status": sum(1 for p in players if isinstance(p, dict) and "status" in p),
        "players_with_chance_of_playing_field": sum(1 for p in players if isinstance(p, dict) and "chance_of_playing_next_round" in p),
        "fixture_http_status": fixtures_headers.get("http_status"),
        "fixture_sha256": sha256(fixtures_raw),
        "fixture_bytes": len(fixtures_raw),
        "fixture_rows": len(fixtures),
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date-exclusive", required=True)
    parser.add_argument("--out", default="readonly-snapshots")
    args = parser.parse_args()

    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date_exclusive)
    span = (end - start).days
    if span < 1 or span > 90:
        print("INPUT_ERROR: date window must be 1–90 days (end date is exclusive).")
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "workflow": "openfootball-5dollar-readonly-reconciliation",
        "retrieved_at_utc": utc_now(),
        "read_only": True,
        "database_access": False,
        "prediction_code_access": False,
        "window_start_date": start.isoformat(),
        "window_end_date_exclusive": end.isoformat(),
        "window_days": span,
        "sources": {},
    }
    failures = []
    required_failures = []
    for name, operation, required in (
        ("openfootball", lambda: fetch_openfootball(out, manifest), True),
        ("fivedollar", lambda: fetch_5dollar(out, start, end, manifest), True),
        ("fpl", lambda: fetch_fpl(out, manifest), False),
    ):
        try:
            operation()
        except (SafeFetchError, ValueError, TypeError, KeyError) as exc:
            safe = str(exc)[:100]
            manifest["sources"][name] = {"status": "FAILED", "error": safe, "retrieved_at_utc": utc_now()}
            failures.append(name)
            if required:
                required_failures.append(name)
    manifest["sources"].update({k: v for k, v in list(manifest.items()) if k in {"openfootball", "fivedollar", "fpl"}})
    manifest.pop("openfootball", None)
    manifest.pop("fivedollar", None)
    manifest.pop("fpl", None)
    manifest["overall_status"] = "PAIRED_SNAPSHOTS_FETCHED" if not required_failures else "PAIRED_SNAPSHOT_FAILED"
    manifest["failed_sources"] = failures
    manifest["required_source_failures"] = required_failures
    manifest["optional_source_failures"] = [name for name in failures if name not in required_failures]
    write_json(out / "snapshot_manifest.json", manifest)
    print(f"SNAPSHOT_STATUS: {manifest['overall_status']}")
    for name, item in manifest["sources"].items():
        print(f"{name.upper()}_STATUS: {item.get('status')}; rows={item.get('source_rows', item.get('fixture_rows', item.get('player_rows', 'n/a')))}; sha256={item.get('payload_sha256', item.get('aggregate_sha256', 'n/a'))}")
    print("READ_ONLY_GUARD: database_access=false; prediction_code_access=false")
    return 0 if not required_failures else 1


if __name__ == "__main__":
    sys.exit(main())
