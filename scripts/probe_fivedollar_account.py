#!/usr/bin/env python3
"""Read-only 5Dollar plan, competition, and timestamped-odds sample for Phase 1."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.5dollarfootballapi.com/v1"


class ProbeError(RuntimeError):
    pass


def _request(path: str, key: str):
    req = Request(
        BASE + path,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "VELTRIX-Phase1-Provider-Qualification/1.0",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = response.headers
            status = response.status
    except HTTPError as exc:
        raise ProbeError(f"HTTP_{exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ProbeError("NETWORK_ERROR") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("INVALID_JSON") from None
    if status != 200 or not isinstance(payload, dict) or payload.get("success") not in (1, True):
        raise ProbeError("UNSUCCESSFUL_RESPONSE")
    return payload, headers


def _valid_timestamp(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _hash(report: dict) -> str:
    body = dict(report)
    body.pop("report_sha256", None)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _odds_summary(payload: dict) -> dict:
    data = payload.get("data")
    if not isinstance(data, dict):
        return {"status": "INVALID_SCHEMA", "bookmakers": 0, "markets": 0,
                "timestamped_markets": 0, "btts": False, "goal_line": False,
                "one_x_two_opened_at": False}
    books = data.get("bookmakers") or []
    if not isinstance(books, list):
        return {"status": "INVALID_SCHEMA", "bookmakers": 0, "markets": 0,
                "timestamped_markets": 0, "btts": False, "goal_line": False,
                "one_x_two_opened_at": False}
    market_count = 0
    timestamped_markets = 0
    btts = False
    goal_line = False
    one_x_two_opened_at = False
    for book in books:
        if not isinstance(book, dict):
            continue
        odds = book.get("odds") or {}
        if not isinstance(odds, dict):
            continue
        for market_name, block in odds.items():
            if not isinstance(block, dict):
                continue
            market_count += 1
            if market_name == "btts":
                btts = True
            if market_name in {"goal_line", "goal_line_fixed"}:
                goal_line = True
            opening = block.get("opening") or {}
            closing = block.get("closing") or {}
            if not isinstance(opening, dict):
                opening = {}
            if not isinstance(closing, dict):
                closing = {}
            has_timestamp = any(_valid_timestamp(value) for value in (
                opening.get("opened_at"), opening.get("at"),
                closing.get("closed_at"), closing.get("at"),
                block.get("opened_at"), block.get("closed_at"),
            ))
            if has_timestamp:
                timestamped_markets += 1
            if market_name == "1x2" and _valid_timestamp(opening.get("opened_at")):
                one_x_two_opened_at = True
    return {
        "status": "OK" if books else "NO_BOOKMAKER_ODDS",
        "bookmakers": len(books),
        "markets": market_count,
        "timestamped_markets": timestamped_markets,
        "timestamped_market_fraction": (timestamped_markets / market_count) if market_count else None,
        "btts": btts,
        "goal_line": goal_line,
        "one_x_two_opened_at": one_x_two_opened_at,
    }


def probe(key: str, request=_request, sleep=time.sleep) -> dict:
    if not key.strip():
        raise ProbeError("MISSING_SECRET")
    request_count = 0

    def call(path: str):
        nonlocal request_count
        # The account has a 20-requests/minute burst ceiling. The preceding
        # multi-source check can use up to four calls; pace this 16-call probe.
        if request_count:
            sleep(2.5)
        payload, headers = request(path, key)
        request_count += 1
        return payload, headers

    status_payload, status_headers = call("/status")
    leagues_payload, league_headers = call("/leagues")
    if not isinstance(status_payload, dict) or not isinstance(status_payload.get("data"), dict):
        raise ProbeError("STATUS_SCHEMA_INVALID")
    if not isinstance(leagues_payload, dict):
        raise ProbeError("LEAGUE_CATALOGUE_SCHEMA_INVALID")
    status_data = status_payload["data"]
    leagues_data = leagues_payload.get("data")
    if isinstance(leagues_data, dict) and isinstance(leagues_data.get("leagues"), list):
        leagues_data = leagues_data["leagues"]
    if not isinstance(leagues_data, list):
        raise ProbeError("LEAGUE_CATALOGUE_SCHEMA_INVALID")

    competitions = []
    for row in leagues_data:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        country = row.get("country")
        if isinstance(country, dict):
            country = country.get("name") or country.get("code")
        competitions.append({
            "id": str(row.get("id")),
            "name": str(row.get("name") or "unknown")[:100],
            "country": str(country or "not_reported")[:60],
        })

    odds_samples = []
    for competition in competitions[:7]:
        league_id = competition["id"]
        fixtures_payload, _ = call(
            f"/leagues/{league_id}/fixtures?" + urlencode({"status": "finished", "per_page": 1})
        )
        rows = fixtures_payload.get("data") if isinstance(fixtures_payload, dict) else None
        if not isinstance(rows, list) or not rows:
            odds_samples.append({
                "league_id": league_id,
                "league": competition["name"],
                "status": "NO_FINISHED_FIXTURE",
            })
            continue
        fixture = rows[0]
        fixture_id = fixture.get("id") or fixture.get("fixture_id")
        if fixture_id is None:
            odds_samples.append({
                "league_id": league_id,
                "league": competition["name"],
                "status": "FIXTURE_ID_MISSING",
            })
            continue
        odds_payload, _ = call(f"/fixtures/{fixture_id}/odds")
        summary = _odds_summary(odds_payload)
        odds_samples.append({
            "league_id": league_id,
            "league": competition["name"],
            "fixture_id": str(fixture_id),
            **summary,
        })

    limits = status_data.get("limits") if isinstance(status_data.get("limits"), dict) else {}
    usage = status_data.get("usage") if isinstance(status_data.get("usage"), dict) else {}
    total_markets = sum(int(row.get("markets", 0) or 0) for row in odds_samples)
    timestamped_markets = sum(int(row.get("timestamped_markets", 0) or 0) for row in odds_samples)
    report = {
        "schema_version": 1,
        "provider": "5DollarFootballAPI",
        "mode": "read_only_plan_competition_and_odds_timestamp_probe",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "OK",
        "plan": str(status_data.get("plan") or "not_reported"),
        "limits": {
            "rate_limit": limits.get("rate_limit"),
            "rate_window_seconds": limits.get("rate_window_seconds"),
            "burst_per_minute": limits.get("burst_per_minute"),
        },
        "usage_today": usage.get("today"),
        "competition_count_page_1": len(competitions),
        "competitions": competitions,
        "pagination": {
            "has_more": (leagues_payload.get("pagination") or {}).get("has_more"),
        },
        "odds_samples": odds_samples,
        "odds_market_blocks_sampled": total_markets,
        "odds_timestamped_market_blocks_sampled": timestamped_markets,
        "odds_timestamped_market_fraction_sampled": (
            timestamped_markets / total_markets if total_markets else None
        ),
        "quota_headers": {
            "status_limit": status_headers.get("X-RateLimit-Limit"),
            "status_remaining": status_headers.get("X-RateLimit-Remaining"),
            "catalogue_limit": league_headers.get("X-RateLimit-Limit"),
            "catalogue_remaining": league_headers.get("X-RateLimit-Remaining"),
        },
        "request_count": request_count,
        "request_budget": 16,
        "side_effects": {
            "database_writes": 0,
            "imports": 0,
            "prediction_changes": 0,
            "telegram_messages": 0,
            "deployments": 0,
        },
    }
    report["report_sha256"] = _hash(report)
    return report


def validate_report(report: dict) -> None:
    if not isinstance(report, dict) or report.get("provider") != "5DollarFootballAPI":
        raise ValueError("provider_invalid")
    if report.get("mode") != "read_only_plan_competition_and_odds_timestamp_probe":
        raise ValueError("mode_invalid")
    if not 2 <= report.get("request_count", 0) <= 16:
        raise ValueError("request_count_invalid")
    if report.get("request_budget") != 16:
        raise ValueError("request_budget_invalid")
    if report.get("side_effects", {}).get("database_writes") != 0:
        raise ValueError("side_effects_invalid")
    if report.get("report_sha256") != _hash(report):
        raise ValueError("report_hash_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/phase1_fivedollar_account.json")
    args = parser.parse_args()
    try:
        report = probe(os.getenv("FIVEDOLLARFOOTBALL_API_KEY", ""))
        validate_report(report)
    except ProbeError as exc:
        print(f"FIVEDOLLAR_ACCOUNT_PROBE: {exc}")
        return 2
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "FIVEDOLLAR_ACCOUNT_PROBE: "
        f"plan={report['plan']} "
        f"rate_limit={report['limits']['rate_limit']} "
        f"burst={report['limits']['burst_per_minute']} "
        f"competitions={report['competition_count_page_1']} "
        f"odds_samples={len(report['odds_samples'])} "
        f"timestamped_market_fraction={report['odds_timestamped_market_fraction_sampled']} "
        f"requests={report['request_count']}/16 "
        f"sha256={report['report_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
