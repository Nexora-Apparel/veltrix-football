"""V2 Telegram rendering boundary.

Formatting is deliberately separate from network delivery. Public rendering
requires an injected verifier backed by the authoritative publication gate.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import math
from typing import Any

from veltrix_v2.reporting.delivery import (
    DeliveryAttempt,
    DeliveryReceipt,
    DeliveryStore,
    deliver_once,
)
from veltrix_v2.reporting.report_identity import (
    ReportIdentity,
    verify_report_identity,
)

TELEGRAM_TEXT_LIMIT = 3900
PUBLIC_RELEASE_MODES = frozenset({"RESTRICTED_PUBLIC", "FULL_PUBLIC"})
MARKET_LABELS = {
    "1X2": ("Home", "Draw", "Away"),
    "BTTS": ("Yes", "No"),
    "TOTALS_2_5": ("Over 2.5", "Under 2.5"),
}


def _market_percentages(values: Mapping[str, Any], keys: tuple[str, ...]) -> list[str]:
    probabilities = [values.get(key) for key in keys]
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        or not math.isfinite(value) or not 0 <= value <= 1
        for value in probabilities
    ):
        raise ValueError("CERTIFIED_MARKET_PROBABILITY_INVALID")
    if abs(sum(probabilities) - 1.0) > 1e-6:
        raise ValueError("CERTIFIED_MARKET_PROBABILITIES_NOT_NORMALIZED")
    return [f"{value:.0%}" for value in probabilities]


def _fixture_block(fixture: Mapping[str, Any]) -> list[str]:
    home = fixture.get("home_team")
    away = fixture.get("away_team")
    if not isinstance(home, str) or not home.strip() or not isinstance(away, str) or not away.strip():
        raise ValueError("published fixture requires both team names")
    kickoff = fixture.get("kickoff_wat")
    competition = fixture.get("competition_name") or "Competition unavailable"
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        f"⚽ {home} vs {away}",
        f"🏆 {competition} · 🕒 {kickoff if isinstance(kickoff, str) and kickoff else 'Time unavailable'}",
    ]
    markets = fixture.get("markets")
    if not isinstance(markets, Mapping):
        raise ValueError("published fixture markets must be an object")
    certified = fixture.get("certified_markets")
    if not isinstance(certified, list):
        raise ValueError("certified_markets must be an explicit list")
    for market in ("1X2", "BTTS", "TOTALS_2_5"):
        if market not in certified:
            continue
        values = markets.get(market)
        if not isinstance(values, Mapping):
            raise ValueError(f"certified market {market} has no probabilities")
        if market == "1X2":
            home, draw, away = _market_percentages(values, ("home", "draw", "away"))
            rendered = f"Home {home} | Draw {draw} | Away {away}"
        elif market == "BTTS":
            yes, no = _market_percentages(values, ("yes", "no"))
            rendered = f"Yes {yes} | No {no}"
        else:
            over, under = _market_percentages(values, ("over", "under"))
            rendered = f"Over 2.5 {over} | Under 2.5 {under}"
        lines.append(f"{market}: {rendered}")
    if not certified:
        lines.append("Forecast unavailable: no market passed publication certification.")
    return lines


def format_public_telegram_messages(
    report: Mapping[str, Any],
    authorization_verifier: Callable[[Mapping[str, Any], ReportIdentity], bool],
) -> list[str]:
    """Render only a hash-verified report accepted by the publication verifier.

    This function never sends messages. It refuses shadow/research reports and
    never renders value bets; those require a separate market certification.
    """
    identity = verify_report_identity(report)
    if report.get("release_mode") not in PUBLIC_RELEASE_MODES:
        raise PermissionError("report is not in an approved public release mode")
    if not callable(authorization_verifier) or not authorization_verifier(report, identity):
        raise PermissionError("authoritative publication authorization was not verified")
    fixtures = report.get("predictions")
    if not isinstance(fixtures, list):
        raise ValueError("report predictions must be a list")
    header = [
        "🔔 🆕 NEW VELTRIX UPDATE",
        "⚽ VELTRIX FOOTBALL · DAILY REPORT",
        f"📅 {identity.as_of_date} · WAT",
        f"Report: {identity.report_id}",
    ]
    blocks = []
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            raise ValueError("report contains a malformed fixture")
        if fixture.get("publication_status") != "PUBLISHED":
            continue
        blocks.append(_fixture_block(fixture))
    if not blocks:
        blocks.append(["No certified fixtures are available for this report."])

    messages: list[str] = []
    current = list(header)
    for block in blocks:
        candidate = current + block
        if len("\n".join(candidate)) <= TELEGRAM_TEXT_LIMIT:
            current = candidate
            continue
        if len(current) > len(header):
            messages.append("\n".join(current))
            current = list(header)
        if len("\n".join(current + block)) > TELEGRAM_TEXT_LIMIT:
            raise ValueError("single fixture block exceeds Telegram message limit")
        current.extend(block)
    if current:
        messages.append("\n".join(current))
    total = len(messages)
    return [
        message.replace(
            "🔔 🆕 NEW VELTRIX UPDATE",
            f"🔔 🆕 NEW VELTRIX UPDATE · MESSAGE {index}/{total}",
            1,
        )
        for index, message in enumerate(messages, start=1)
    ]


def dispatch_public_telegram_report(
    report: Mapping[str, Any],
    destination: str,
    authorization_verifier: Callable[[Mapping[str, Any], ReportIdentity], bool],
    store: DeliveryStore,
    send_message: Callable[[str, str], str],
) -> DeliveryAttempt:
    """Format and dispatch one immutable report through the idempotent store.

    The caller supplies the real Telegram transport. This module has no
    credentials or network access. A partial multi-message failure is marked
    OUTCOME_UNKNOWN and must be reconciled manually before any further send.
    """
    identity = verify_report_identity(report)
    messages = format_public_telegram_messages(report, authorization_verifier)

    def send_all() -> DeliveryReceipt:
        message_ids = []
        for message in messages:
            message_id = send_message(destination, message)
            if not isinstance(message_id, (str, int)) or not str(message_id).strip():
                raise RuntimeError("TELEGRAM_MESSAGE_ID_MISSING")
            message_ids.append(str(message_id))
        return DeliveryReceipt(destination, tuple(message_ids))

    return deliver_once(identity, destination, store, send_all)
