"""Read-only Premier League fixture reconciliation across StrikerAPI and 5DollarFootballAPI."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from pathlib import Path

# Direct script execution places scripts/ rather than the repository root on sys.path.
# Add the root so the shared reconciliation module is importable in GitHub Actions.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.reconcile_provider_fixtures import reconcile, striker_record, fivedollar_record, valid_identity
from scripts.verify_strikerapi import call_api, collect_pages, validate_game, ProbeError
from app.provider_team_aliases import load_registry

FIVEDOLLAR_BASE = "https://api.5dollarfootballapi.com/v1"
FIVEDOLLAR_EPL_ID = 4160026622
FIVEDOLLAR_PAGE_SIZE = 100
FIVEDOLLAR_MAX_PAGES = 3
TIMEOUT = 25


class ExportError(RuntimeError):
    pass


def request_fivedollar(url: str, api_key: str):
    request = Request(
        url,
        headers={"Accept":"application/json","Authorization":f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, response.headers, payload
    except HTTPError as exc:
        raise ExportError(f"5DollarFootballAPI HTTP {exc.code}") from None
    except (URLError, TimeoutError, OSError):
        raise ExportError("5DollarFootballAPI network request failed") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ExportError("5DollarFootballAPI returned invalid JSON") from None


def collect_fivedollar_pages(api_key: str, start_ts: int, end_ts: int, request=request_fivedollar):
    rows = []
    pages = 0
    page = 1
    while pages < FIVEDOLLAR_MAX_PAGES:
        query = urlencode({
            "start_time":start_ts,
            "end_time":end_ts,
            "status":"finished",
            "page":page,
            "per_page":FIVEDOLLAR_PAGE_SIZE,
            "order":"asc",
        })
        url = f"{FIVEDOLLAR_BASE}/leagues/{FIVEDOLLAR_EPL_ID}/fixtures?{query}"
        status, headers, payload = request(url, api_key)
        if status != 200 or not isinstance(payload, dict) or payload.get("success") not in (1, True, "1"):
            raise ExportError("5DollarFootballAPI returned an unexpected response")
        data = payload.get("data")
        pagination = payload.get("pagination")
        if not isinstance(data, list) or not isinstance(pagination, dict):
            raise ExportError("5DollarFootballAPI response schema is incomplete")
        rows.extend(data)
        pages += 1
        if not pagination.get("has_more", False):
            return rows, pages, headers
        page += 1
    raise ExportError("5DollarFootballAPI pagination exceeded the bounded page cap")


def validate_fivedollar_row(row: object) -> bool:
    if not isinstance(row, dict):
        return False
    record = fivedollar_record(row)
    if not valid_identity(record) or record["competition_key"] != str(FIVEDOLLAR_EPL_ID):
        return False
    if record["status"] != "finished":
        return False
    for score in (record["home_score"], record["away_score"]):
        if not isinstance(score, int) or isinstance(score, bool) or score < 0:
            return False
    if not record["home_id"] or not record["away_id"]:
        return False
    return True


def main() -> int:
    striker_key = os.getenv("STRIKERAPI_API_KEY", "").strip()
    dollar_key = os.getenv("FIVEDOLLARFOOTBALL_API_KEY", "").strip()
    if not striker_key or not dollar_key:
        print("LIVE_RECONCILIATION: BLOCKED_MISSING_PROVIDER_SECRET")
        return 2

    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(days=90)
    start_ts, end_ts = int(start.timestamp()), int(now.timestamp())
    start_date, end_date = start.date().isoformat(), now.date().isoformat()
    print(
        f"RECONCILIATION_WINDOW_UTC: start={start.isoformat()}; end_exclusive={now.isoformat()}"
    )
    print(f"COMPETITION_MAPPING: StrikerAPI soccer -> 5DollarFootballAPI {FIVEDOLLAR_EPL_ID} (authenticated catalogue)")

    try:
        striker_rows, striker_pages, striker_truncated, striker_page_counts = collect_pages(
            striker_key, "soccer", "final", start_date, end_date, call_api
        )
        if striker_truncated:
            raise ExportError("StrikerAPI Premier League pagination was incomplete")
        invalid_striker = [
            row for row in striker_rows
            if not validate_game(row, "final")[0]
        ]
        if invalid_striker:
            raise ExportError(f"StrikerAPI returned {len(invalid_striker)} invalid final rows")

        dollar_rows, dollar_pages, dollar_headers = collect_fivedollar_pages(
            dollar_key, start_ts, end_ts
        )
        invalid_dollar = [row for row in dollar_rows if not validate_fivedollar_row(row)]
        if invalid_dollar:
            raise ExportError(f"5DollarFootballAPI returned {len(invalid_dollar)} invalid finished rows")
    except (ProbeError, ExportError) as exc:
        safe = str(exc).replace("\n", " ")[:160]
        print(f"LIVE_RECONCILIATION_FAILED: {safe}")
        print("DATABASE_WRITES: 0; IMPORTS: 0; CHECKPOINTS: 0")
        return 1

    normalized_striker = [striker_record(row, "soccer") for row in striker_rows]
    normalized_dollar = [fivedollar_record(row) for row in dollar_rows]
    alias_registry = load_registry(Path("data/provider_team_aliases.json"))
    report = reconcile(
        normalized_striker,
        normalized_dollar,
        {"soccer":str(FIVEDOLLAR_EPL_ID)},
        alias_registry=alias_registry,
        alias_competition_key="england_premier_league",
        season="2026-27",
    )
    report["provenance"] = {
        "window_start_utc":start.isoformat(),
        "window_end_exclusive_utc":now.isoformat(),
        "striker":{"endpoint":"POST /v1/list_games","league":"soccer","status":"final",
                   "from":start_date,"to":end_date,"pages":striker_pages,
                   "page_count_fields":striker_page_counts,"calls":striker_pages,
                   "documented_credits":striker_pages*2},
        "fivedollar":{"endpoint":f"GET /v1/leagues/{FIVEDOLLAR_EPL_ID}/fixtures",
                      "league_id":FIVEDOLLAR_EPL_ID,"status":"finished",
                      "start_time":start_ts,"end_time_exclusive":end_ts,
                      "pages":dollar_pages,"calls":dollar_pages,
                      "rate_limit_remaining":dollar_headers.get("X-RateLimit-Remaining")},
        "database_writes":0,"imports":0,"checkpoints":0,
    }
    output = Path("strikerapi_5dollar_epl_reconciliation.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    outcomes = {}
    for decision in report["decisions"]:
        outcome = decision["outcome"]
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    print(
        f"RECONCILIATION_COUNTS: striker_rows={len(striker_rows)}; "
        f"fivedollar_rows={len(dollar_rows)}; striker_calls={striker_pages}; "
        f"striker_credits={striker_pages*2}; fivedollar_calls={dollar_pages}; "
        f"outcomes={json.dumps(outcomes, sort_keys=True)}"
    )
    print(f"RECONCILIATION_ACCEPTANCE: {'PASS' if report['acceptance_pass'] else 'FAIL_REVIEW_REQUIRED'}")
    print(f"RECONCILIATION_REPORT: {output.name}")
    print("DATABASE_WRITES: 0; IMPORTS: 0; CHECKPOINTS: 0; CANONICAL_MERGES: 0")
    # A completed audit with conflicts is a valid diagnostic artifact, not API failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
