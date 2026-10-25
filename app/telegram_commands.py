"""Safe Telegram Command Centre router for Veltrix Football.

Formats command replies and reads only explicitly supplied report data. It never
invents odds or treats experimental estimates as validated bets.
"""
from __future__ import annotations

import re
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
    rows = report.get("predictions", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _status(report: dict[str, Any] | None, ledger: dict[str, Any] | None) -> str:
    predictions = _report_predictions(report)
    odds_status = "not connected to this command router"
    if isinstance(report, dict):
        meta = report.get("odds_meta") or report.get("odds") or {}
        if isinstance(meta, dict) and meta.get("status"):
            odds_status = str(meta["status"])
    ledger_status = "available" if isinstance(ledger, dict) else "not available"
    return (
        "VELTRIX COMMAND CENTRE — STATUS\n"
        f"Current report: {'available' if isinstance(report, dict) else 'not loaded'}\n"
        f"Forecast rows in report: {len(predictions)}\n"
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

    if command in {"/today", "/fixtures", "/tomorrow", "/live", "/match", "/goals"}:
        predictions = _report_predictions(report)
        if not predictions:
            if command == "/match" and not argument.strip():
                body = "Usage: /match Home Team vs Away Team"
            else:
                body = (
                    f"{command.upper()} — DATA NOT AVAILABLE\n"
                    "No current prediction report was supplied to the command router. "
                    "I won't invent fixtures, scores, kickoff times, or probabilities."
                )
            return _reply(body)
        if command == "/match":
            query = argument.casefold().replace(" vs ", " ").strip()
            if not query:
                return _reply("Usage: /match Home Team vs Away Team")
            matches = [
                row for row in predictions
                if query in f"{row.get('home_team', '')} {row.get('away_team', '')}".casefold()
            ]
            if not matches:
                return _reply("No matching fixture was found in the loaded report.")
            selected = matches[:5]
        else:
            selected = predictions
        lines = [f"{command.upper()} — EXPERIMENTAL REPORT"]
        for row in selected[:15]:
            probs = row.get("probabilities") or {}
            lines.append(
                f"{row.get('home_team', 'Home')} vs {row.get('away_team', 'Away')} | "
                f"{row.get('league', 'Competition unknown')} | "
                f"H {float(probs.get('home_win', probs.get('home', 0))):.0%} / "
                f"D {float(probs.get('draw', 0)):.0%} / "
                f"A {float(probs.get('away_win', probs.get('away', 0))):.0%}"
            )
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
