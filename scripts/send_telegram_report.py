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


def format_report_messages(report: dict[str, Any], ledger: dict[str, Any] | None = None) -> list[str]:
    day = str(report.get("as_of_date", "unknown date"))
    timezone_name = str(report.get("timezone", "Africa/Lagos"))
    predictions = report.get("predictions", [])
    usable = [p for p in predictions if p.get("status") == "EXPERIMENTAL_ONLY"]
    insufficient = [p for p in predictions if p.get("status") == "INSUFFICIENT_HISTORY"]
    unsupported = [p for p in predictions if p.get("status") == "UNSUPPORTED_COMPETITION"]

    header = [
        "╔══════════════════════════╗",
        "🔔 🆕 NEW VELTRIX MESSAGE",
        "╚══════════════════════════╝",
        "⚽ VELTRIX FOOTBALL",
        "TODAY'S MATCH FORECASTS",
        f"📅 {day} | Kick-off times: Nigeria (WAT)",
        DIVIDER,
        "⚠️ Experimental estimates only — not validated betting advice.",
        "",
        f"FORECASTS: {len(usable)}",
        f"NOT SHOWN: {len(insufficient)} need more team history | {len(unsupported)} unsupported competitions",
        "",
    ]
    sync = report.get("recent_results_sync") or {}
    if sync and (sync.get("status") not in {"OK", "SUCCESS", "COMPLETE", "UP_TO_DATE"} or sync.get("warning")):
        sync_status = str(sync.get("status") or "UNKNOWN").upper()
        sync_warning = str(sync.get("warning") or "").lower()
        if "limited to" in sync_warning:
            sync_reason = "Historical refresh was intentionally bounded to protect the daily provider request quota."
        elif "http 429" in sync_warning or "quota" in sync_warning or "rate limit" in sync_warning:
            sync_reason = "Provider request quota/rate limit reached; no further historical results were fetched."
        elif "http 401" in sync_warning or "http 403" in sync_warning or "authentication" in sync_warning or "token" in sync_warning:
            sync_reason = "Provider authentication was rejected; historical results were not refreshed."
        elif sync_status == "PARTIAL":
            sync_reason = "Only part of the requested historical date range was refreshed."
        elif sync_status == "NO_BASE_HISTORY":
            sync_reason = "No base historical dataset was available to refresh."
        else:
            sync_reason = "The historical-results provider request failed; available saved history was retained."
        header.extend([
            f"DATA NOTICE: Recent-results refresh status: {sync_status}.",
            sync_reason,
            "Forecasts use available saved history; missing results are not invented.",
        ])
        coverage = report.get("historical_data_coverage") or {}
        if coverage.get("status") == "GAPPED_OR_STALE":
            contiguous_through = coverage.get("contiguous_through") or "unknown"
            latest_available = coverage.get("latest_available_match_date") or "unknown"
            succeeded = coverage.get("ranges_succeeded")
            requested = coverage.get("ranges_requested")
            if isinstance(succeeded, int) and isinstance(requested, int) and requested > 0:
                header.append(f"Historical coverage: {succeeded}/{requested} date ranges refreshed.")
            header.append(
                f"History is only confirmed continuous through {contiguous_through}; "
                f"latest available result date is {latest_available}."
            )
        header.append("")

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
        model_name = str(item.get("model", "experimental_unknown"))
        is_elo_primary = "elo" in model_name
        expected_goals = item.get("expected_goals") or {}
        model_label = "Elo ratings (1X2); Poisson xG" if is_elo_primary else "Recent-goals Poisson (1X2 + xG)"
        block = [
            DIVIDER,
            f"⚽ {item.get('home_team', 'Home')} vs {item.get('away_team', 'Away')}",
            f"🏆 {item.get('league') or 'Unknown competition'}",
            f"🕒 Kickoff: {kickoff}",
            "",
            "WIN / DRAW / WIN PROBABILITY",
            f"Home win: {float(home_probability):.0%}",
            f"Draw: {float(draw_probability):.0%}",
            f"Away win: {float(away_probability):.0%}",
            "",
            f"Expected goals: {_format_goals(expected_goals.get('home'))} - {_format_goals(expected_goals.get('away'))}",
            f"Model: {model_label}",
            "Status: experimental estimate only",
            "",
        ]
        blocks.append(block)

    footer = [DIVIDER, "QUICK NOTES"]
    if insufficient:
        footer.append(f"• {len(insufficient)} match(es) withheld: not enough reliable team history.")
    if unsupported:
        footer.append(f"• {len(unsupported)} match(es) withheld: league history is not supported.")
    footer.extend([
        "• No betting slips or forced picks are generated.",
        "• Probabilities are model estimates, not guarantees.",
        "• When Elo is primary, expected goals are a separate Poisson estimate and do not directly generate the displayed 1X2 probabilities.",
        "• Fixture data provided by Highlightly Football API.",
    ])

    def render(selected: list[list[str]]) -> str:
        lines = list(header)
        for block in selected:
            lines.extend(block)
        lines.extend(footer)
        return "\n".join(lines)

    # Keep every fixture. Split between complete fixture blocks instead of
    # silently dropping later matches when the Telegram message limit is reached.
    chunks: list[str] = []
    selected: list[list[str]] = []
    for block in blocks:
        single_block_message = render([block])
        if len(single_block_message) > MAX_MESSAGE_LENGTH:
            if selected:
                chunks.append(render(selected))
                selected = []
            # Defensive fallback for an unusually long single fixture block.
            chunks.append(single_block_message[: MAX_MESSAGE_LENGTH - 1].rstrip() + "…")
            continue
        candidate = render(selected + [block])
        if len(candidate) <= MAX_MESSAGE_LENGTH:
            selected.append(block)
            continue
        if selected:
            chunks.append(render(selected))
            selected = [block]
    if selected or not chunks:
        message = render(selected)
        if len(message) > MAX_MESSAGE_LENGTH:
            message = message[: MAX_MESSAGE_LENGTH - 1].rstrip() + "…"
        chunks.append(message)
    # Add a strong visual marker to every Telegram message, including split parts,
    # so fresh Veltrix updates are easy to distinguish in a busy chat.
    total = len(chunks)
    return [
        f"🔔 🆕 NEW VELTRIX UPDATE  •  MESSAGE {index}/{total}\n╔══════════════════════════╗\n" + chunk
        for index, chunk in enumerate(chunks, start=1)
    ]


def format_report(report: dict[str, Any], ledger: dict[str, Any] | None = None) -> str:
    """Compatibility helper returning the first Telegram-sized report chunk."""
    return format_report_messages(report, ledger)[0]


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
        messages = format_report_messages(report, ledger)
        for index, message in enumerate(messages, start=1):
            send_message(token, chat_id, message)
            print(f"Telegram report part {index}/{len(messages)} delivered.")
        print(f"Telegram report delivered for {report.get('as_of_date', 'unknown date')}.")
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError, requests.RequestException) as exc:
        print(f"TELEGRAM REPORT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
