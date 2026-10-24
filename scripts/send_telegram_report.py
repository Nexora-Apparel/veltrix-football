"""Send a clearly labelled experimental daily report to Telegram."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os
import sys
from pathlib import Path
from typing import Any

import requests

MAX_MESSAGE_LENGTH = 3900
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def _format_goals(value: Any) -> str:
    """Render numeric expected-goal estimates consistently without hiding missing data."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}"
    return str(value) if value is not None else "—"


def _format_kickoff(value: Any, timezone_name: str) -> str:
    """Show a readable local kickoff time rather than a raw ISO timestamp."""
    if not value:
        return "Time unavailable"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    try:
        target_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        target_timezone = None
    if target_timezone is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=target_timezone)
        else:
            parsed = parsed.astimezone(target_timezone)
    abbreviation = "WAT" if timezone_name == "Africa/Lagos" else parsed.tzname()
    return f"{parsed:%H:%M} {abbreviation}" if abbreviation else f"{parsed:%H:%M}"


def format_report(report: dict[str, Any], ledger: dict[str, Any] | None = None) -> str:
    day = str(report.get("as_of_date", "unknown date"))
    timezone_name = str(report.get("timezone", "Africa/Lagos"))
    predictions = report.get("predictions", [])
    usable = [p for p in predictions if p.get("status") == "EXPERIMENTAL_ONLY"]
    insufficient = [p for p in predictions if p.get("status") == "INSUFFICIENT_HISTORY"]

    header = [
        "⚽ VELTRIX FOOTBALL",
        "DAILY MATCH ANALYTICS",
        f"📅 {day}  |  Timezone: {timezone_name}",
        DIVIDER,
        "⚠️ EXPERIMENTAL MODEL — NOT VALIDATED FOR BETTING",
        "Probabilities are research estimates, not betting tips.",
        "",
        f"MATCH FORECASTS: {len(usable)}",
        "",
    ]
    if "fixtures_received" in report:
        header.extend([
            "FIXTURE FILTER",
            f"API fixtures received: {report.get('fixtures_received', 0)}",
            (
                f"Today/future fixtures considered: {report.get('future_fixtures_considered', 0)}"
                f"  |  Past kickoffs excluded: {report.get('past_kickoffs_excluded', 0)}"
            ),
            f"Other dates/status excluded: {report.get('fixtures_excluded_other_date_or_status', 0)}",
            "",
        ])
    if ledger is not None:
        paper_lines = [DIVIDER, "PAPER TRACKING — CUMULATIVE"]
        attempt = ledger.get("last_attempt") or {}
        paper_lines.append(f"Latest evaluation status: {attempt.get('status', 'UNKNOWN')}")
        model_metrics = ledger.get("cumulative_metrics_by_model") or {}
        if model_metrics:
            for model_name, metrics in sorted(model_metrics.items()):
                accuracy = metrics.get("result_accuracy")
                brier = metrics.get("brier_score")
                log_loss = metrics.get("log_loss")
                paper_lines.append(
                    f"{model_name}: {metrics.get('matches', 0)} scored | "
                    f"accuracy {accuracy:.1%}" if isinstance(accuracy, (int, float))
                    else f"{model_name}: {metrics.get('matches', 0)} scored | accuracy unavailable"
                )
                if isinstance(brier, (int, float)) and isinstance(log_loss, (int, float)):
                    paper_lines.append(f"  Brier {brier:.3f} | log loss {log_loss:.3f}")
        else:
            paper_lines.append("No completed forecasts scored yet.")
        paper_lines.append("Paper metrics are retrospective, not proof of profitability.")
        header.extend(paper_lines + [""])

    if not usable:
        header.extend([
            "NO USABLE EXPERIMENTAL FORECASTS TODAY.",
            "No betting slips generated. No picks are being forced.",
            "",
        ])

    # Keep each fixture as a block so a long report never ends mid-fixture.
    blocks: list[list[str]] = []
    for item in usable:
        probs = item.get("probabilities", {})
        # The model emits home_win/draw/away_win; accept home/draw/away too
        # for older reports and simple test fixtures.
        home_probability = probs.get("home_win", probs.get("home", 0))
        draw_probability = probs.get("draw", 0)
        away_probability = probs.get("away_win", probs.get("away", 0))
        kickoff = _format_kickoff(item.get("kickoff_local"), timezone_name)
        expected_goals = item.get("expected_goals", {})
        block = [
            DIVIDER,
            f"⚽ {item.get('home_team', 'Home')} vs {item.get('away_team', 'Away')}",
            f"🏆 {item.get('league') or 'Unknown competition'}",
            f"🕒 Kickoff: {kickoff}",
            "",
            "1X2 PROBABILITY ESTIMATE",
            f"Home  {float(home_probability):.0%}",
            f"Draw  {float(draw_probability):.0%}",
            f"Away  {float(away_probability):.0%}",
        ]
        elo_probs = item.get("elo_probabilities")
        if isinstance(elo_probs, dict):
            block.extend([
                "",
                "ELO ALTERNATIVE (EXPERIMENTAL)",
                f"Home  {float(elo_probs.get('home_win', 0)):.0%}",
                f"Draw  {float(elo_probs.get('draw', 0)):.0%}",
                f"Away  {float(elo_probs.get('away_win', 0)):.0%}",
            ])
        block.extend([
            "",
            f"Expected goals: {_format_goals(expected_goals.get('home'))} - "
            f"{_format_goals(expected_goals.get('away'))}",
            "Status: experimental estimate only",
            "",
        ])
        blocks.append(block)

    footer = [
        DIVIDER,
        "MODEL & DATA NOTES",
    ]
    if insufficient:
        footer.append(
            f"• {len(insufficient)} fixture(s) withheld: insufficient historical team data."
        )
    suggested = sum(bool(p.get("team_name_match_suggestions")) for p in insufficient)
    if suggested:
        footer.append(
            f"• {suggested} withheld fixture(s) have possible team-name variants to review; "
            "these are suggestions only and are never auto-matched."
        )
    footer.extend([
        "• Standard 10.00-odds slips: DISABLED.",
        "• Value slips (50.00–100.00 odds): DISABLED.",
        "• Reason: models have not beaten the historical market benchmark.",
        "",
        "Please do not use these experimental estimates as betting advice.",
    ])

    def render(selected: list[list[str]], omitted: int = 0) -> str:
        lines = list(header)
        for block in selected:
            lines.extend(block)
        if omitted:
            lines.extend([
                "",
                f"{omitted} additional fixture(s) omitted to fit Telegram's message limit.",
            ])
        lines.extend(footer)
        return "\n".join(lines)

    full_message = render(blocks)
    if len(full_message) <= MAX_MESSAGE_LENGTH:
        return full_message

    selected: list[list[str]] = []
    for block in blocks:
        remaining_after_add = len(blocks) - len(selected) - 1
        candidate = render(selected + [block], remaining_after_add)
        if len(candidate) > MAX_MESSAGE_LENGTH:
            break
        selected.append(block)

    omitted = len(blocks) - len(selected)
    message = render(selected, omitted)
    # Defensive fallback for unusually long external team/league names.
    if len(message) > MAX_MESSAGE_LENGTH:
        return message[: MAX_MESSAGE_LENGTH - 1].rstrip() + "…"
    return message


