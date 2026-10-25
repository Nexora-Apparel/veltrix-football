"""Fetch today's fixtures, refresh completed results, and write an experimental report."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError
from app.live_predictions import _name_key, build_daily_report, load_historical_matches
from app.recent_results import fetch_recent_results_incremental
from app.live_odds import extract_market_probabilities



def _load_recent_cache(path: Path) -> tuple[dict, list[dict]]:
    """Load the public cache defensively and normalize dates/team keys for modelling."""
    empty = {"version": 1, "matches": [], "state": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty, []
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("matches"), list):
        return empty, []
    state = value.get("state") if isinstance(value.get("state"), dict) else {}
    try:
        for key in ("backfill_anchor_end", "next_backfill_end_date", "latest_covered_through"):
            if state.get(key):
                date.fromisoformat(str(state[key]))
        if "backfill_complete" in state and not isinstance(state["backfill_complete"], bool):
            raise ValueError("invalid backfill_complete flag")
    except (TypeError, ValueError):
        state = {}
    rows = []
    for raw in value["matches"]:
        if not isinstance(raw, dict):
            continue
        try:
            match_date = date.fromisoformat(str(raw["date"]))
            home, away = str(raw["home"]).strip(), str(raw["away"]).strip()
            home_goals, away_goals = int(raw["home_goals"]), int(raw["away_goals"])
            division = str(raw.get("division") or "")
            if not home or not away or _name_key(home) == _name_key(away) or home_goals < 0 or away_goals < 0:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        rows.append({
            "date": match_date, "division": division, "home": home, "away": away,
            "home_key": _name_key(home), "away_key": _name_key(away),
            "home_goals": home_goals, "away_goals": away_goals,
            "source": "VELTRIX_RECENT_RESULTS_CACHE",
        })
    return {"version": 1, "matches": value["matches"], "state": state}, rows


def _merge_recent_rows(*groups: list[dict]) -> list[dict]:
    unique = {}
    for group in groups:
        for row in group:
            key = (
                row["date"].isoformat(), str(row.get("division") or ""),
                row["home_key"], row["away_key"],
            )
            unique[key] = row
    return sorted(unique.values(), key=lambda row: (row["date"], row.get("division", ""), row["home_key"], row["away_key"]))


def _serialize_recent_cache(rows: list[dict]) -> list[dict]:
    """Keep only score/history fields; omit internal keys to minimize published cache size."""
    return [{
        "date": row["date"].isoformat(),
        "division": str(row.get("division") or ""),
        "home": row["home"],
        "away": row["away"],
        "home_goals": int(row["home_goals"]),
        "away_goals": int(row["away_goals"]),
    } for row in rows]

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="Fixture date YYYY-MM-DD in the selected timezone (defaults to today)")
    parser.add_argument("--history", default="data/open_historical_matches.csv")
    parser.add_argument("--output", default="reports/daily_predictions.json")
    parser.add_argument("--recent-cache", default="reports/recent_results_cache.json")
    parser.add_argument("--timezone", default="Africa/Lagos")
    args = parser.parse_args()
    try:
        target_date = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(args.timezone)).date()
        api = FootballAPI(get_settings())
        payload = api.fixtures(target_date.isoformat(), args.timezone)
        base_history = load_historical_matches(args.history)
        cache_path = Path(args.recent_cache)
        cache_data, cached_rows = _load_recent_cache(cache_path)

        # Refresh one date range per run and persist the cursor/results so a large
        # historical gap is backfilled over time without repeatedly exhausting quota.
        recent_rows, recent_sync = fetch_recent_results_incremental(
            api,
            base_history,
            target_date - timedelta(days=1),
            cache_state=cache_data.get("state") or {},
            timezone_name=args.timezone,
        )
        updated_cache_state = recent_sync.pop("cache_state", cache_data.get("state") or {})
        merged_recent_rows = _merge_recent_rows(cached_rows, recent_rows)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_payload = {
            "version": 1,
            "state": updated_cache_state,
            "matches": _serialize_recent_cache(merged_recent_rows),
        }
        cache_path.write_text(
            json.dumps(cache_payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        market_odds_by_fixture = {}
        # Odds are only useful for fixtures that have not kicked off yet.
        if _has_future_fixtures(payload, target_date, args.timezone):
            try:
                odds_payload = api.odds_for_date(target_date.isoformat(), args.timezone)
                market_odds_by_fixture = extract_market_probabilities(odds_payload)
                odds_sync = {
                    "status": "AVAILABLE" if market_odds_by_fixture else "NO_VALID_1X2_ODDS",
                    "fixtures_with_odds": len(market_odds_by_fixture),
                    "snapshot_date": target_date.isoformat(),
                    "warning": None,
                }
            except (FootballAPIError, ValueError) as exc:
                odds_sync = {
                    "status": "UNAVAILABLE",
                    "fixtures_with_odds": 0,
                    "snapshot_date": target_date.isoformat(),
                    "warning": str(exc),
                }
        else:
            odds_sync = {
                "status": "SKIPPED_NO_FUTURE_FIXTURES",
                "fixtures_with_odds": 0,
                "snapshot_date": target_date.isoformat(),
                "warning": None,
            }

        report = build_daily_report(
            payload,
            args.history,
            as_of=target_date,
            timezone_name=args.timezone,
            additional_historical_matches=merged_recent_rows,
            base_historical_matches=base_history,
            market_odds_by_fixture=market_odds_by_fixture,
        )
        report["recent_results_sync"] = recent_sync
        base_history_through = max(
            (row["date"].isoformat() for row in base_history if row.get("date") < target_date),
            default=None,
        )
        refresh_status = str(recent_sync.get("status") or "UNKNOWN").upper()
        cache_backfill_complete = bool(updated_cache_state.get("backfill_complete"))
        latest_covered = updated_cache_state.get("latest_covered_through")
        contiguous_candidate = max(
            (value for value in (base_history_through, latest_covered) if value),
            default=None,
        )
        refresh_complete = cache_backfill_complete and (
            not contiguous_candidate or contiguous_candidate >= (target_date - timedelta(days=1)).isoformat()
        )
        report["historical_data_coverage"] = {
            "status": "CONTIGUOUS_THROUGH_TARGET_MINUS_ONE" if refresh_complete else "GAPPED_OR_STALE",
            "base_history_through": base_history_through,
            "contiguous_through": contiguous_candidate if refresh_complete else base_history_through,
            "latest_available_match_date": report.get("historical_data_through"),
            "refresh_status": refresh_status,
            "requested_start": recent_sync.get("requested_start"),
            "requested_end": recent_sync.get("requested_end"),
            "covered_from": recent_sync.get("covered_from"),
            "covered_through": recent_sync.get("covered_through"),
            "ranges_succeeded": recent_sync.get("ranges_succeeded"),
            "ranges_requested": recent_sync.get("ranges_requested"),
            "backfill_complete": cache_backfill_complete,
            "cache_path": str(cache_path),
        }
        report["live_odds_sync"] = odds_sync
        report["fixtures_with_market_odds"] = sum(
            isinstance(item.get("market_probabilities"), dict)
            for item in report.get("predictions", [])
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "date": target_date.isoformat(),
            "fixtures_received": report["fixtures_received"],
            "same_day_pre_match_fixtures": report["same_day_pre_match_fixtures"],
            "future_fixtures_considered": report["future_fixtures_considered"],
            "past_kickoffs_excluded": report["past_kickoffs_excluded"],
            "fixtures_excluded_other_date_or_status": report["fixtures_excluded_other_date_or_status"],
            "predictions_created": report["predictions_created"],
            "insufficient_history": report["insufficient_history"],
            "unsupported_competitions": report.get("unsupported_competitions", 0),
            "unsupported_competition_breakdown": report.get("unsupported_competition_breakdown", {}),
            "possible_team_name_mismatches": report["possible_team_name_mismatches"],
            "historical_data_through": report.get("historical_data_through"),
            "historical_matches_available": report.get("historical_matches_available", 0),
            "recent_results_sync": recent_sync,
            "live_odds_sync": odds_sync,
            "fixtures_with_market_odds": report["fixtures_with_market_odds"],
            "output": str(output),
            "model_status": report["model_status"],
        }, indent=2))
    except (RuntimeError, ValueError, FootballAPIError, OSError) as exc:
        print(f"DAILY PREDICTION RUN FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def _has_future_fixtures(payload: dict, target_date: date, timezone_name: str) -> bool:
    """Return whether the payload contains a same-local-day fixture still to start."""
    from app.live_predictions import _fixture_parts
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(timezone_name))
    response = payload.get("response")
    if not isinstance(response, list):
        return False
    return any(
        (part := _fixture_parts(item, timezone_name))
        and part["kickoff_date"] == target_date
        and part["kickoff_datetime"] > now
        for item in response
    )


if __name__ == "__main__":
    main()
