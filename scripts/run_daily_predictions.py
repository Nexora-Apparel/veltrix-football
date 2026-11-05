"""Fetch today's fixtures, refresh completed results, and write an experimental report."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from app.live_predictions import LEAGUE_DIVISION_BY_CODE, LEAGUE_DIVISION_BY_ID, _name_key, build_daily_report, load_historical_matches
from app.recent_results import fetch_recent_results_incremental
from app.api_football_odds import APIFootballError  # legacy error type for compatibility helpers only
from app.provider_adapters import FiveDollarFootballClient, ProviderAPIError, enrich_report_with_multi_source_odds, supplement_fixtures_from_odds_api, supplement_fixtures_from_infersports
from app.value_bets_runtime import attach_value_bet_screens
from app.value_intelligence_runtime import attach_value_intelligence
import math



def _load_recent_cache(path: Path) -> tuple[dict, list[dict]]:
    """Load the public cache defensively and normalize dates/team keys for modelling."""
    empty = {"version": 2, "matches": [], "state": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty, []
    # The publisher and workflow persist cache schema v2. Accept v2 so the
    # incremental cursor and historical matches survive between scheduled runs;
    # continue accepting v1 caches for a safe one-time migration.
    if (
        not isinstance(value, dict)
        or value.get("version") not in (1, 2)
        or not isinstance(value.get("matches"), list)
    ):
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
            "source_provider": str(raw.get("source_provider") or "LEGACY_UNATTRIBUTED"),
            "source": "VELTRIX_RECENT_RESULTS_CACHE",
        })
    return {"version": 2, "matches": value["matches"], "state": state}, rows


def _cache_backfill_complete(state: dict[str, Any]) -> bool:
    """A backfill is complete only when the persisted cache has no known gaps."""
    return bool(state.get("backfill_complete")) and not state.get("history_gaps") and not state.get("history_plan_limited_dates")


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


def _filter_licensed_recent_history(rows: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Use only sources with an explicit commercial/redistribution basis in live modelling."""
    allowed = {"5dollarfootballapi", "openligadb"}
    accepted = []
    excluded: dict[str, int] = {}
    for row in rows:
        source = str(row.get("source_provider") or "LEGACY_UNATTRIBUTED").strip()
        if source.casefold() in allowed:
            accepted.append(row)
        else:
            excluded[source] = excluded.get(source, 0) + 1
    return accepted, excluded


def _serialize_recent_cache(rows: list[dict]) -> list[dict]:
    """Keep score/history fields and explicit source licensing metadata."""
    return [{
        "date": row["date"].isoformat(),
        "division": str(row.get("division") or ""),
        "home": row["home"],
        "away": row["away"],
        "home_goals": int(row["home_goals"]),
        "away_goals": int(row["away_goals"]),
        "fixture_id": row.get("fixture_id") if isinstance(row.get("fixture_id"), int) else None,
        "fixture_status": str(row.get("fixture_status") or "FT"),
        "source_provider": str(row.get("source_provider") or "LEGACY_UNATTRIBUTED"),
        "source_license": str(row.get("source_license") or (
            "5DOLLAR_API_COMMERCIAL_WITH_ATTRIBUTION"
            if str(row.get("source_provider") or "").casefold() == "5dollarfootballapi"
            else "ODBL-1.0" if str(row.get("source_provider") or "").casefold() == "openligadb"
            else "UNVERIFIED_LEGACY_SOURCE"
        )),
        "source_attribution": str(row.get("source_attribution") or (
            "5DollarFootballAPI" if str(row.get("source_provider") or "").casefold() == "5dollarfootballapi"
            else "OpenLigaDB" if str(row.get("source_provider") or "").casefold() == "openligadb"
            else "Source not recorded"
        )),
    } for row in rows]


def _combined_odds_status(football_api_status: str, api_sports_fixtures_attached: int) -> str:
    """Report the effective odds status without hiding source-specific diagnostics."""
    return "AVAILABLE" if api_sports_fixtures_attached > 0 else football_api_status

