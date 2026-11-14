"""V2 Telegram command renderer for certified report artifacts only.

This replaces the legacy forecast command router at the V2 webhook boundary.
It never reads legacy prediction fields, derives probabilities, or exposes
uncertified value-bet candidates.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import Any

from veltrix_v2.reporting.report_identity import ReportIdentity
from veltrix_v2.reporting.telegram import format_public_telegram_messages


_HEADER = "🔔 🆕 NEW VELTRIX UPDATE\n━━━━━━━━━━━━━━━━━━━━"
_MARKETS = {
    "1X2": (("home", "draw", "away"), ("Home", "Draw", "Away")),
    "BTTS": (("yes", "no"), ("Yes", "No")),
    "TOTALS_2_5": (("over", "under"), ("Over 2.5", "Under 2.5")),
}
_VALUE_COMMANDS = frozenset({"/value", "/1x2value", "/bttsvalue", "/overvalue"})


def _reply(body: str) -> str:
    return f"{_HEADER}\n{body.strip()}"


def _market_values(fixture: Mapping[str, Any], market: str) -> tuple[float, ...] | None:
    keys, _ = _MARKETS[market]
    markets = fixture.get("markets")
    if not isinstance(markets, Mapping):
        return None
    values = markets.get(market)
    if not isinstance(values, Mapping) or set(values) != set(keys):
        return None
    raw = [values.get(key) for key in keys]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
        for value in raw
    ):
        return None
    if abs(sum(raw) - 1.0) > 1e-6:
        return None
    return tuple(float(value) for value in raw)


def _published_fixtures(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = report.get("predictions")
    if not isinstance(rows, list):
        return []
    return [
        row for row in rows
        if isinstance(row, Mapping) and row.get("publication_status") == "PUBLISHED"
    ]


def _fixture_title(fixture: Mapping[str, Any]) -> str:
    home = str(fixture.get("home_team") or "Home")
    away = str(fixture.get("away_team") or "Away")
    competition = str(fixture.get("competition_name") or "Competition unavailable")
    kickoff = str(fixture.get("kickoff_wat") or "Time unavailable")
    return f"⚽ {home} vs {away}\n🏆 {competition} · 🕒 {kickoff}"


def _render_market(fixture: Mapping[str, Any], market: str) -> list[str]:
    if market not in fixture.get("certified_markets", []):
        return []
    values = _market_values(fixture, market)
    if values is None:
        return []
    _, labels = _MARKETS[market]
    rendered = " · ".join(
        f"{label} {value:.0%}" for label, value in zip(labels, values)
    )
    return [f"{market}: {rendered}"]


def _slipcheck(argument: str) -> str:
    try:
        odds = [float(value) for value in re.split(r"[\s,]+", argument.strip()) if value]
    except (TypeError, ValueError):
        return "Usage: /slipcheck 1.80 2.10 1.65"
    if (
        not odds
        or len(odds) > 25
        or any(not math.isfinite(value) or value <= 1 for value in odds)
    ):
        return "Invalid input. Enter 1–25 finite decimal odds, each greater than 1."
    combined = math.prod(odds)
    if not math.isfinite(combined):
        return "Invalid input. Combined decimal odds exceed the supported numeric range."
    return (
        "SLIP ARITHMETIC ONLY — NOT A BETTING RECOMMENDATION\n"
        f"Selections: {len(odds)}\nCombined decimal odds: {combined:.2f}\n"
        f"Implied break-even probability before margin: {100 / combined:.2f}%\n"
        "No selection, price or outcome has been validated."
    )


def handle_v2_command(
    text: str,
    *,
    report: Mapping[str, Any] | None,
    authorization_verifier: Callable[[Mapping[str, Any], ReportIdentity], bool] | None,
) -> str:
    """Render a Telegram command from a certified V2 report or static help."""
    raw = (text or "").strip()
    if not raw:
        return _reply("Use /help to see available commands.")
    command_token, _, argument = raw.partition(" ")
    command = command_token.split("@", 1)[0].casefold()
    argument = argument.strip()

    if command == "/start":
        return _reply("VELTRIX FOOTBALL 2.0\nUse /help for certified report commands.")
    if command == "/help":
        return _reply(
            "AVAILABLE COMMANDS\n"
            "/today or /fixtures — published fixtures\n"
            "/match Team A vs Team B — inspect one fixture\n"
            "/1x2 — certified Home/Draw/Away markets\n"
            "/btts — certified BTTS markets\n"
            "/overunder — certified Over/Under 2.5 markets\n"
            "/value — value-betting release status\n"
            "/status — report and certification availability\n"
            "/results or /performance — prospective paper results\n"
            "/slipcheck — decimal-odds arithmetic only"
        )
    if command in _VALUE_COMMANDS:
        return _reply(
            "VALUE BETTING — LOCKED\n"
            "No value-bet selections are approved for public release. "
            "Market-specific prospective certification is incomplete. "
            "No bookmaker actions are performed."
        )
    if command in {"/tomorrow", "/live"}:
        return _reply(
            f"{command[1:].upper()} — NOT CONNECTED\n"
            "The V2 report is a same-day pre-match artifact. No future-date or live-status feed is assumed."
        )
    if command in {"/goals", "/cleansheet"}:
        return _reply(
            "EXPECTED-GOALS INSIGHTS — NOT CERTIFIED\n"
            "Only explicitly certified public markets are available in V2. "
            "No expected-goals or clean-sheet probabilities are derived in this command."
        )
    if command in {"/odds", "/oddsdiag"}:
        return _reply(
            "ODDS DIAGNOSTIC — NOT EXPOSED IN THE PUBLIC V2 COMMAND\n"
            "The public report contains certified forecast markets only. "
            "No provider metadata or unverified prices are displayed."
        )
    if command in {"/slipcheck"}:
        return _reply(_slipcheck(argument))
    if command in {"/builder", "/10odds"}:
        return _reply(
            "NO AUTOMATIC BET BUILDER\n"
            "VELTRIX does not create betting slips or target combined odds. "
            "No bookmaker actions are performed."
        )
    if command in {"/results", "/performance"}:
        return _reply(
            "PROSPECTIVE PAPER RESULTS — NOT AVAILABLE\n"
            "No certified prospective settlement ledger is currently connected to this command."
        )

    if command not in {"/today", "/fixtures", "/match", "/1x2", "/btts", "/overunder", "/status"}:
        return _reply("Unknown command. Use /help.")

    if not isinstance(report, Mapping) or not callable(authorization_verifier):
        return _reply(
            "V2 REPORT UNAVAILABLE\n"
            "No public forecast is displayed until the authoritative certification and rights verifier is configured."
        )

    try:
        # Re-run the exact public rendering authorization gate before reading any fixture.
        format_public_telegram_messages(report, authorization_verifier)
    except Exception:
        return _reply("V2 REPORT UNAVAILABLE\nThe report failed publication authorization.")
    fixtures = _published_fixtures(report)
    fixture_ids = [fixture.get("fixture_id") for fixture in fixtures]
    if (
        not fixtures
        or len(fixtures) > 25
        or any(not isinstance(value, str) or not value.strip() for value in fixture_ids)
        or len(fixture_ids) != len(set(fixture_ids))
    ):
        return _reply("V2 REPORT UNAVAILABLE\\nFixture identity, uniqueness or report-size validation failed.")


    market_counts = {
        market: sum(
            1 for fixture in fixtures
            if market in fixture.get("certified_markets", [])
            and _market_values(fixture, market) is not None
        )
        for market in _MARKETS
    }
    if command == "/status":
        return _reply(
            "V2 PUBLIC REPORT STATUS\n"
            f"Report: {report.get('report_id')}\n"
            f"Date: {report.get('as_of_date')} · WAT\n"
            f"Published fixtures: {len(fixtures)}\n"
            + "\n".join(f"{market}: {count}" for market, count in market_counts.items())
            + "\nValue betting: LOCKED"
        )

    selected = fixtures
    if command == "/match":
        if not argument:
            return _reply("Usage: /match Home Team vs Away Team")
        query = argument.casefold().replace(" vs ", " ").strip()
        selected = [
            fixture for fixture in fixtures
            if query in f"{fixture.get('home_team', '')} {fixture.get('away_team', '')}".casefold()
        ]
        if not selected:
            return _reply("No matching published fixture was found.")
        selected = selected[:5]
    if command in {"/1x2", "/btts", "/overunder"}:
        market = {"/1x2": "1X2", "/btts": "BTTS", "/overunder": "TOTALS_2_5"}[command]
        selected = [
            fixture for fixture in fixtures
            if market in fixture.get("certified_markets", [])
            and _market_values(fixture, market) is not None
        ]
        if not selected:
            return _reply(f"{market} — NO CERTIFIED PUBLIC FIXTURES")
    elif command == "/fixtures":
        selected = fixtures[:25]

    lines = [
        f"VELTRIX FOOTBALL · {report.get('as_of_date')} · WAT",
        f"Report: {report.get('report_id')}",
    ]
    if command in {"/1x2", "/btts", "/overunder"}:
        lines.append(f"CERTIFIED MARKET: { {'/1x2': '1X2', '/btts': 'BTTS', '/overunder': 'TOTALS_2_5'}[command] }")
    for fixture in selected:
        lines.extend(["━━━━━━━━━━━━━━━━━━━━", _fixture_title(fixture)])
        if command in {"/1x2", "/btts", "/overunder"}:
            market = {"/1x2": "1X2", "/btts": "BTTS", "/overunder": "TOTALS_2_5"}[command]
            lines.extend(_render_market(fixture, market))
        elif command == "/match":
            for market in _MARKETS:
                lines.extend(_render_market(fixture, market))
    if command in {"/today", "/fixtures"}:
        lines.append(f"Published fixtures: {len(fixtures)}")
    lines.append("Value betting remains locked pending separate certification.")
    return _reply("\n".join(lines))
