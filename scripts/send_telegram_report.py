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
    lines = [
        "⚽ VELTRIX FOOTBALL — DAILY REPORT",
        f"Date: {day} ({timezone_name})",
        "MODEL STATUS: EXPERIMENTAL — NOT VALIDATED FOR BETTING",
        "These are probability estimates for research, not betting tips.",
        "",
    ]
    usable = [p for p in predictions if p.get("status") == "EXPERIMENTAL_ONLY"]
    insufficient = [p for p in predictions if p.get("status") == "INSUFFICIENT_HISTORY"]
    if not usable:
        lines.append("NO USABLE EXPERIMENTAL FORECASTS TODAY.")
        lines.append("No betting slips generated. No picks are being forced.")
    for item in usable:
        probs = item.get("probabilities", {})
        kickoff = str(item.get("kickoff_local", "Kickoff time unavailable"))
        lines.extend([
            f"{item.get('home_team', 'Home')} vs {item.get('away_team', 'Away')}",
            f"League: {item.get('league') or 'Unknown competition'}",
            f"Kickoff: {kickoff}",
            "1X2 estimate: "
            f"Home {float(probs.get('home', 0)):.0%} | "
            f"Draw {float(probs.get('draw', 0)):.0%} | "
            f"Away {float(probs.get('away', 0)):.0%}",
            f"Estimated goals: {item.get('expected_goals', {}).get('home', '—')} - "
            f"{item.get('expected_goals', {}).get('away', '—')}",
            "Status: experimental only; do not treat as a recommendation.",
            "",
        ])
    if insufficient:
        lines.append(f"{len(insufficient)} fixture(s) withheld because historical team data was insufficient.")
    lines.extend([
        "",
        "Normal 10.00-odds slips: DISABLED.",
        "Value slips (50.00–100.00 odds): DISABLED.",
        "Reason: current models have not beaten the historical market benchmark.",
    ])
    message = "\n".join(lines)
    if len(message) <= MAX_MESSAGE_LENGTH:
        return message
    # Keep each fixture block intact where possible; Telegram has a hard message cap.
    header = "\n".join(lines[:5])
    footer = "\n\nFurther fixtures omitted to fit Telegram's message limit."
    return message[: MAX_MESSAGE_LENGTH - len(footer)] + footer


def send_message(token: str, chat_id: str, message: str, *, timeout: int = 15) -> None:
    if not token.strip() or not chat_id.strip():
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are both required.")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=timeout,
    )
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
