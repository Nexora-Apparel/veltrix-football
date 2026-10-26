"""Authenticated Telegram webhook routes for Veltrix Football."""
from __future__ import annotations

import hmac
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException, Request as FastAPIRequest
from fastapi.responses import JSONResponse

from app.telegram_commands import handle_command
from app.report_artifacts import load_latest_report, load_paper_ledger
from app.telegram_security import telegram_webhook_secret_token
from app.api_football_odds import APIFootballClient, APIFootballError

app = FastAPI(title="Veltrix Football Telegram Command Centre")

# Persistent reply keyboard: users can tap features instead of typing commands.
KEYBOARD = {
    "keyboard": [
        [{"text": "Over/Under Goals"}, {"text": "BTTS"}],
        [{"text": "Today's Predictions"}, {"text": "Fixtures"}],
        [{"text": "Paper Tracking"}, {"text": "Results & Performance"}],
        [{"text": "Status"}, {"text": "Help"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Choose a Veltrix feature…",
}
BUTTON_COMMANDS = {
    "over/under goals": "/overunder",
    "over under goals": "/overunder",
    "btts": "/btts",
    "today's predictions": "/today",
    "todays predictions": "/today",
    "fixtures": "/fixtures",
    "paper tracking": "/results",
    "results & performance": "/performance",
    "status": "/status",
    "help": "/help",
}


def _send_message(token: str, chat_id: str, text: str) -> None:
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text[:3900],
        "disable_web_page_preview": True,
        "reply_markup": KEYBOARD,
    }).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=8) as response:
        result = json.loads(response.read().decode("utf-8"))
        if response.status >= 300 or not result.get("ok"):
            raise RuntimeError("Telegram rejected command reply")


@app.get("/api/telegram")
@app.get("/api/index")
def health() -> dict[str, str]:
    return {"service": "Veltrix Telegram Command Centre", "status": "ready"}


@app.post("/api/telegram")
@app.post("/api/index")
async def telegram_webhook(
    request: FastAPIRequest,
    secret_header: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
) -> JSONResponse:
    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    allowed_chat = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not expected_secret or not bot_token or not allowed_chat:
        raise HTTPException(status_code=503, detail="Webhook environment is not configured")
    try:
        expected_token = telegram_webhook_secret_token(expected_secret)
    except ValueError:
        raise HTTPException(status_code=503, detail="Webhook environment is not configured") from None
    if not secret_header or not hmac.compare_digest(secret_header, expected_token):
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    text = str(message.get("text") or "")
    if chat_id != allowed_chat:
        return JSONResponse({"ok": True})
    # Telegram reply-keyboard buttons arrive as ordinary text messages.
    command = BUTTON_COMMANDS.get(text.strip().casefold(), text)
    if not command.startswith("/"):
        return JSONResponse({"ok": True})
    if command.strip().split()[0].split("@", 1)[0].casefold() == "/oddsdiag":
        try:
            today_lagos = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
            client = APIFootballClient()
            status = client.status()
            odds = client.odds_for_date(today_lagos, timezone="Africa/Lagos")
            meta = odds.get("_veltrix_meta") or {}
            subscription = status.get("subscription") or {}
            diagnostic = "\n".join([
                "API-FOOTBALL / API-SPORTS CONNECTION DIAGNOSTIC",
                "Authentication: SUCCESS",
                f"Subscription active: {subscription.get('active', 'not reported')}",
                f"Plan: {subscription.get('plan', 'not reported')}",
                f"Requests remaining: {(meta.get('requests_remaining') or 'not reported')}",
                f"Prematch odds rows for {today_lagos}: {odds.get('results', 0)}",
                f"Odds status: {meta.get('status', 'UNKNOWN')}",
                f"Team-name enrichment: {meta.get('team_name_enrichment', 'not reported')}",
                f"Enrichment detail: {meta.get('team_name_enrichment_detail', 'none')}",
                f"Provider raw fixture rows: {meta.get('raw_fixture_rows', 0)}",
                f"Fixtures with bookmakers: {meta.get('fixtures_with_bookmakers', 0)}",
                f"Bookmaker records: {meta.get('bookmaker_count', 0)}",
                f"Sample market names: {', '.join(meta.get('sample_market_names', [])) or 'none returned'}",
                "Sample fixtures:",
                *[
                    f"- {row.get('match')} | {row.get('date')} | {row.get('league')} | fixture ID {row.get('fixture_id')}"
                    for row in meta.get('fixture_examples', [])
                ],
                "Use fixture IDs and bookmaker counts to distinguish missing coverage from response-normalization issues.",
                "API key and account email are never shown.",
            ])
            _send_message(bot_token, chat_id, "🔔 🆕 NEW VELTRIX UPDATE\n━━━━━━━━━━━━━━━━━━━━\n" + diagnostic)
        except APIFootballError as exc:
            _send_message(
                bot_token, chat_id,
                "🔔 🆕 NEW VELTRIX UPDATE\n━━━━━━━━━━━━━━━━━━━━\nAPI-FOOTBALL DIAGNOSTIC — UNAVAILABLE\n" + str(exc)
            )
        except Exception:
            _send_message(bot_token, chat_id, "🔔 🆕 NEW VELTRIX UPDATE\n━━━━━━━━━━━━━━━━━━━━\nODDS DIAGNOSTIC FAILED — internal details withheld.")
        return JSONResponse({"ok": True})
    try:
        # Read published snapshots only. This never starts prediction jobs or
        # consumes the football provider's API quota.
        try:
            report = load_latest_report()
            ledger = load_paper_ledger()
        except Exception:
            # A data-source outage must not break the Telegram webhook.
            report, ledger = None, None
        odds_data = None
        odds_error = None
        if command.strip().split()[0].split("@", 1)[0].casefold() == "/odds":
            try:
                today_lagos = datetime.now(ZoneInfo("Africa/Lagos")).date().isoformat()
                odds_data = APIFootballClient().odds_for_date(today_lagos, timezone="Africa/Lagos")
            except APIFootballError as exc:
                odds_error = str(exc)
            except Exception:
                odds_error = "Unexpected odds-provider error; details were withheld."
        _send_message(
            bot_token, chat_id,
            handle_command(command, report=report, ledger=ledger,
                           odds_data=odds_data, odds_error=odds_error)
        )
    except Exception:
        # Do not expose the update, chat id, token, or Telegram request URL.
        raise HTTPException(status_code=502, detail="Telegram reply delivery failed") from None
    return JSONResponse({"ok": True})
