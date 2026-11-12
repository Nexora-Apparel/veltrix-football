#!/usr/bin/env python3
"""Bounded StrikerAPI feature and timestamp qualification (maximum 62 credits)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://mcp.strikerapi.com/v1"
COSTS = {
    "list_games": 2,
    "get_game": 5,
    "get_lineups": 5,
    "get_events": 10,
    "get_shot_map": 10,
    "get_team_stats": 5,
    "get_odds": 5,
    "get_market_odds": 10,
    "get_line_movement": 10,
}
MAX_CREDITS = sum(COSTS.values())


class ProbeError(RuntimeError):
    pass


def _send(api_key: str, tool: str, params: dict):
    request = Request(
        f"{BASE}/{tool}",
        data=json.dumps(params).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "User-Agent": "VELTRIX-Phase1-StrikerAPI-feature-probe/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload, response.headers
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        return exc.code, payload if isinstance(payload, dict) else {}, exc.headers
    except (URLError, TimeoutError, OSError):
        raise ProbeError("NETWORK_ERROR") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProbeError("INVALID_JSON") from None


def _valid_timestamp(value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _hash(report: dict) -> str:
    body = dict(report)
    body.pop("report_sha256", None)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _data(payload):
    if not isinstance(payload, dict):
        return {}
    value = payload.get("data", payload)
    return value if isinstance(value, dict) else {}


def _lineup_counts(value):
    counts = {"players": 0, "starters": 0, "bench": 0}
    def walk(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                lowered = str(k).casefold()
                if isinstance(v, list):
                    if lowered in {"players", "starting", "starters", "bench", "substitutes"}:
                        counts["players"] += len(v)
                    if lowered in {"starting", "starters"}:
                        counts["starters"] += len(v)
                    if lowered in {"bench", "substitutes"}:
                        counts["bench"] += len(v)
                walk(v, lowered)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)
    walk(value)
    return counts


def _shot_counts(rows):
    if not isinstance(rows, list):
        return {"rows": 0, "xg_rows": 0, "located_rows": 0}
    xg_rows = 0
    located_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        xg = row.get("xg")
        if _number(xg) and 0 <= float(xg) <= 1:
            xg_rows += 1
        if _number(row.get("x")) and _number(row.get("y")):
            located_rows += 1
    return {"rows": len(rows), "xg_rows": xg_rows, "located_rows": located_rows}


def _summarize(tool: str, data: dict) -> dict:
    if tool == "get_game":
        players = data.get("players") if isinstance(data.get("players"), list) else []
        stats = data.get("team_stats") if isinstance(data.get("team_stats"), list) else []
        return {
            "status": "OK" if data.get("game") else "OK_EMPTY",
            "player_rows": len(players),
            "team_stat_rows": len(stats),
            "xg_team_stat_rows": sum(1 for row in stats if isinstance(row, dict) and _number(row.get("xg"))),
            "game_fields": sorted((data.get("game") or {}).keys()) if isinstance(data.get("game"), dict) else [],
        }
    if tool == "get_lineups":
        counts = _lineup_counts(data)
        return {"status": "OK" if any(counts.values()) else "OK_EMPTY", **counts}
    if tool == "get_events":
        events = data.get("events") if isinstance(data.get("events"), list) else []
        shots = [row.get("shot") for row in events if isinstance(row, dict) and isinstance(row.get("shot"), dict)]
        return {"status": "OK" if events else "OK_EMPTY", "event_rows": len(events), **_shot_counts(shots)}
    if tool == "get_shot_map":
        shots = data.get("shots") if isinstance(data.get("shots"), list) else []
        return {
            "status": "OK" if shots or data.get("shots_total") is not None else "OK_EMPTY",
            "shots_total": data.get("shots_total"),
            **_shot_counts(shots),
        }
    if tool == "get_team_stats":
        teams = data.get("teams") if isinstance(data.get("teams"), list) else []
        return {
            "status": "OK" if teams else "OK_EMPTY",
            "team_rows": len(teams),
            "xg_for_rows": sum(1 for row in teams if isinstance(row, dict) and _number(row.get("xg_for"))),
            "xg_against_rows": sum(1 for row in teams if isinstance(row, dict) and _number(row.get("xg_against"))),
        }
    if tool == "get_odds":
        games = data.get("games") if isinstance(data.get("games"), list) else []
        books = [book for game in games if isinstance(game, dict)
                 for book in (game.get("books") or []) if isinstance(book, dict)]
        timestamps = sum(1 for book in books if _valid_timestamp(book.get("captured_at")))
        return {
            "status": "OK" if books else "OK_EMPTY",
            "game_rows": len(games),
            "book_rows": len(books),
            "timestamped_book_rows": timestamps,
            "timestamped_book_fraction": timestamps / len(books) if books else None,
            "rows_with_1x2": sum(1 for b in books if any(_number(b.get(k)) for k in ("home_ml_open", "home_ml_close", "draw_ml_open", "away_ml_close"))),
            "rows_with_totals": sum(1 for b in books if any(_number(b.get(k)) for k in ("total_open", "total_close", "over_odds", "under_odds"))),
        }
    if tool == "get_market_odds":
        books = data.get("books") if isinstance(data.get("books"), list) else []
        timestamped = sum(
            1 for book in books if isinstance(book, dict)
            and _valid_timestamp(book.get("opening_captured_at"))
            and _valid_timestamp(book.get("closing_captured_at"))
        )
        return {
            "status": "OK" if books else "OK_EMPTY",
            "book_rows": len(books),
            "timestamped_open_close_rows": timestamped,
            "timestamped_open_close_fraction": timestamped / len(books) if books else None,
            "opening_price_rows": sum(len(book.get("opening") or []) for book in books if isinstance(book, dict)),
            "closing_price_rows": sum(len(book.get("closing") or []) for book in books if isinstance(book, dict)),
        }
    if tool == "get_line_movement":
        movement = data.get("movement") if isinstance(data.get("movement"), dict) else {}
        snapshots = [row for rows in movement.values() if isinstance(rows, list) for row in rows if isinstance(row, dict)]
        timestamped = sum(1 for row in snapshots if _valid_timestamp(row.get("captured_at")))
        return {
            "status": "OK" if snapshots else "OK_EMPTY",
            "bookmakers": len(movement),
            "snapshot_rows": len(snapshots),
            "timestamped_snapshot_rows": timestamped,
            "timestamped_snapshot_fraction": timestamped / len(snapshots) if snapshots else None,
        }
    return {"status": "UNSUPPORTED_SUMMARY"}


def probe(api_key: str, send=_send, sleep=time.sleep) -> dict:
    if not api_key.strip():
        return {
            "schema_version": 1, "provider": "StrikerAPI",
            "mode": "bounded_non_live_feature_and_odds_qualification",
            "status": "MISSING_SECRET", "calls": [], "credits_spent_estimate": 0,
            "maximum_credits": MAX_CREDITS,
        }

    calls = []
    credits_spent = 0

    def call(tool: str, params: dict):
        nonlocal credits_spent
        cost = COSTS[tool]
        if calls:
            sleep(0.8)
        status, payload, headers = send(api_key, tool, params)
        if status == 402:
            calls.append({"tool": tool, "http_status": 402, "credit_cost": cost, "status": "INSUFFICIENT_CREDITS"})
            return None, False
        if status != 200:
            calls.append({"tool": tool, "http_status": status, "credit_cost": cost, "status": "HTTP_ERROR"})
            return None, False
        credits_spent += cost
        data = _data(payload)
        summary = _summarize(tool, data)
        calls.append({
            "tool": tool,
            "http_status": 200,
            "credit_cost": cost,
            **summary,
        })
        return data, True

    end = date.today()
    start = end - timedelta(days=90)
    games_data, ok = call("list_games", {
        "league": "soccer",
        "status": "final",
        "from": start.isoformat(),
        "to": end.isoformat(),
        "limit": 50,
        "offset": 0,
    })
    if not ok:
        status = "INSUFFICIENT_CREDITS" if calls[-1]["http_status"] == 402 else "LIST_GAMES_FAILED"
    else:
        games = games_data.get("games") if isinstance(games_data.get("games"), list) else []
        finished = [row for row in games if isinstance(row, dict) and row.get("status") == "final" and row.get("game_id")]
        finished.sort(key=lambda row: str(row.get("starts_at") or ""), reverse=True)
        if not finished:
            status = "NO_FINISHED_GAME_SAMPLE"
        else:
            game = finished[0]
            game_id = str(game["game_id"])
            season = game.get("season") or end.year
            status = "PARTIAL"
            endpoints = [
                ("get_game", {"game_id": game_id, "league": "soccer"}),
                ("get_lineups", {"game_id": game_id, "league": "soccer"}),
                ("get_events", {"game_id": game_id, "kind": "all", "limit": 300, "league": "soccer"}),
                ("get_shot_map", {"game_id": game_id, "include_shots": True, "league": "soccer"}),
                ("get_team_stats", {"season": season, "league": "soccer"}),
                ("get_odds", {"game_id": game_id, "league": "soccer"}),
                ("get_market_odds", {"game_id": game_id, "market": "btts", "league": "soccer"}),
                ("get_line_movement", {"game_id": game_id, "all_snapshots": True, "league": "soccer"}),
            ]
            for tool, params in endpoints:
                _, endpoint_ok = call(tool, params)
                if not endpoint_ok:
                    status = "INSUFFICIENT_CREDITS" if calls[-1]["http_status"] == 402 else "PARTIAL_ENDPOINT_ERROR"
                    break
            else:
                status = "ALL_FEATURE_ENDPOINTS_RESPONDED"

    report = {
        "schema_version": 1,
        "provider": "StrikerAPI",
        "mode": "bounded_non_live_feature_and_odds_qualification",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "sample_game": {
            "game_id": str(finished[0].get("game_id")) if "finished" in locals() and finished else None,
            "competition": str(finished[0].get("competition") or "not_reported")[:100] if "finished" in locals() and finished else None,
            "season": finished[0].get("season") if "finished" in locals() and finished else None,
        },
        "calls": calls,
        "credits_spent_estimate": credits_spent,
        "maximum_credits": MAX_CREDITS,
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
    if report.get("provider") != "StrikerAPI" or report.get("mode") != "bounded_non_live_feature_and_odds_qualification":
        raise ValueError("scope_invalid")
    if report.get("maximum_credits") != MAX_CREDITS or report.get("credits_spent_estimate", 0) > MAX_CREDITS:
        raise ValueError("credit_cap_invalid")
    if report.get("side_effects", {}).get("database_writes") != 0:
        raise ValueError("side_effects_invalid")
    if report.get("report_sha256") != _hash(report):
        raise ValueError("report_hash_invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/phase1/strikerapi-features.json")
    args = parser.parse_args()
    try:
        report = probe(os.getenv("STRIKERAPI_API_KEY", ""))
        validate_report(report)
    except ProbeError as exc:
        print(f"STRIKERAPI_FEATURE_PROBE: {exc}")
        return 2
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "STRIKERAPI_FEATURE_PROBE: "
        f"status={report['status']} "
        f"calls={len(report['calls'])} "
        f"credits={report['credits_spent_estimate']}/{MAX_CREDITS} "
        f"sha256={report['report_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
