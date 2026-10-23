"""Send a clearly labelled experimental daily report to Telegram."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

MAX_MESSAGE_LENGTH = 3900


def format_report(report: dict[str, Any]) -> str:
    day = str(report.get("as_of_date", "unknown date"))
    timezone_name = str(report.get("timezone", "Africa/Lagos"))
    predictions = report.get("predictions", [])
    header = [
        "⚽ VELTRIX FOOTBALL — DAILY REPORT",
        f"Date: {day} ({timezone_name})",
        "MODEL STATUS: EXPERIMENTAL — NOT VALIDATED FOR BETTING",
        "These are probability estimates for research, not betting tips.",
        "",
    ]
    usable = [p for p in predictions if p.get("status") == "EXPERIMENTAL_ONLY"]
    insufficient = [p for p in predictions if p.get("status") == "INSUFFICIENT_HISTORY"]
    if not usable:
        header.extend([
            "NO USABLE EXPERIMENTAL FORECASTS TODAY.",
            "No betting slips generated. No picks are being forced.",
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
        kickoff = str(item.get("kickoff_local", "Kickoff time unavailable"))
        blocks.append([
            f"{item.get('home_team', 'Home')} vs {item.get('away_team', 'Away')}",
            f"League: {item.get('league') or 'Unknown competition'}",
            f"Kickoff: {kickoff}",
            "1X2 estimate: "
            f"Home {float(home_probability):.0%} | "
            f"Draw {float(draw_probability):.0%} | "
            f"Away {float(away_probability):.0%}",
            f"Estimated goals: {item.get('expected_goals', {}).get('home', '—')} - "
            f"{item.get('expected_goals', {}).get('away', '—')}",
            "Status: experimental only; do not treat as a recommendation.",
            "",
        ])

    footer = []
    if insufficient:
        footer.append(
            f"{len(insufficient)} fixture(s) withheld because historical team data was insufficient."
        )
    footer.extend([
        "",
        "Normal 10.00-odds slips: DISABLED.",
        "Value slips (50.00–100.00 odds): DISABLED.",
        "Reason: current models have not beaten the historical market benchmark.",
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
    # The header/footer and omission note are small; this is a defensive fallback
    # for unusually long external team/league names.
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
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    try:
        report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        if not isinstance(report, dict) or not report.get("same_day_only"):
            raise ValueError("Report is invalid or does not enforce same-day fixture filtering.")
        message = format_report(report)
        send_message(token, chat_id, message)
        print(f"Telegram report delivered for {report.get('as_of_date', 'unknown date')}.")
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError, requests.RequestException) as exc:
        print(f"TELEGRAM REPORT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