def _safe_api_sports_error(exc: Exception) -> str:
    """Keep provider diagnostics useful without exposing arbitrary exception text."""
    if isinstance(exc, APIFootballError):
        return str(exc)
    return f"Unexpected API-Sports integration error ({type(exc).__name__})."


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
            "EXPERIMENTAL_ONLY", "EXPERIMENTAL_LOW_DATA", "INSUFFICIENT_HISTORY", "UNSUPPORTED_COMPETITION"
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
        availability = prediction.get("data_availability")
        if isinstance(availability, dict):
            availability["live_bookmaker_odds"] = "AVAILABLE_FROM_API_FOOTBALL"
        attached += 1
    return attached


def _limit_fixture_payload(
    payload: dict,
    limit: int = 0,
    timezone_name: str = "Africa/Lagos",
    as_of_date: date | None = None,
    now: datetime | None = None,
) -> dict:
    """Select the requested local date and reconcile without dropping provenance.

    The legacy limit argument is retained for CLI compatibility but is no
    longer allowed to truncate discovered fixtures. Fixture visibility and
    provider traceability take precedence over a fixed report-size target.
    """
    from copy import deepcopy
    from app.fixture_identity import reconcile_fixture_rows

    result = deepcopy(payload)
    rows = result.get("response")
    if not isinstance(rows, list):
        raise ValueError("Fixture provider response must contain a response list.")
    zone = ZoneInfo(timezone_name)
    current_time = now.astimezone(zone) if now is not None and now.tzinfo else (
        now.replace(tzinfo=zone) if now is not None else datetime.now(zone)
    )
    target_date = as_of_date or current_time.date()
    eligible: list[dict] = []
    invalid_source_records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
        league = row.get("league") if isinstance(row.get("league"), dict) else {}
        teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        raw = fixture.get("date")
        if not raw:
            invalid_source_records.append({
                "provider": str(row.get("_veltrix_source") or row.get("provider") or "UNKNOWN"),
                "fixture_id": fixture.get("id"),
                "competition_id": league.get("id"),
                "home_team_id": home.get("id"), "away_team_id": away.get("id"),
                "reason": "MISSING_KICKOFF",
            })
            continue
        try:
            kickoff = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=zone)
            kickoff = kickoff.astimezone(zone)
        except (TypeError, ValueError, OverflowError):
            invalid_source_records.append({
                "provider": str(row.get("_veltrix_source") or row.get("provider") or "UNKNOWN"),
                "fixture_id": fixture.get("id"),
                "competition_id": league.get("id"),
                "home_team_id": home.get("id"), "away_team_id": away.get("id"),
                "raw_kickoff": str(raw),
                "reason": "INVALID_KICKOFF",
            })
            continue
        if kickoff.date() == target_date:
            eligible.append(row)

    canonical, reconciliation = reconcile_fixture_rows(
        eligible, timezone_name=timezone_name,
    )
    # Do not enforce the historical 25-row cap: it silently discarded real
    # fixtures and their provider IDs before the report could explain coverage.
    result["response"] = canonical
    meta = result.get("_veltrix_meta")
    if not isinstance(meta, dict):
        meta = {}
        result["_veltrix_meta"] = meta

    def source_counts(items: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            provenance = item.get("_veltrix_provenance")
            source_names = (
                [str(record.get("provider") or "UNKNOWN") for record in provenance if isinstance(record, dict)]
                if isinstance(provenance, list) and provenance else
                [str(item.get("_veltrix_source") or item.get("provider") or "UNKNOWN")]
            )
            for source_name in source_names:
                counts[source_name] = counts.get(source_name, 0) + 1
        return dict(sorted(counts.items()))

    meta["fixtures_before_reconciliation"] = len(eligible)
    meta["invalid_fixture_source_records"] = invalid_source_records
    meta["fixture_reconciliation"] = reconciliation
    meta["fixtures_after_reconciliation"] = len(canonical)
    meta["fixtures_by_source_before_reconciliation"] = source_counts(eligible)
    meta["fixtures_by_source_after_reconciliation"] = source_counts(canonical)
    meta["legacy_fixture_cap_ignored"] = max(0, int(limit or 0))
    meta["fixture_selection_policy"] = reconciliation["policy"] + "; no fixed fixture cap"
    return result

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=None, help="Fixture date YYYY-MM-DD in the selected timezone (defaults to today)")
    parser.add_argument("--history", default="data/open_historical_matches.csv")
    parser.add_argument("--output", default="reports/daily_predictions.json")
    parser.add_argument("--recent-cache", default="reports/recent_results_cache.json")
    parser.add_argument("--timezone", default="Africa/Lagos")
    parser.add_argument("--max-fixtures", type=int, default=0, help="Deprecated compatibility option; all discovered same-day fixtures are retained")
    args = parser.parse_args()
    try:
        target_date = date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo(args.timezone)).date()
        api = FiveDollarFootballClient()
        primary_fixture_error = None
        primary_fixture_error_details = None
        primary_provider_status = "SUCCESS"
        if not api.api_key:
            primary_provider_status = "NOT_CONFIGURED"
            primary_fixture_error = "MISSING_API_KEY"
            payload = {
                "response": [],
                "_veltrix_meta": {
                    "provider": "5DollarFootballAPI",
                    "primary_provider_status": primary_provider_status,
                },
            }
            primary_fixture_count = 0
        else:
            try:
                payload = api.fixtures(target_date.isoformat(), args.timezone)
                primary_fixture_count = len(payload.get("response") or [])
            except ProviderAPIError as exc:
                primary_fixture_error = type(exc).__name__
                primary_fixture_error_details = {
                    "status_code": getattr(exc, "status_code", None),
                    "retry_after_seconds": getattr(exc, "retry_after_seconds", None),
                    "rate_limit_remaining": getattr(exc, "rate_limit_remaining", None),
                    "rate_limit_reset": getattr(exc, "rate_limit_reset", None),
                }
                primary_provider_status = "RATE_LIMITED" if "HTTP 429" in str(exc) else "UNAVAILABLE"
                primary_fixture_count = 0
                payload = {
                    "response": [],
                    "_veltrix_meta": {
                        "provider": "5DollarFootballAPI",
                        "primary_provider_status": primary_provider_status,
                        "primary_error_type": primary_fixture_error,
                    },
                }
        # The primary feed may be rate-limited or expose only a small set of
        # leagues. In either case, use the already-connected Odds API and
        # InferSports fixture feeds as independent same-day discovery sources.
        payload = supplement_fixtures_from_odds_api(
            payload,
            target_date.isoformat(),
            timezone_name=args.timezone,
        )
        # InferSports broadens fixture discovery independently of its disabled-by-default
        # odds enrichment. The report builder still enforces competition and history rules.
        payload = supplement_fixtures_from_infersports(
            payload,
            target_date.isoformat(),
            timezone_name=args.timezone,
        )
        # Bound model workload and Telegram report size after cross-provider discovery.
        payload = _limit_fixture_payload(payload, args.max_fixtures, args.timezone, as_of_date=target_date)
        if primary_provider_status != "SUCCESS" and not (payload.get("response") or []):
            raise ProviderAPIError(
                "Primary fixture provider was unavailable and no supplemental source returned same-day fixtures."
            )
        base_history = load_historical_matches(args.history)
        licensed_history_only = os.getenv("VELTRIX_LIVE_HISTORY_LICENSED_ONLY", "").strip().lower() in {"1", "true", "yes"}
        if licensed_history_only:
            # The 238k Football-Data-derived snapshot is retained for research
            # backtests only; production live forecasts use explicitly licensed rows.
            base_history = []
        cache_path = Path(args.recent_cache)
        cache_data, cached_rows = _load_recent_cache(cache_path)

        # Refresh one date range per run only when the primary provider is
        # healthy. In licensed-only production mode, anchor the incremental cursor
        # to verified provider rows already in the cache, never the research dataset.
        history_anchor = base_history
        history_cache_state = dict(cache_data.get("state") or {})
        if licensed_history_only:
            history_anchor, _ = _filter_licensed_recent_history(cached_rows)
            if history_cache_state.get("history_source_mode") != "LICENSED_ONLY":
                # Start a clean, provider-attributed 56-day bootstrap. The provider
                # supports three months on the Free plan; one seven-day chunk is
                # fetched per scheduled run to stay inside the hourly request cap.
                bootstrap_end = target_date - timedelta(days=1)
                history_cache_state = {
                    "coverage_state_version": 2,
                    "source_provider": "5DollarFootballAPI",
                    "history_source_mode": "LICENSED_ONLY",
                    "bootstrap_start_date": (bootstrap_end - timedelta(days=55)).isoformat(),
                    "backfill_anchor_end": bootstrap_end.isoformat(),
                    "next_backfill_end_date": bootstrap_end.isoformat(),
                    "backfill_complete": False,
                }
        if primary_provider_status == "SUCCESS":
            try:
                recent_rows, recent_sync = fetch_recent_results_incremental(
                    api,
                    history_anchor,
                    target_date - timedelta(days=1),
                    cache_state=history_cache_state,
                    timezone_name=args.timezone,
                )
            except ProviderAPIError as exc:
                recent_rows = []
                recent_sync = {
                    "status": "PRIMARY_PROVIDER_UNAVAILABLE",
                    "results_added": 0,
                    "requested_start": None,
                    "requested_end": (target_date - timedelta(days=1)).isoformat(),
                    "covered_from": None,
                    "covered_through": (cache_data.get("state") or {}).get("latest_covered_through"),
                    "ranges_succeeded": 0,
                    "ranges_requested": 0,
                    "warning": "Recent-results refresh skipped after primary-provider failure; existing cache retained.",
                    "provider_error_type": type(exc).__name__,
                    "provider_error_details": {
                        "status_code": getattr(exc, "status_code", None),
                        "retry_after_seconds": getattr(exc, "retry_after_seconds", None),
                        "rate_limit_remaining": getattr(exc, "rate_limit_remaining", None),
                        "rate_limit_reset": getattr(exc, "rate_limit_reset", None),
                    },
                    "cache_state": cache_data.get("state") or {},
                }
        else:
            recent_rows = []
            recent_sync = {
                "status": "SKIPPED_PRIMARY_PROVIDER_UNAVAILABLE",
                "results_added": 0,
                "requested_start": None,
                "requested_end": (target_date - timedelta(days=1)).isoformat(),
                "covered_from": None,
                "covered_through": (cache_data.get("state") or {}).get("latest_covered_through"),
                "ranges_succeeded": 0,
                "ranges_requested": 0,
                "warning": "Primary provider was unavailable for fixture discovery; cached historical results were retained without another provider request.",
                "provider_error_type": primary_fixture_error,
                "cache_state": cache_data.get("state") or {},
            }
        updated_cache_state = recent_sync.pop("cache_state", cache_data.get("state") or {})
        merged_recent_rows = _merge_recent_rows(cached_rows, recent_rows)
        if licensed_history_only:
            model_recent_rows, excluded_history_source_counts = _filter_licensed_recent_history(merged_recent_rows)
        else:
            model_recent_rows, excluded_history_source_counts = merged_recent_rows, {}
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_payload = {
            "version": 2,
            "state": updated_cache_state,
            "matches": _serialize_recent_cache(merged_recent_rows),
        }
        cache_path.write_text(
            json.dumps(cache_payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

        # External bookmaker prices are attached after forecasts are built; they
        # never alter model probabilities and their failures do not block the report.
        market_odds_by_fixture = {}

        report = build_daily_report(
            payload,
            args.history,
            as_of=target_date,
            timezone_name=args.timezone,
            additional_historical_matches=model_recent_rows,
            base_historical_matches=base_history,
            market_odds_by_fixture=market_odds_by_fixture,
        )
        report["recent_results_sync"] = recent_sync
        history_coverage = report.setdefault("historical_data_coverage", {})
        model_source_counts = {}
        for source_row in model_recent_rows:
            source_name = str(source_row.get("source_provider") or "LEGACY_UNATTRIBUTED")
            model_source_counts[source_name] = model_source_counts.get(source_name, 0) + 1
        history_coverage.update({
            "live_history_mode": "LICENSED_PROVIDERS_ONLY" if licensed_history_only else "RESEARCH_MODE",
            "base_history_rows_used": len(base_history),
            "recent_cache_rows_used": len(model_recent_rows),
            "model_history_source_counts": model_source_counts,
            "excluded_unverified_history_rows": sum(excluded_history_source_counts.values()),
            "excluded_unverified_history_source_counts": excluded_history_source_counts,
            "source_provenance_status": (
                "LICENSED_PROVIDERS_ONLY_WITH_LEGACY_EXCLUDED"
                if licensed_history_only else "RESEARCH_MODE_NOT_LICENSE_FILTERED"
            ),
        })
        if licensed_history_only and isinstance(history_coverage, dict):
            history_coverage["legacy_unattributed_rows"] = excluded_history_source_counts.get("LEGACY_UNATTRIBUTED", 0)
        fixture_meta = payload.get("_veltrix_meta") if isinstance(payload.get("_veltrix_meta"), dict) else {}
        report["primary_provider_request"] = {
            "provider": fixture_meta.get("provider", "5DollarFootballAPI"),
            "status": primary_provider_status,
            "error_type": primary_fixture_error,
            "error_details": primary_fixture_error_details,
            "requests_remaining": fixture_meta.get("requests_remaining"),
            "pages_fetched": fixture_meta.get("pages_fetched", 1),
            "fixtures_received": primary_fixture_count,
        }
        # Make supplemental discovery measurable in the saved report and CI logs.
        # This separates successful provider execution from actual model eligibility.
        report["fixture_discovery"] = {
            "primary_provider": fixture_meta.get("provider", "5DollarFootballAPI"),
            "primary_provider_status": primary_provider_status,
            "supplemental_provider": fixture_meta.get("supplemental_fixture_source"),
            "the_odds_api": {
                "fixtures_added": int(fixture_meta.get("supplemental_fixtures_added", 0) or 0),
                "sports_queried": fixture_meta.get("supplemental_sports_queried", []),
                "sports_failed": fixture_meta.get("supplemental_sports_failed", []),
            },
            "infersports": fixture_meta.get("infersports_fixture_discovery", {"status": "NOT_RUN"}),
            "fixtures_total_after_supplement": int(fixture_meta.get("fixtures_total_after_supplement", len(payload.get("response") or [])) or 0),
            "fixture_reconciliation": fixture_meta.get("fixture_reconciliation", {}),
            "fixture_selection": {
                "policy": fixture_meta.get("fixture_selection_policy"),
                "before_reconciliation": fixture_meta.get("fixtures_by_source_before_reconciliation", {}),
                "after_reconciliation": fixture_meta.get("fixtures_by_source_after_reconciliation", {}),
                "legacy_fixture_cap_ignored": fixture_meta.get("legacy_fixture_cap_ignored", 0),
            },
            "future_fixtures_considered": report.get("future_fixtures_considered", 0),
            "predictions_created": report.get("predictions_created", 0),
            "insufficient_history": report.get("insufficient_history", 0),
            "possible_team_name_mismatches": report.get("possible_team_name_mismatches", 0),
        }
        base_history_through = max(
            (row["date"].isoformat() for row in base_history if row.get("date") < target_date),
            default=None,
        )
        refresh_status = str(recent_sync.get("status") or "UNKNOWN").upper()
        base_backfill_complete = bool(updated_cache_state.get("backfill_complete"))
        cache_backfill_complete = _cache_backfill_complete(updated_cache_state)
        latest_covered = updated_cache_state.get("latest_covered_through")
        contiguous_candidate = max(
            (value for value in (base_history_through, latest_covered) if value),
            default=None,
        )
        history_gaps = updated_cache_state.get("history_gaps") or []
        plan_limited_dates = updated_cache_state.get("history_plan_limited_dates") or []
        cache_source_counts = {}
        for cached_match in merged_recent_rows:
            source_name = str(cached_match.get("source_provider") or "LEGACY_UNATTRIBUTED")
            cache_source_counts[source_name] = cache_source_counts.get(source_name, 0) + 1
        legacy_unattributed_rows = cache_source_counts.get("LEGACY_UNATTRIBUTED", 0)
        refresh_complete = cache_backfill_complete and not history_gaps and not plan_limited_dates and (
            not contiguous_candidate or contiguous_candidate >= (target_date - timedelta(days=1)).isoformat()
        )
        report["historical_data_coverage"] = {
            "status": "CONTIGUOUS_THROUGH_TARGET_MINUS_ONE" if refresh_complete else "GAPPED_OR_STALE",
            "base_history_through": base_history_through,
            "contiguous_through": contiguous_candidate if refresh_complete else None,
            "latest_available_match_date": report.get("historical_data_through"),
            "refresh_status": refresh_status,
            "requested_start": recent_sync.get("requested_start"),
            "requested_end": recent_sync.get("requested_end"),
            "covered_from": recent_sync.get("covered_from"),
            "covered_through": recent_sync.get("covered_through"),
            "ranges_succeeded": recent_sync.get("ranges_succeeded"),
            "ranges_requested": recent_sync.get("ranges_requested"),
            # This flag describes the complete contiguous refresh, not merely
            # whether the original historical import finished. Keep the base
            # import marker separately so unresolved recent gaps cannot be
            # mistaken for a complete history.
            "backfill_complete": refresh_complete,
            "base_backfill_complete": base_backfill_complete,
            "incremental_history_complete": refresh_complete,
            "retryable_gap_date_count": len(history_gaps) if isinstance(history_gaps, list) else 0,
            "provider_plan_limited_date_count": len(plan_limited_dates) if isinstance(plan_limited_dates, list) else 0,
            "provider_plan_limited_dates": plan_limited_dates if isinstance(plan_limited_dates, list) else [],
            "recent_cache_rows": len(merged_recent_rows),
            "recent_cache_source_counts": cache_source_counts,
            "legacy_unattributed_rows": legacy_unattributed_rows,
            "source_provenance_status": "PARTIAL_LEGACY_UNATTRIBUTED" if legacy_unattributed_rows else "ATTRIBUTED",
            "cache_path": str(cache_path),
        }
        report = enrich_report_with_multi_source_odds(
            report,
            payload,
            timezone_name=args.timezone,
        )
        # Build all-market value diagnostics from actual same-bookmaker prices.
        # Alerts remain locked until repeated chronological validation passes.
        report = attach_value_bet_screens(report, validation_certificate=None)
        report = attach_value_intelligence(report)
        multi_odds = report.get("multi_source_odds_sync") or {}
        five_status = (multi_odds.get("five_dollar") or {}).get("status", "NOT_CONFIGURED")
        odds_api_status = (multi_odds.get("the_odds_api") or {}).get("status", "NOT_CONFIGURED")
        infer_status = (multi_odds.get("infer_sports") or {}).get("status", "DISABLED")
        all_skipped = five_status == "SKIPPED_NO_FUTURE_FIXTURES" and odds_api_status == "SKIPPED_NO_FUTURE_FIXTURES"
        any_available = any(status == "AVAILABLE" for status in (five_status, odds_api_status, infer_status))
        combined_status = "SKIPPED_NO_FUTURE_FIXTURES" if all_skipped else "AVAILABLE" if any_available else "NO_MATCHED_MARKET_ODDS"
        report["live_odds_sync"] = {
            "status": combined_status,
            "primary_fixture_provider": "5DollarFootballAPI",
            "five_dollar_status": five_status,
            "the_odds_api_status": odds_api_status,
            "infer_sports_status": infer_status,
            "fixtures_with_market_odds": sum(
                bool(item.get("five_dollar_market_odds") or item.get("the_odds_api_market_odds") or item.get("infer_sports_market_odds"))
                for item in report.get("predictions", []) if isinstance(item, dict)
            ),
            "note": "Market odds are reference data; forecast probabilities remain experimental and unchanged.",
        }
        report["fixtures_with_market_odds"] = report["live_odds_sync"]["fixtures_with_market_odds"]
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
            "fixture_discovery": report["fixture_discovery"],
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
            "live_odds_sync": report["live_odds_sync"],
            "fixtures_with_market_odds": report["fixtures_with_market_odds"],
            "output": str(output),
            "model_status": report["model_status"],
        }, indent=2))
    except (RuntimeError, ValueError, OSError, ProviderAPIError) as exc:
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
