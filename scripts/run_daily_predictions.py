"""Fetch today's fixtures, refresh completed results, and write an experimental report."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from app.config import get_settings
from app.football_api import FootballAPI, FootballAPIError
from app.live_predictions import _name_key, build_daily_report, load_historical_matches
from app.recent_results import fetch_recent_results_incremental
from app.live_odds import extract_market_probabilities
from app.api_football_odds import APIFootballClient, APIFootballError
import math



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
        fixture_id = raw.get("fixture_id")
        try:
            fixture_id = int(fixture_id) if fixture_id is not None else None
        except (TypeError, ValueError):
            fixture_id = None
        fixture_status = str(raw.get("fixture_status") or "FT").upper()
        rows.append({
            "date": match_date, "division": division, "home": home, "away": away,
            "home_key": _name_key(home), "away_key": _name_key(away),
            "home_goals": home_goals, "away_goals": away_goals,
            "fixture_id": fixture_id, "fixture_status": fixture_status,
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
        "fixture_id": row.get("fixture_id") if isinstance(row.get("fixture_id"), int) else None,
        "fixture_status": str(row.get("fixture_status") or "FT"),
    } for row in rows]


def _merge_api_sports_market_odds(
    report: dict,
    odds_payload: dict,
    *,
    timezone_name: str = "Africa/Lagos",
) -> int:
    """Attach real, de-vigged API-Sports 1X2 consensus by date and team names.

    Provider fixture IDs are not interchangeable, so matching deliberately uses
    normalized home/away names and the local kickoff date. Ambiguous or incomplete
    markets are ignored rather than guessed.
    """
    from zoneinfo import ZoneInfo

    rows = odds_payload.get("response")
    predictions = report.get("predictions")
    if not isinstance(rows, list) or not isinstance(predictions, list):
        return 0
    zone = ZoneInfo(timezone_name)
    markets: dict[tuple[str, str, str], list[dict[str, float]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        prices = row.get("odds")
        if not isinstance(prices, dict):
            continue
        try:
            odds = {key: float(prices[key]) for key in ("home", "draw", "away")}
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if not all(math.isfinite(value) and value > 1.0 for value in odds.values()):
            continue
        day = str(row.get("date") or "")
        home_key, away_key = _name_key(str(row.get("home_team") or "")), _name_key(str(row.get("away_team") or ""))
        if not day or not home_key or not away_key:
            continue
        implied = {key: 1.0 / value for key, value in odds.items()}
        total = sum(implied.values())
        if not math.isfinite(total) or total <= 0:
            continue
        key = (day, home_key, away_key)
        markets.setdefault(key, []).append({name: value / total for name, value in implied.items()})

    attached = 0
    for prediction in predictions:
        if not isinstance(prediction, dict) or prediction.get("status") not in {
            "EXPERIMENTAL_ONLY", "INSUFFICIENT_HISTORY", "UNSUPPORTED_COMPETITION"
        }:
            continue
        raw_kickoff = prediction.get("kickoff_local") or prediction.get("kickoff")
        if not isinstance(raw_kickoff, str):
            continue
        try:
            kickoff = datetime.fromisoformat(raw_kickoff.replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=zone)
            day = kickoff.astimezone(zone).date().isoformat()
        except (ValueError, OverflowError):
            continue
        key = (
            day,
            _name_key(str(prediction.get("home_team") or "")),
            _name_key(str(prediction.get("away_team") or "")),
        )
        candidates = markets.get(key, [])
        if not candidates:
            continue
        count = len(candidates)
        probabilities = {
            outcome: sum(item[outcome] for item in candidates) / count
            for outcome in ("home", "draw", "away")
        }
        total = sum(probabilities.values())
        if not math.isfinite(total) or total <= 0:
            continue
        probabilities = {key: round(value / total, 6) for key, value in probabilities.items()}
        prediction["market_model"] = "api_sports_bookmaker_consensus"
        prediction["market_probabilities"] = {
            "home_win": probabilities["home"],
            "draw": probabilities["draw"],
            "away_win": probabilities["away"],
        }
        prediction["market_bookmakers_count"] = count
        prediction["market_updated_at"] = None
        prediction["market_method"] = "equal-weight mean of bookmaker-specific de-vigged API-Sports 1X2 prices"
        attached += 1
    return attached


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
        api_sports_odds_status = "NOT_CONFIGURED"
        api_sports_odds_attached = 0
        # API-Sports is the verified real-bookmaker feed used by the Telegram
        # command centre. Use it as an optional enrichment source when the same
        # key is configured in GitHub Actions; never require or print the key.
        if os.environ.get("API_FOOTBALL_KEY", "").strip():
            try:
                api_sports_payload = APIFootballClient().odds_for_date(
                    target_date.isoformat(), timezone=args.timezone
                )
                api_sports_odds_attached = _merge_api_sports_market_odds(
                    report, api_sports_payload, timezone_name=args.timezone
                )
                provider_odds_status = str(
                    (api_sports_payload.get("_veltrix_meta") or {}).get("status") or "UNKNOWN"
                )
                if api_sports_odds_attached:
                    api_sports_odds_status = "AVAILABLE"
                elif provider_odds_status == "NO_ODDS_RETURNED":
                    api_sports_odds_status = "NO_ODDS_RETURNED"
                else:
                    # Provider rows alone do not prove report integration. Only
                    # call it AVAILABLE after at least one fixture was matched.
                    api_sports_odds_status = "NO_MATCHED_1X2_ODDS"
            except APIFootballError:
                api_sports_odds_status = "UNAVAILABLE"
            except Exception:
                # Optional enrichment must never suppress the primary report.
                api_sports_odds_status = "UNAVAILABLE"
        report["live_odds_sync"] = {
            **odds_sync,
            # Keep the original FootballAPI feed status for diagnostics, but make
            # the headline status reflect the combined report integration. This
            # avoids saying "NO_VALID_1X2_ODDS" when API-Sports successfully
            # attached real bookmaker consensus to report fixtures.
            "football_api_status": odds_sync.get("status"),
            "football_api_fixtures_with_odds": odds_sync.get("fixtures_with_odds", 0),
            "status": (
                "AVAILABLE" if api_sports_odds_attached > 0
                else odds_sync.get("status", "UNKNOWN")
            ),
            "api_sports_status": api_sports_odds_status,
            "api_sports_fixtures_with_odds": api_sports_odds_attached,
        }
        report["fixtures_with_market_odds"] = sum(
            isinstance(item.get("market_probabilities"), dict)
            for item in report.get("predictions", [])
        )
        # Distinguish a report built from this live run from a reused snapshot.
        # The publisher adds command_data_publication=PUBLISHED only after the
        # public command-data write succeeds.
        report["publication_status"] = "LIVE_REPORT_GENERATED_PENDING_PUBLICATION"
        report["publication_notice"] = (
            "Generated from this run's live fixture response. Public publication "
            "is confirmed separately by command_data_publication."
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
