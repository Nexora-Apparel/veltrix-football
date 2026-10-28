"""Safe Telegram Command Centre router for Veltrix Football.

Formats command replies and reads only explicitly supplied report data. It never
invents odds or treats experimental estimates as validated bets.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Any

COMMANDS: dict[str, str] = {
    "/start": "Open the Veltrix Football Command Centre.",
    "/help": "Show available commands.",
    "/today": "Show today's report, if a current report is available.",
    "/tomorrow": "Show tomorrow's fixtures only when a source supports that date.",
    "/fixtures": "Show fixtures available in the current report.",
    "/match": "Inspect a named fixture: /match Arsenal vs Chelsea",
    "/live": "Show live matches only when live-status data is connected.",
    "/overunder": "PRIMARY MARKET: experimental Over/Under 0.5–4.5 goal probabilities from model expected goals.",
    "/btts": "PRIMARY MARKET: experimental Both Teams To Score Yes/No probabilities from model expected goals.",
    "/goals": "Expected-goals summary for available forecasts.",
    "/cleansheet": "Clean-sheet estimates; unavailable until calibrated team-goal probabilities exist.",
    "/value": "Value screen status; candidates stay disabled until the model passes validation.",
    "/overvalue": "Over/Under value screen status; requires model probabilities and real odds.",
    "/bttsvalue": "BTTS value screen status; requires model probabilities and real odds.",
    "/odds": "Show matched BTTS and Over/Under bookmaker prices from the connected multi-source report.",
    "/oddsdiag": "Inspect saved multi-source fixture and odds coverage without spending API quota.",
    "/10odds": "Research shortlist targeting total decimal odds near 10.00 only when real odds are available; not a guarantee.",
    "/builder": "Explain the conservative multi-pick builder rules.",
    "/slipcheck": "Check a supplied decimal-odds combination for arithmetic only.",
    "/results": "Show retrospective paper-tracking results when a ledger is available.",
    "/performance": "Show model-versus-market paper metrics when a ledger is available.",
    "/status": "Show command/data availability status.",
}

NEW_MESSAGE_HEADER = "🔔 🆕 NEW VELTRIX UPDATE\n━━━━━━━━━━━━━━━━━━━━"


def _reply(body: str) -> str:
    return f"{NEW_MESSAGE_HEADER}\n{body.strip()}"


def _report_predictions(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    report_date = report.get("as_of_date")
    if report_date:
        try:
            if str(report_date) != datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat():
                return []
        except (TypeError, ValueError):
            return []
    rows = report.get("predictions", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _kickoff_is_future(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
    expected_date: date | None = None,
) -> bool:
    """Accept not-yet-started fixtures, optionally constrained to a report date."""
    raw = row.get("kickoff_local") or row.get("kickoff")
    if not isinstance(raw, str) or not raw.strip():
        return False
    try:
        kickoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        lagos = ZoneInfo("Africa/Lagos")
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=lagos)
        kickoff = kickoff.astimezone(lagos)
        current = now or datetime.now(lagos)
        if current.tzinfo is None:
            current = current.replace(tzinfo=lagos)
        current = current.astimezone(lagos)
        return kickoff > current and (expected_date is None or kickoff.date() == expected_date)
    except (TypeError, ValueError, OverflowError):
        return False


def _future_fixtures(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        return []
    expected_date = None
    report_date = report.get("as_of_date")
    if report_date:
        try:
            expected_date = date.fromisoformat(str(report_date))
        except ValueError:
            return []
    return [
        row for row in _report_predictions(report)
        if _kickoff_is_future(row, expected_date=expected_date)
    ]

def _odds_row_is_future(row: dict[str, Any], *, now: datetime | None = None) -> bool:
    """Fail closed on missing/invalid kickoff data and exclude started fixtures."""
    raw_date, raw_time = row.get("date"), row.get("time")
    if not isinstance(raw_date, str) or not isinstance(raw_time, str):
        return False
    try:
        kickoff_date = date.fromisoformat(raw_date)
        kickoff_time = datetime.strptime(raw_time, "%H:%M").time()
        lagos = ZoneInfo("Africa/Lagos")
        kickoff = datetime.combine(kickoff_date, kickoff_time, tzinfo=lagos)
        current = now or datetime.now(lagos)
        if current.tzinfo is None:
            current = current.replace(tzinfo=lagos)
        return kickoff > current.astimezone(lagos)
    except (TypeError, ValueError, OverflowError):
        return False


def _valid_probability_vector(probabilities: Any) -> bool:
    if not isinstance(probabilities, dict):
        return False
    try:
        values = [float(probabilities[key]) for key in ("home_win", "draw", "away_win")]
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return (
        all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in values)
        and abs(sum(values) - 1.0) <= 0.02
    )


def _forecast_predictions(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return only current-day, future, explicitly usable experimental forecasts."""
    return [
        row for row in _future_fixtures(report)
        if row.get("status") == "EXPERIMENTAL_ONLY"
        and _valid_probability_vector(row.get("probabilities"))
    ]


