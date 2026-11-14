# Same-day attribution replay is intentionally driven by the [reuse-report-40175707059] workflow marker.
"""Send the daily VELTRIX football verdict report to Telegram."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import requests

from veltrix_v2.reporting.report_identity import REPORT_SCHEMA


MAX_MESSAGE_LENGTH = 3900
MESSAGE_PREFIX = "🔔 🆕 NEW VELTRIX UPDATE  •  MESSAGE 999/999"
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"
DELIVERY_STATE_PATH = "public-data/telegram_delivery_state.json"
DELIVERY_STATE_BRANCH = "command-data"


def _github_json(url: str, token: str, method: str = "GET", body: dict | None = None) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Veltrix-Telegram-Delivery-Guard",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub returned an unexpected delivery-state response.")
    return payload


def _load_delivery_state(repo: str, token: str) -> tuple[dict[str, Any], str | None]:
    """Read the persistent sent-date guard from the command-data branch."""
    path = quote(DELIVERY_STATE_PATH, safe="/")
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={quote(DELIVERY_STATE_BRANCH, safe='')}"
    try:
        payload = _github_json(url, token)
    except HTTPError as exc:
        if exc.code == 404:
            return {"version": 1, "sent_dates": []}, None
        raise RuntimeError(f"Could not read Telegram delivery guard (HTTP {exc.code}).") from None
    except (URLError, OSError):
        raise RuntimeError("Could not read Telegram delivery guard due to a GitHub network error.") from None
    try:
        encoded = payload.get("content")
        state = json.loads(base64.b64decode(encoded).decode("utf-8"))
        dates = state.get("sent_dates")
        if state.get("version") not in {1, 2} or not isinstance(dates, list):
            raise ValueError("unsupported delivery state")
        sent_dates = sorted({str(value) for value in dates if isinstance(value, str) and len(value) == 10})
        raw_hashes = state.get("sent_report_hashes_by_date", {})
        if not isinstance(raw_hashes, dict):
            raise ValueError("invalid sent report hashes")
        hashes: dict[str, list[str]] = {}
        for report_day, values in raw_hashes.items():
            if not isinstance(report_day, str) or len(report_day) != 10 or not isinstance(values, list):
                raise ValueError("invalid sent report hash entry")
            valid = [value.lower() for value in values if isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)]
            hashes[report_day] = valid[-10:]
        return {"version": 2, "sent_dates": sent_dates[-30:], "sent_report_hashes_by_date": hashes}, str(payload["sha"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise RuntimeError("Published Telegram delivery guard is malformed; refusing a potentially duplicate send.") from None


def _report_fingerprint(messages: list[str]) -> str:
    """Stable hash of the exact Telegram report content, independent of run timestamps."""
    canonical = "\n\n".join(messages).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _should_skip_delivery(state: dict[str, Any], report_date: str, report_hash: str, force: bool = False) -> bool:
    hashes = state.get("sent_report_hashes_by_date") or {}
    known = hashes.get(report_date, []) if isinstance(hashes, dict) else []
    return not force and report_hash in known


def _mark_same_day_update(messages: list[str]) -> list[str]:
    if not messages:
        return messages
    first, separator, rest = messages[0].partition("\n")
    banner = "🔄 UPDATED SAME-DAY REPORT — refreshed fixture inventory"
    messages = list(messages)
    messages[0] = first + "\n" + banner + (separator + rest if separator else "")
    return messages


def _record_delivery_date(
    repo: str, token: str, sent_date: str, report_hash: str,
    state: dict[str, Any], sha: str | None,
) -> None:
    """Persist both the sent date and exact content hash to prevent stale same-day suppression."""
    dates = sorted(set(state.get("sent_dates", [])) | {sent_date})[-30:]
    hashes = dict(state.get("sent_report_hashes_by_date") or {})
    current = list(hashes.get(sent_date, []))
    if report_hash not in current:
        current.append(report_hash)
    hashes[sent_date] = current[-10:]
    retained_dates = set(dates)
    hashes = {day: values for day, values in hashes.items() if day in retained_dates}
    data = json.dumps({
        "version": 2,
        "sent_dates": dates,
        "sent_report_hashes_by_date": hashes,
    }, indent=2).encode("utf-8")
    path = quote(DELIVERY_STATE_PATH, safe="/")
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    body = {
        "message": f"Record Veltrix Telegram delivery for {sent_date}",
        "content": base64.b64encode(data).decode("ascii"),
        "branch": DELIVERY_STATE_BRANCH,
    }
    if sha:
        body["sha"] = sha
    try:
        _github_json(url, token, method="PUT", body=body)
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
        # The report has already been sent. Fail visibly so a human knows that
        # the persistent idempotency marker did not stick; never claim it did.
        raise RuntimeError("Telegram report was sent, but its duplicate-prevention marker could not be saved.") from None


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


def _reference_market_lines(item: dict[str, Any]) -> list[str]:
    """Render real matched odds as reference data; never label them value."""
    odds = item.get("the_odds_api_market_odds")
    markets = odds.get("markets") if isinstance(odds, dict) else {}
    if not isinstance(markets, dict):
        return []
    lines: list[str] = []
    for key, label in (("h2h", "1X2"), ("btts", "BTTS"), ("totals", "O/U 2.5")):
        entries = markets.get(key) or []
        if not isinstance(entries, list):
            continue
        market = next((entry for entry in entries if isinstance(entry, dict)), None)
        if not market:
            continue
        outcomes = market.get("outcomes") or []
        rendered = []
        for outcome in outcomes:
            if not isinstance(outcome, dict):
                continue
            price = outcome.get("price")
            name = outcome.get("name")
            if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 1 and name:
                point = outcome.get("point")
                suffix = f" {point:g}" if isinstance(point, (int, float)) and key == "totals" else ""
                rendered.append(f"{name}{suffix} {price:.2f}")
        if rendered:
            bookmaker = str(market.get("bookmaker") or "matched bookmaker")
            lines.append(f"{label} · {bookmaker}: " + " / ".join(rendered[:3]))
    return lines


def _format_recent_form(team_form: Any) -> str:
    if not isinstance(team_form, dict):
        return "N/A"
    last_five = team_form.get("last_5")
    if not isinstance(last_five, dict) or not last_five.get("matches"):
        return "N/A"
    form = str(last_five.get("form") or "—")
    points = last_five.get("points_per_game")
    if isinstance(points, (int, float)) and not isinstance(points, bool):
        return f"{form} ({points:.2f} PPG)"
    return form


def format_report_messages(report: dict[str, Any], ledger: dict[str, Any] | None = None) -> list[str]:
    """Format legacy report payloads; V2 reports use the separately gated formatter."""
    if report.get("schema") == REPORT_SCHEMA:
        raise ValueError("V2 report rejected by legacy Telegram formatter; use the V2 publication gate.")
    day = str(report.get("as_of_date", "unknown date"))
    timezone_name = str(report.get("timezone", "Africa/Lagos"))
    predictions = report.get("predictions", [])
    fixtures = [item for item in predictions if isinstance(item, dict)]
    usable = [item for item in fixtures if item.get("status") in {"EXPERIMENTAL_ONLY", "LOW_HISTORY_FORECAST"} and isinstance(item.get("probabilities"), dict)]

    header = [
        DIVIDER,
        f"⚽ VELTRIX FOOTBALL AI · DAILY INTELLIGENCE",
        f"📅 {day} · Kick-off times: WAT",
        "Football data by 5DollarFootballAPI · https://5dollarfootballapi.com",
        "",
    ]
    blocks: list[list[str]] = []
    for item in usable:
        probs = item.get("probabilities") if isinstance(item.get("probabilities"), dict) else {}
        home = probs.get("home_win", probs.get("home"))
        draw = probs.get("draw")
        away = probs.get("away_win", probs.get("away"))
        expected = item.get("expected_goals") if isinstance(item.get("expected_goals"), dict) else {}
        btts = item.get("btts_yes")
        over25 = item.get("over_2_5")
        if btts is None and isinstance(expected.get("home"), (int, float)) and isinstance(expected.get("away"), (int, float)):
            # Preserve only supplied model probabilities; do not fabricate a market estimate here.
            btts = None

        block = [
            DIVIDER,
            f"⚽ {item.get('home_team', 'Home')} vs {item.get('away_team', 'Away')}",
            f"🏆 {item.get('league') or 'Competition unavailable'} · 🕒 {_format_kickoff(item.get('kickoff_local') or item.get('kickoff'), timezone_name)}",
            f"1X2: Home {_format_percent(home)} | Draw {_format_percent(draw)} | Away {_format_percent(away)}",
            f"BTTS Yes: {_format_percent(btts)}",
            f"Over 1.5: {_format_percent(item.get('over_1_5'))} | Under 1.5: {_format_percent(1 - float(item.get('over_1_5'))) if isinstance(item.get('over_1_5'), (int, float)) and 0 <= item.get('over_1_5') <= 1 else '—'}",
            f"Over 2.5: {_format_percent(over25)} | Under 2.5: {_format_percent(1 - float(over25)) if isinstance(over25, (int, float)) and 0 <= over25 <= 1 else '—'}",
            f"Over 3.5: {_format_percent(item.get('over_3_5'))} | Under 3.5: {_format_percent(1 - float(item.get('over_3_5'))) if isinstance(item.get('over_3_5'), (int, float)) and 0 <= item.get('over_3_5') <= 1 else '—'}",
            f"xG: {_format_goals(expected.get('home'))} - {_format_goals(expected.get('away'))}",
        ]
        one_x_two = {"Home": home, "Draw": draw, "Away": away}
        ranked = [(label, value) for label, value in one_x_two.items() if isinstance(value, (int, float))]
        if ranked:
            verdict, probability = max(ranked, key=lambda pair: pair[1])
            block.append(f"1X2 VERDICT: {verdict} lean ({_format_percent(probability)})")
        if isinstance(btts, (int, float)):
            block.append("BTTS VERDICT: {} ({})".format("Yes" if btts >= 0.5 else "No", _format_percent(btts if btts >= 0.5 else 1-btts)))
        if isinstance(over25, (int, float)):
            block.append("GOALS VERDICT: {} 2.5 ({})".format("Over" if over25 >= 0.5 else "Under", _format_percent(over25 if over25 >= 0.5 else 1-over25)))
        recent_form = item.get("recent_form") if isinstance(item.get("recent_form"), dict) else {}
        home_form = _format_recent_form((recent_form.get("home_team") or {}).get("overall") if isinstance(recent_form.get("home_team"), dict) else None)
        away_form = _format_recent_form((recent_form.get("away_team") or {}).get("overall") if isinstance(recent_form.get("away_team"), dict) else None)
        if home_form != "N/A" or away_form != "N/A":
            block.append(f"Recent form · last 5: Home {home_form} | Away {away_form}")
        prediction_basis = str(item.get("prediction_basis") or "").strip()
        if prediction_basis:
            block.append("WHY THIS VERDICT: " + prediction_basis)
        value_screen = item.get("value_bet_screen") if isinstance(item.get("value_bet_screen"), dict) else {}
        certificate = report.get("value_validation_certificate")
        certificate = certificate if isinstance(certificate, dict) else {}
        certificate_status = str(certificate.get("status") or "").upper()
        approved_markets = certificate.get("approved_markets") or []
        if not isinstance(approved_markets, list):
            approved_markets = []
        # Report-supplied certificate labels are untrusted. Telegram must not
        # release value alerts until the source-attested verifier is wired in.
        certificate_releases = False
        for market, result in (value_screen.get("markets") or {}).items():
            raw_candidates = (result.get("candidates") or [])[:2]
            market_approved = certificate_releases and market in approved_markets
            released = raw_candidates if market_approved else []
            shadow = ((result.get("paper_candidates") or []) + ([] if market_approved else raw_candidates))[:2]
            for candidate in released:
                block.append(
                    "VALUE BET VERDICT: {} {} @ {:.2f} · estimated edge {:.1f}pp · expected return {:.1f}% · approved".format(
                        market, candidate.get("selection"), float(candidate.get("decimal_odds")),
                        float(candidate.get("edge_percentage_points")),
                        float(candidate.get("expected_return_per_unit")) * 100.0,
                    )
                )
            for candidate in shadow:
                block.append(
                    "VALUE BET VERDICT: Potential edge under review · {} {} @ {:.2f} · edge {:.1f}pp · expected return {:.1f}% · not approved".format(
                        market, candidate.get("selection"), float(candidate.get("decimal_odds")),
                        float(candidate.get("edge_percentage_points")),
                        float(candidate.get("expected_return_per_unit")) * 100.0,
                    )
                )
        if not any(
            (result.get("candidates") or []) or (result.get("paper_candidates") or [])
            for result in (value_screen.get("markets") or {}).values()
            if isinstance(result, dict)
        ):
            block.append("VALUE BET VERDICT: No qualifying value bet at the available prices.")
        reference_lines = _reference_market_lines(item)
        if reference_lines:
            block.append("REFERENCE BOOKMAKER PRICES — NOT VALUE PICKS")
            block.extend(reference_lines)
        block.append("")
        blocks.append(block)

    # Do not silently hide discovered fixtures just because the model cannot
    # produce an eligible forecast. Publish the fixture and the explicit gate.
    for item in fixtures:
        if item.get("status") in {"EXPERIMENTAL_ONLY", "LOW_HISTORY_FORECAST"}:
            continue
        status = str(item.get("status") or "FORECAST_UNAVAILABLE").upper()
        if status == "LOW_HISTORY_FORECAST":
            continue
        elif status == "EXPERIMENTAL_LOW_DATA":
            status = "INSUFFICIENT_HISTORY"
            reason = "Historical evidence is not yet sufficient for a reliable forecast."
        elif status == "INSUFFICIENT_HISTORY":
            reason = "Forecast withheld: insufficient reliable team history."
        elif status == "UNSUPPORTED_COMPETITION":
            reason = "Forecast withheld: competition is not mapped to a supported model."
        elif status == "KICKOFF_UNVERIFIED":
            reason = "Fixture retained; forecast withheld because its kickoff time could not be verified."
        else:
            reason = "Forecast withheld: fixture did not pass model eligibility checks."
        blocks.append([
            DIVIDER,
            f"⚽ {item.get('home_team') or 'Home'} vs {item.get('away_team') or 'Away'}",
            f"🏆 {item.get('league') or 'Competition unavailable'} · 🕒 {_format_kickoff(item.get('kickoff_local') or item.get('kickoff'), timezone_name)}",
            "FORECAST STATUS: " + status,
            reason,
            "No probabilities or betting signal published for this fixture.",
            "",
        ])

    if not blocks:
        blocks.append([DIVIDER, "No upcoming fixtures were retrieved for today.", ""])

    def render(selected: list[list[str]]) -> str:
        body = header + [line for block in selected for line in block]
        return MESSAGE_PREFIX + "\n" + "\n".join(body)

    chunks: list[str] = []
    selected: list[list[str]] = []
    for block in blocks:
        candidate = render(selected + [block])
        if len(candidate) <= MAX_MESSAGE_LENGTH:
            selected.append(block)
            continue
        if selected:
            chunks.append(render(selected))
            selected = [block]
        else:
            chunks.append(render([block])[: MAX_MESSAGE_LENGTH - 1].rstrip() + "…")
            selected = []
    if selected:
        chunks.append(render(selected))
    total = len(chunks)
    # Prefix is included during chunk sizing, so the final Telegram payload
    # never exceeds the limit after message numbering is added.
    return [
        chunk.replace(MESSAGE_PREFIX, f"🔔 🆕 NEW VELTRIX UPDATE  •  MESSAGE {index}/{total}", 1)
        for index, chunk in enumerate(chunks, start=1)
    ]


def _format_percent(value: Any) -> str:
    """Format a supplied probability without treating missing values as zero."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1:
        return f"{value:.0%}"
    return "—"


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
    parser.add_argument("--force", action="store_true", help="Allow an explicitly requested replacement report to be delivered again for the same date.")
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
        report_date = str(report.get("as_of_date", ""))
        repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
        github_token = os.environ.get("GITHUB_TOKEN", "").strip()
        messages = format_report_messages(report, ledger)
        report_hash = _report_fingerprint(messages)
        delivery_state = None
        delivery_sha = None
        same_day_update = False
        if repo and github_token:
            delivery_state, delivery_sha = _load_delivery_state(repo, github_token)
            if _should_skip_delivery(delivery_state, report_date, report_hash, args.force):
                print(f"Telegram delivery skipped: this exact report for {report_date} was already sent.")
                return
            same_day_update = report_date in delivery_state["sent_dates"]
        else:
            print("WARNING: persistent duplicate-prevention is unavailable outside GitHub Actions.", file=sys.stderr)

        if same_day_update and not args.force:
            messages = _mark_same_day_update(messages)
            print(f"Sending an updated same-day report for {report_date}; its fixture/report content differs from the last recorded delivery.")
        for index, message in enumerate(messages, start=1):
            send_message(token, chat_id, message)
            print(f"Telegram report part {index}/{len(messages)} delivered.")
        if delivery_state is not None:
            _record_delivery_date(repo, github_token, report_date, report_hash, delivery_state, delivery_sha)
        print(f"Telegram report delivered for {report_date or 'unknown date'}.")
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError, requests.RequestException) as exc:
        print(f"TELEGRAM REPORT FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