def send_message(token: str, chat_id: str, message: str, *, timeout: int = 15) -> None:
    if not token.strip() or not chat_id.strip():
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are both required.")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        # Never print the exception itself: request errors may contain the token-bearing URL.
        raise RuntimeError(
            f"Telegram network request failed ({exc.__class__.__name__})."
        ) from None
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Telegram returned non-JSON HTTP {response.status_code}.") from exc
    if response.status_code >= 400 or not payload.get("ok"):
        # Do not echo the token-bearing URL or response request details.
        description = payload.get("description", "Telegram rejected the message.")
        raise RuntimeError(f"Telegram delivery failed (HTTP {response.status_code}): {description}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="reports/daily_predictions.json")
    parser.add_argument("--ledger", default="reports/paper_tracking_ledger.json")
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        if not isinstance(report, dict) or not report.get("same_day_only"):
            raise ValueError("Report is invalid or does not enforce same-day fixture filtering.")
        ledger = None
        ledger_path = Path(args.ledger)
        if ledger_path.exists():
            try:
                loaded_ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
                if isinstance(loaded_ledger, dict):
                    ledger = loaded_ledger
            except (OSError, json.JSONDecodeError):
                ledger = None
        message = format_report(report, ledger)
        send_message(token, chat_id, message)
        print(f"Telegram report delivered for {report.get('as_of_date', 'unknown date')}.")
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError, requests.RequestException) as exc:
        print(f"TELEGRAM REPORT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