def _expected_goals(row: dict[str, Any]) -> tuple[float, float] | None:
    """Read finite, plausible Poisson goal means from an explicitly usable forecast."""
    values = row.get("expected_goals")
    if not isinstance(values, dict):
        return None
    try:
        home, away = float(values["home"]), float(values["away"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(x) and 0.0 <= x <= 10.0 for x in (home, away)):
        return None
    return home, away


def _poisson_probability_at_least(k: int, mean: float) -> float:
    """P(X >= k) for a Poisson goal count, evaluated without external libraries."""
    if k <= 0:
        return 1.0
    term = math.exp(-mean)
    cumulative = term
    for goals in range(1, k):
        term *= mean / goals
        cumulative += term
    return min(1.0, max(0.0, 1.0 - cumulative))


def _goal_market_probabilities(row: dict[str, Any]) -> dict[str, float] | None:
    means = _expected_goals(row)
    if means is None:
        return None
    home, away = means
    total = home + away
    # Independent Poisson approximation; explicitly experimental, not calibrated.
    markets = {
        "over_0_prob": _poisson_probability_at_least(1, total),
        "over_1_prob": _poisson_probability_at_least(2, total),
        "over_2_prob": _poisson_probability_at_least(3, total),
        "over_3_prob": _poisson_probability_at_least(4, total),
        "over_4_prob": _poisson_probability_at_least(5, total),
        "btts_yes_prob": (1.0 - math.exp(-home)) * (1.0 - math.exp(-away)),
    }
    return markets

def _saved_market_price_lines(row: dict[str, Any], market_key: str) -> list[str]:
    """Read only actual prices attached to this fixture in the published report."""
    lines: list[str] = []
    five = row.get("five_dollar_market_odds")
    if isinstance(five, dict):
        for book in (five.get("bookmakers") or []):
            if not isinstance(book, dict):
                continue
            if market_key == "btts":
                market = book.get("btts") or {}
                yes, no = market.get("yes"), market.get("no")
                if isinstance(yes, (int, float)) and isinstance(no, (int, float)):
                    lines.append("5DollarFootballAPI · {} · BTTS Yes {:.2f} / No {:.2f}".format(book.get("bookmaker", "bookmaker"), yes, no))
            elif market_key == "totals":
                market = book.get("over_under") or {}
                over, under = market.get("over"), market.get("under")
                if isinstance(over, (int, float)) and isinstance(under, (int, float)):
                    lines.append("5DollarFootballAPI · {} · O/U {}: Over {:.2f} / Under {:.2f}".format(book.get("bookmaker", "bookmaker"), market.get("line", "—"), over, under))
            if len(lines) >= 2:
                break
    odds_api = row.get("the_odds_api_market_odds")
    if isinstance(odds_api, dict):
        markets = odds_api.get("markets") or {}
        for market in (markets.get(market_key) or [])[:2]:
            if not isinstance(market, dict):
                continue
            outcomes = []
            for outcome in market.get("outcomes") or []:
                if not isinstance(outcome, dict) or not isinstance(outcome.get("price"), (int, float)):
                    continue
                label = "{} {:.2f}".format(outcome.get("name", "outcome"), outcome["price"])
                if outcome.get("point") is not None:
                    label += " ({})".format(outcome["point"])
                outcomes.append(label)
            if outcomes:
                lines.append("The Odds API · {} · {}".format(market.get("bookmaker", "bookmaker"), " / ".join(outcomes)))
    oddspapi = row.get("oddspapi_market_odds")
    if isinstance(oddspapi, dict):
        if market_key == "btts":
            for market in (oddspapi.get("btts") or [])[:2]:
                if isinstance(market, dict) and isinstance(market.get("yes"), (int, float)) and isinstance(market.get("no"), (int, float)):
                    lines.append("OddsPapi · {} · BTTS Yes {:.2f} / No {:.2f}".format(market.get("bookmaker", "bookmaker"), market["yes"], market["no"]))
        elif market_key == "totals":
            for market in (oddspapi.get("over_under") or [])[:2]:
                if isinstance(market, dict) and isinstance(market.get("over"), (int, float)) and isinstance(market.get("under"), (int, float)):
                    lines.append("OddsPapi · {} · O/U {}: Over {:.2f} / Under {:.2f}".format(market.get("bookmaker", "bookmaker"), market.get("line", "—"), market["over"], market["under"]))
    return lines[:5]


def _history_notice(report: dict[str, Any] | None) -> str | None:
    if not isinstance(report, dict):
        return None
    notices: list[str] = []
    if str(report.get("publication_status") or "").upper() == "REUSED_SNAPSHOT_NOT_REFRESHED":
        notices.append(
            "SNAPSHOT NOTICE: This is a reused same-day snapshot; fresh fixtures were not fetched in this run."
        )
    sync = report.get("recent_results_sync") or {}
    coverage = report.get("historical_data_coverage") or {}
    if isinstance(sync, dict) and isinstance(coverage, dict):
        if coverage.get("status") == "GAPPED_OR_STALE":
            contiguous = coverage.get("contiguous_through") or "unknown"
            latest = coverage.get("latest_available_match_date") or "unknown"
            succeeded, requested = sync.get("ranges_succeeded"), sync.get("ranges_requested")
            progress = (
                f" {succeeded}/{requested} date ranges refreshed."
                if isinstance(succeeded, int) and isinstance(requested, int) and requested > 0
                else ""
            )
            notices.append(
                "DATA NOTICE: Historical results are incomplete; forecasts may miss matches from the gap. "
                f"History is continuous through {contiguous}; latest available result date is {latest}."
                f"{progress}"
            )
        else:
            status = str(sync.get("status") or "").upper()
            if status and status not in {"COMPLETE", "UP_TO_DATE", "SUCCESS", "OK"}:
                notices.append(
                    f"DATA NOTICE: Recent-results refresh status is {status}; saved history may be incomplete."
                )
    return "\n".join(notices) if notices else None


def _status(report: dict[str, Any] | None, ledger: dict[str, Any] | None) -> str:
    fixtures = _future_fixtures(report)
    predictions = _forecast_predictions(report)
    odds_status = "not connected to this command router"
    if isinstance(report, dict):
        multi = report.get("multi_source_odds_sync") or {}
        meta = report.get("live_odds_sync") or report.get("odds_meta") or report.get("odds") or {}
        if isinstance(multi, dict) and multi:
            five = (multi.get("five_dollar") or {}).get("status", "UNKNOWN")
            odds_api = (multi.get("the_odds_api") or {}).get("status", "UNKNOWN")
            odds_status = f"5DollarFootballAPI {five}; The Odds API {odds_api}"
            if isinstance(meta, dict) and meta.get("fixtures_with_market_odds") is not None:
                odds_status += f" ({meta.get('fixtures_with_market_odds')} matched fixtures)"
        elif isinstance(meta, dict) and meta.get("status"):
            odds_status = str(meta["status"])
    if isinstance(ledger, dict):
        scored_count = len(ledger.get("scored_matches", [])) if isinstance(ledger.get("scored_matches"), list) else 0
        ledger_status = f"available ({scored_count} settled forecast rows)"
    else:
        ledger_status = "not available"
    history_status = "unknown"
    history_coverage = "not reported"
    if isinstance(report, dict):
        sync = report.get("recent_results_sync") or {}
        coverage = report.get("historical_data_coverage") or {}
        if isinstance(sync, dict) and sync.get("status"):
            history_status = str(sync["status"])
            succeeded, requested = sync.get("ranges_succeeded"), sync.get("ranges_requested")
            if isinstance(succeeded, int) and isinstance(requested, int) and requested > 0:
                history_status += f" ({succeeded}/{requested} ranges refreshed)"
        if isinstance(coverage, dict) and coverage.get("status"):
            history_coverage = str(coverage["status"])
            contiguous = coverage.get("contiguous_through")
            latest = coverage.get("latest_available_match_date")
            if contiguous or latest:
                history_coverage += f"; continuous through {contiguous or 'unknown'}, latest available {latest or 'unknown'}"
    report_is_current = isinstance(report, dict) and bool(_report_predictions(report))
    freshness_status = (
        str(report.get("publication_status") or "FRESHNESS_UNMARKED")
        if isinstance(report, dict) else "UNKNOWN"
    )
    # The generator marks its local output pending publication. Once the publisher
    # confirms the public command-data write, avoid presenting that old intermediate
    # state as if publication were still pending.
    if isinstance(report, dict) and report.get("command_data_publication") == "PUBLISHED":
        if freshness_status == "LIVE_REPORT_GENERATED_PENDING_PUBLICATION":
            freshness_status = "LIVE_REPORT_GENERATED_AND_PUBLISHED"
    return (
        "VELTRIX COMMAND CENTRE — STATUS\n"
        f"Current report: {'available' if report_is_current else 'not loaded or no longer current'}\n"
        f"Fixtures in report: {len(fixtures)}\n"
        f"Usable experimental forecasts: {len(predictions)}\n"
        f"Recent-results refresh: {history_status}\n"
        f"Historical coverage: {history_coverage}\n"
        f"Report freshness / reuse: {freshness_status}\n"
        f"Command-data publication: {str(report.get('command_data_publication') or 'UNCONFIRMED') if isinstance(report, dict) else 'UNKNOWN'}\n"
        f"Report multi-source odds integration: {odds_status}\n"
        "/oddsdiag reads saved provider coverage and does not spend API quota.\n"
        f"Paper-tracking ledger: {ledger_status}\n"
        "Betting/value alerts: DISABLED until chronological out-of-sample validation.\n"
        "No bookmaker actions are performed."
    )


def _slipcheck(argument: str) -> str:
    raw = argument.strip()
    if not raw:
        return "Usage: /slipcheck 1.80 2.10 1.65"
    try:
        odds = [float(value) for value in re.split(r"[\s,]+", raw) if value]
    except ValueError:
        return "Send decimal odds as numbers greater than 1, e.g. /slipcheck 1.80 2.10"
    if not odds or any(value <= 1 or value != value or value in (float("inf"), float("-inf")) for value in odds):
        return "Invalid input. Every decimal odd must be a finite number greater than 1."
    total = 1.0
    for value in odds:
        total *= value
    return (
        "SLIP ARITHMETIC CHECK — NOT A BETTING RECOMMENDATION\n"
        f"Selections entered: {len(odds)}\n"
        f"Combined decimal odds: {total:.2f}\n"
        f"Implied break-even probability (before bookmaker margin): {100 / total:.2f}%\n"
        "This does not verify the selections, prices, or likelihood of winning."
    )


def handle_command(
    text: str,
    *,
    report: dict[str, Any] | None = None,
    ledger: dict[str, Any] | None = None,
    odds_data: dict[str, Any] | None = None,
    odds_error: str | None = None,
) -> str:
    """Return a clearly labelled reply for a Telegram command.

    Report and ledger must be loaded by the caller from trusted, current sources.
    Commands never silently fall back to fabricated fixture or odds data.
    """
    message = (text or "").strip()
    if not message.startswith("/"):
        return _reply("Use /help to see the available commands.")
    first, _, argument = message.partition(" ")
    command = first.split("@", 1)[0].casefold()
    if command not in COMMANDS:
        return _reply("Unknown command. Use /help to see available commands.")

    if command in {"/start", "/help"}:
        lines = ["VELTRIX FOOTBALL — COMMAND CENTRE", "", "FIXTURES & MATCHES"]
        lines.extend(f"{cmd} — {desc}" for cmd, desc in COMMANDS.items())
        lines.extend([
            "",
            "SAFETY",
            "Forecasts are experimental. Odds/value screens need real odds and validated probabilities.",
            "No picks or odds are fabricated; no bets are placed.",
        ])
        return _reply("\n".join(lines))

    if command == "/odds":
        # Legacy explicit payload support is retained for tests/integrators; the
        # production webhook reads saved multi-source report data and never calls it.
        if isinstance(odds_data, dict):
            legacy_rows = odds_data.get("response", [])
            if not isinstance(legacy_rows, list) or not legacy_rows:
                return _reply("LIVE BOOKMAKER ODDS — NO PRICES RETURNED\\nThe supplied provider payload contains no usable odds.")
            now_lagos = datetime.now(ZoneInfo("Africa/Lagos"))
            upcoming_legacy = [row for row in legacy_rows if isinstance(row, dict) and _odds_row_is_future(row, now=now_lagos)]
            if not upcoming_legacy:
                return _reply("LIVE BOOKMAKER ODDS — NO UPCOMING FIXTURES WITH USABLE PREMATCH PRICES\\nAll supplied prices are stale or have invalid kickoff times.")
            legacy_lines = ["LIVE BOOKMAKER ODDS — UPCOMING FIXTURES | RAW PRICES, NOT VALUE PICKS"]
            for row in upcoming_legacy[:12]:
                prices = row.get("odds") or {}
                parts = [f"{key} {float(prices[key]):.2f}" for key in ("home", "draw", "away") if key in prices]
                legacy_lines.append(f"{row.get('home_team')} vs {row.get('away_team')} | {row.get('date')} {row.get('time')} | {row.get('bookmaker')}")
                legacy_lines.append(" | ".join(parts) if parts else "No supported prices in this row.")
            legacy_lines.append("Prices are reference data only; model probabilities are not validated for betting.")
            return _reply("\\n".join(legacy_lines))
        rows = _future_fixtures(report)
        if not rows:
            return _reply("MULTI-SOURCE BOOKMAKER ODDS — NO CURRENT UPCOMING FIXTURES IN THE PUBLISHED REPORT\\nRefresh the daily report first. This command reads saved report data and does not call external providers.")
        lines = ["BTTS + OVER/UNDER BOOKMAKER PRICES — REFERENCE DATA ONLY"]
        shown = 0
        for row in rows:
            sources = []
            five = row.get("five_dollar_market_odds")
            if isinstance(five, dict):
                for book in (five.get("bookmakers") or []):
                    if not isinstance(book, dict):
                        continue
                    btts, totals = book.get("btts") or {}, book.get("over_under") or {}
                    parts = []
                    if btts.get("yes") is not None and btts.get("no") is not None:
                        parts.append("BTTS Yes {:.2f} / No {:.2f}".format(float(btts["yes"]), float(btts["no"])))
                    if totals.get("over") is not None and totals.get("under") is not None:
                        parts.append("O/U {}: Over {:.2f} / Under {:.2f}".format(totals.get("line", 2.5), float(totals["over"]), float(totals["under"])))
                    if parts:
                        sources.append("5DollarFootballAPI · " + str(book.get("bookmaker") or "bookmaker") + " · " + " · ".join(parts))
            odds_api = row.get("the_odds_api_market_odds")
            if isinstance(odds_api, dict):
                markets = odds_api.get("markets") or {}
                for market_key, market_label in (("btts", "BTTS"), ("totals", "Over/Under")):
                    for market in (markets.get(market_key) or [])[:2]:
                        if not isinstance(market, dict):
                            continue
                        outcomes = market.get("outcomes") or []
                        parts = []
                        for outcome in outcomes:
                            if not isinstance(outcome, dict) or outcome.get("price") is None:
                                continue
                            label = "{} {:.2f}".format(outcome.get("name"), float(outcome["price"]))
                            if outcome.get("point") is not None:
                                label += " ({})".format(outcome["point"])
                            parts.append(label)
                        if parts:
                            sources.append("The Odds API · " + str(market.get("bookmaker") or "bookmaker") + " · " + market_label + ": " + " / ".join(parts))
            oddspapi = row.get("oddspapi_market_odds")
            if isinstance(oddspapi, dict):
                for market in (oddspapi.get("btts") or [])[:2]:
                    if isinstance(market, dict) and (market.get("yes") is not None or market.get("no") is not None):
                        sources.append("OddsPapi · {} · BTTS Yes {} / No {}".format(market.get("bookmaker", "bookmaker"), market.get("yes", "—"), market.get("no", "—")))
                for market in (oddspapi.get("over_under") or [])[:2]:
                    if isinstance(market, dict) and (market.get("over") is not None or market.get("under") is not None):
                        sources.append("OddsPapi · {} · O/U {}: Over {} / Under {}".format(market.get("bookmaker", "bookmaker"), market.get("line", "—"), market.get("over", "—"), market.get("under", "—")))
            if not sources:
                continue
            lines.append("")
            lines.append("{} vs {} · {}".format(row.get("home_team"), row.get("away_team"), row.get("kickoff_local") or row.get("kickoff")))
            lines.extend(sources[:5])
            shown += 1
            if shown >= 10:
                break
        if not shown:
            return _reply("MULTI-SOURCE BOOKMAKER ODDS — NO MATCHED BTTS OR OVER/UNDER PRICES\\nThe current report contains fixtures, but no provider prices matched safely by teams and local kickoff date. No odds were fabricated.")
        lines.extend([
            "",
            "Prices are provider-reported and may change. Forecast probabilities remain experimental; no value recommendations or bookmaker actions are generated.",
        ])
        return _reply("\\n".join(lines))

    if command == "/status":
        return _reply(_status(report, ledger))

    if command == "/slipcheck":
        return _reply(_slipcheck(argument))

    if command == "/builder":
        return _reply(
            "CONSERVATIVE BUILDER\n"
            "No automatic slip is generated. Use only independently checked selections and current bookmaker prices. "
            "A target total of 10.00 odds is not a probability or a profit guarantee.\n"
            "Use /10odds to check whether verified odds data are connected."
        )

    if command in {"/tomorrow", "/live"}:
        label = "TOMORROW" if command == "/tomorrow" else "LIVE MATCHES"
        return _reply(
            f"{label} — DATA NOT CONNECTED\n"
            "The saved report is a same-day pre-match snapshot. A separate date-specific or live-status source is required; no fixtures are guessed."
        )

    if command in {"/today", "/fixtures", "/match", "/goals", "/overunder", "/btts"}:
        all_rows = _future_fixtures(report)
        forecast_rows = _forecast_predictions(report)
        if not all_rows:
            if command == "/match" and not argument.strip():
                body = "Usage: /match Home Team vs Away Team"
            else:
                body = (
                    f"{command.upper()} — DATA NOT AVAILABLE\n"
                    "No current saved prediction report was supplied. I won't invent fixtures, scores, kickoff times, or probabilities."
                )
            return _reply(body)

        if command == "/match":
            query = argument.casefold().replace(" vs ", " ").strip()
            if not query:
                return _reply("Usage: /match Home Team vs Away Team")
            matches = [
                row for row in all_rows
                if query in f"{row.get('home_team', '')} {row.get('away_team', '')}".casefold()
            ]
            if not matches:
                return _reply("No matching fixture was found in the loaded report.")
            selected = matches[:5]
        elif command == "/fixtures":
            selected = _future_fixtures(report)[:15]
            if not selected:
                return _reply("FIXTURES — NO FUTURE SAME-DAY FIXTURES remain in the saved snapshot.")
        elif command in {"/overunder", "/btts"}:
            selected = [row for row in forecast_rows if _goal_market_probabilities(row) is not None][:15]
            if not selected:
                market = "OVER/UNDER" if command == "/overunder" else "BTTS"
                return _reply(
                    f"{market} — NO USABLE GOAL-MARKET ESTIMATES. "
                    "The current report has no eligible fixtures with valid expected-goal inputs."
                )
        elif command == "/goals":
            selected = [row for row in forecast_rows if _expected_goals(row) is not None][:15]
            if not selected:
                return _reply("GOALS — NO USABLE EXPECTED-GOALS FORECASTS in the saved report.")
        else:
            selected = forecast_rows[:15]
            if not selected:
                notice = _history_notice(report)
                body = "TODAY — NO USABLE FORECASTS. Fixtures may exist, but no rows passed the forecast-data checks."
                if notice:
                    body += "\n" + notice
                return _reply(body)

        titles = {
            "/overunder": "PRIMARY MARKET — OVER/UNDER GOALS (EXPERIMENTAL)",
            "/btts": "PRIMARY MARKET — BOTH TEAMS TO SCORE (EXPERIMENTAL)",
            "/fixtures": "FIXTURE LIST",
        }
        lines = [titles.get(command, f"{command.upper()} — EXPERIMENTAL REPORT")]
        notice = _history_notice(report)
        if notice:
            lines.extend([notice, ""])
        for row in selected:
            home = row.get("home_team", "Home")
            away = row.get("away_team", "Away")
            league = row.get("league", "Competition unknown")
            kickoff = row.get("kickoff_local") or row.get("kickoff") or "kickoff unavailable"
            if command == "/fixtures":
                lines.append(
                    f"{home} vs {away} | {league} | {kickoff} | "
                    f"{row.get('status', 'status unknown')}"
                )
                continue

            probs = row.get("probabilities")
            if row.get("status") != "EXPERIMENTAL_ONLY" or not _valid_probability_vector(probs):
                reason = row.get("reason") or row.get("status") or "forecast unavailable"
                lines.append(f"{home} vs {away} | {league} | {kickoff} | WITHHELD: {reason}")
                continue
            lines.append(
                f"{home} vs {away} | {league} | {kickoff} | "
                f"H {float(probs['home_win']):.0%} / D {float(probs['draw']):.0%} / A {float(probs['away_win']):.0%}"
            )
            means = _expected_goals(row)
            if means is not None and command == "/goals":
                lines.append(f"Expected goals: {means[0]:.2f} - {means[1]:.2f}")
            if means is not None and command == "/overunder":
                markets = _goal_market_probabilities(row) or {}
                lines.append(f"Model expected goals: {means[0]:.2f} + {means[1]:.2f} = {sum(means):.2f}")
                lines.append("Over probabilities: " + " | ".join(
                    f"O{line}.5 {markets[f'over_{line}_prob']:.0%}" for line in (0, 1, 2, 3, 4)
                ))
                prices = _saved_market_price_lines(row, "totals")
                lines.extend(["Bookmaker reference prices:", *prices] if prices else ["No matched bookmaker Over/Under prices in this report."])
            if means is not None and command == "/btts":
                markets = _goal_market_probabilities(row) or {}
                yes = markets["btts_yes_prob"]
                lines.append(f"BTTS Yes: {yes:.0%} | BTTS No: {1.0 - yes:.0%}")
                lines.append(f"Model expected goals: home {means[0]:.2f}, away {means[1]:.2f}")
                prices = _saved_market_price_lines(row, "btts")
                lines.extend(["Bookmaker reference prices:", *prices] if prices else ["No matched bookmaker BTTS prices in this report."])

        if command in {"/overunder", "/btts"}:
            lines.append(
                "Goal-market estimates use an independent-Poisson approximation from experimental expected goals. "
                "They are not calibrated or validated betting advice. Market prices are reference data only."
            )
        else:
            lines.append("Experimental estimates only — not validated betting advice.")
        return _reply("\n".join(lines))

    if command in {"/overunder", "/btts", "/cleansheet", "/value", "/overvalue", "/bttsvalue", "/10odds"}:
        return _reply(
            f"{command.upper()} — NOT ENABLED\n"
            "The connected report does not yet provide verified bookmaker prices plus validated probabilities for this market. "
            "No candidate will be published until both are available. No odds or selections have been fabricated."
        )

    if command in {"/results", "/performance"}:
        if not isinstance(ledger, dict):
            return _reply(
                f"{command.upper()} — PAPER LEDGER NOT AVAILABLE\n"
                "No current cumulative paper-tracking ledger was supplied. Historical performance will not be guessed."
            )
        metrics = ledger.get("cumulative_metrics_by_model") or {}
        if not metrics:
            return _reply("PAPER TRACKING: no completed forecast evaluations are available yet.")
        lines = [f"{command.upper()} — RETROSPECTIVE PAPER METRICS"]
        for name, values in sorted(metrics.items()):
            accuracy = values.get("result_accuracy")
            brier = values.get("brier_score")
            loss = values.get("log_loss")
            lines.append(f"{name}: {values.get('matches', 0)} scored")
            lines.append(f"Accuracy: {accuracy:.1%}" if isinstance(accuracy, (int, float)) else "Accuracy: unavailable")
            lines.append(f"Brier: {brier:.3f} | Log loss: {loss:.3f}" if isinstance(brier, (int, float)) and isinstance(loss, (int, float)) else "Brier/log loss: unavailable")
        lines.append("Retrospective metrics are not proof of profitability.")
        return _reply("\n".join(lines))

    return _reply("This command is listed but has no handler yet. Use /help for status and available functions.")
