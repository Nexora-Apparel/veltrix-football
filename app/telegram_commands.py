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
    "/overunder": "Over/Under analysis; requires supported goal-market probabilities.",
    "/btts": "Both Teams To Score analysis; requires supported goal-market probabilities.",
    "/goals": "Expected-goals summary for available forecasts.",
    "/cleansheet": "Clean-sheet estimates; unavailable until calibrated team-goal probabilities exist.",
    "/value": "Value screen status; candidates stay disabled until the model passes validation.",
    "/overvalue": "Over/Under value screen status; requires model probabilities and real odds.",
    "/bttsvalue": "BTTS value screen status; requires model probabilities and real odds.",
    "/odds": "Show odds only when a live odds provider returns real prices.",
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


def _history_notice(report: dict[str, Any] | None) -> str | None:
    if not isinstance(report, dict):
        return None
    sync = report.get("recent_results_sync") or {}
    coverage = report.get("historical_data_coverage") or {}
    if not isinstance(sync, dict) or not isinstance(coverage, dict):
        return None
    if coverage.get("status") == "GAPPED_OR_STALE":
        contiguous = coverage.get("contiguous_through") or "unknown"
        latest = coverage.get("latest_available_match_date") or "unknown"
        succeeded, requested = sync.get("ranges_succeeded"), sync.get("ranges_requested")
        progress = (
            f" {succeeded}/{requested} date ranges refreshed."
            if isinstance(succeeded, int) and isinstance(requested, int) and requested > 0
            else ""
        )
        return (
            "DATA NOTICE: Historical results are incomplete; forecasts may miss matches from the gap. "
            f"History is continuous through {contiguous}; latest available result date is {latest}."
            f"{progress}"
        )
    status = str(sync.get("status") or "").upper()
    if status and status not in {"COMPLETE", "UP_TO_DATE", "SUCCESS", "OK"}:
        return f"DATA NOTICE: Recent-results refresh status is {status}; saved history may be incomplete."
    return None


def _status(report: dict[str, Any] | None, ledger: dict[str, Any] | None) -> str:
    fixtures = _future_fixtures(report)
    predictions = _forecast_predictions(report)
    odds_status = "not connected to this command router"
    if isinstance(report, dict):
        meta = report.get("live_odds_sync") or report.get("odds_meta") or report.get("odds") or {}
        if isinstance(meta, dict) and meta.get("status"):
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
    return (
        "VELTRIX COMMAND CENTRE — STATUS\n"
        f"Current report: {'available' if report_is_current else 'not loaded or no longer current'}\n"
        f"Fixtures in report: {len(fixtures)}\n"
        f"Usable experimental forecasts: {len(predictions)}\n"
        f"Recent-results refresh: {history_status}\n"
        f"Historical coverage: {history_coverage}\n"
        f"Live bookmaker odds: {odds_status}\n"
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

    if command in {"/today", "/fixtures", "/match", "/goals"}:
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
        elif command == "/goals":
            selected = [row for row in forecast_rows if isinstance(row.get("expected_goals"), dict)][:15]
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

        lines = [f"{command.upper()} — {'FIXTURE LIST' if command == '/fixtures' else 'EXPERIMENTAL REPORT'}"]
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
            if isinstance(row.get("expected_goals"), dict) and command == "/goals":
                eg = row["expected_goals"]
                lines.append(f"Expected goals: {eg.get('home', 'n/a')} - {eg.get('away', 'n/a')}")

        lines.append("Experimental estimates only — not validated betting advice.")
        return _reply("\n".join(lines))

    if command in {"/overunder", "/btts", "/cleansheet", "/value", "/overvalue", "/bttsvalue", "/odds", "/10odds"}:
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
