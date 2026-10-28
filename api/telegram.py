"""Authenticated Telegram webhook routes for Veltrix Football."""
from __future__ import annotations

import hmac
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException, Request as FastAPIRequest
from fastapi.responses import HTMLResponse, JSONResponse

from app.telegram_commands import handle_command
from app.report_artifacts import load_latest_report, load_paper_ledger
from app.telegram_security import telegram_webhook_secret_token

app = FastAPI(title="Veltrix Football Command Centre")

DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#090b10"><title>Veltrix Football</title>
<style>
:root{color-scheme:dark;--bg:#090b10;--panel:#121620;--line:#252c39;--text:#f2f5fa;--muted:#9ba6b7;--accent:#78aaff;--warn:#f4c56a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:26px 18px 18px;background:linear-gradient(145deg,#111a2a,#090b10 72%);border-bottom:1px solid var(--line)}
.wrap{max-width:960px;margin:auto} .brand{font-size:12px;letter-spacing:.18em;color:var(--accent);font-weight:800}
h1{font-size:27px;line-height:1.15;margin:8px 0} .sub{color:var(--muted);font-size:13px}
main{padding:18px;max-width:960px;margin:auto}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.metric,.card,.notice{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:15px}
.label{color:var(--muted);font-size:12px}.value{font-size:23px;font-weight:750;margin-top:3px}
h2{font-size:18px;margin:25px 0 10px}.notice{margin-top:14px;color:var(--warn);font-size:13px}
.card{margin:10px 0}.teams{font-size:16px;font-weight:750}.league{color:var(--muted);font-size:12px;margin:4px 0 12px}
.row{display:flex;justify-content:space-between;gap:12px;border-top:1px solid var(--line);padding-top:10px;margin-top:10px}
.pill{font-size:11px;color:var(--warn);border:1px solid #5c4c2b;padding:3px 7px;border-radius:20px;white-space:nowrap}
.empty{color:var(--muted);padding:16px 0}.footer{color:var(--muted);font-size:12px;margin:22px 0}
button{background:#202a3b;color:var(--text);border:1px solid #34445e;border-radius:9px;padding:9px 12px;font-weight:650}
@media(max-width:520px){.grid{grid-template-columns:1fr 1fr}.metric:last-child{grid-column:span 2}h1{font-size:24px}}
</style></head><body>
<header><div class="wrap"><div class="brand">VELTRIX FOOTBALL</div><h1>Command Centre</h1>
<div class="sub">Fixtures, experimental forecasts and system status</div></div></header>
<main><div class="grid">
<div class="metric"><div class="label">Fixtures received</div><div class="value" id="fixtures">—</div></div>
<div class="metric"><div class="label">Experimental forecasts</div><div class="value" id="forecasts">—</div></div>
<div class="metric"><div class="label">Fixtures with odds</div><div class="value" id="odds">—</div></div>
</div>
<div class="notice" id="notice">Loading published report…</div>
<h2>Upcoming experimental forecasts</h2><div class="sub" id="reporttime">Checking latest published data…</div>
<div id="predictions"><div class="empty">Loading fixtures…</div></div>
<div class="footer">Forecasts are experimental and not validated for betting. Value-betting alerts remain disabled. Data refreshes when the published report updates.</div>
<button onclick="loadDashboard()">Refresh data</button></main>
<script>
async function loadDashboard(){
const box=document.getElementById('predictions');box.replaceChildren();
try{
const r=await fetch('/api/dashboard-data',{cache:'no-store'});if(!r.ok)throw new Error('Dashboard data unavailable');const d=await r.json();
document.getElementById('fixtures').textContent=d.fixtures_received??'—';
document.getElementById('forecasts').textContent=d.experimental_forecasts??'—';
document.getElementById('odds').textContent=d.fixtures_with_market_odds??'—';
document.getElementById('reporttime').textContent='Report date: '+(d.as_of_date||'unknown')+' · Generated: '+(d.generated_at_utc||'unknown')+' · Published: '+(d.published_at_utc||'unknown');
let notice=d.warning||'Published report loaded. Forecasts are experimental.';
if(d.historical_data_coverage&&d.historical_data_coverage.status==='GAPPED_OR_STALE'){const cov=d.historical_data_coverage;notice+=' Historical results have coverage gaps; forecasts may use incomplete recent history.';if(Number(cov.provider_plan_limited_date_count)>0){notice+=' '+cov.provider_plan_limited_date_count+' historical date(s) are inaccessible on the selected provider plan and will not be retried automatically.';}if(Number(cov.retryable_gap_date_count)>0){notice+=' '+cov.retryable_gap_date_count+' transient gap date(s) remain queued for bounded retry.';}}
if(d.live_odds_sync){notice+=' Matched bookmaker odds: '+(d.live_odds_sync.fixtures_with_odds??d.fixtures_with_market_odds??0)+'.';}
document.getElementById('notice').textContent=notice;
if(!d.predictions||!d.predictions.length){const p=document.createElement('div');p.className='empty';p.textContent='No eligible upcoming experimental forecasts in the published report.';box.append(p);return;}
for(const m of d.predictions){
const card=document.createElement('article');card.className='card';
const teams=document.createElement('div');teams.className='teams';teams.textContent=(m.home_team||'Home')+' vs '+(m.away_team||'Away');card.append(teams);
const league=document.createElement('div');league.className='league';league.textContent=(m.league||'Competition')+' · '+(m.kickoff_local||m.kickoff||'Kickoff unavailable');card.append(league);
const pill=document.createElement('span');pill.className='pill';pill.textContent='EXPERIMENTAL ONLY';card.append(pill);
const row=document.createElement('div');row.className='row';
const probs=m.probabilities||{};row.textContent='Home '+fmt(probs.home_win)+' · Draw '+fmt(probs.draw)+' · Away '+fmt(probs.away_win);card.append(row);
const note=document.createElement('div');note.className='sub';note.style.marginTop='9px';note.textContent='No betting recommendation · Model not validated';card.append(note);box.append(card);
}
}catch(e){document.getElementById('notice').textContent='Could not load the published report. Please refresh shortly.';const p=document.createElement('div');p.className='empty';p.textContent='Dashboard data request failed.';box.append(p);}
}
function fmt(v){return Number.isFinite(Number(v))?(Number(v)*100).toFixed(1)+'%':'—'}
loadDashboard();
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)

@app.get("/api/dashboard-data")
def dashboard_data() -> dict:
    report = load_latest_report()
    if not isinstance(report, dict):
        return {"status": "UNAVAILABLE", "warning": "No published report could be loaded.", "predictions": []}
    now = datetime.now(ZoneInfo("Africa/Lagos"))
    rows = report.get("predictions") if isinstance(report.get("predictions"), list) else []
    upcoming = []
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "EXPERIMENTAL_ONLY":
            continue
        raw = row.get("kickoff_local") or row.get("kickoff")
        try:
            kickoff = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=ZoneInfo("Africa/Lagos"))
            if kickoff.astimezone(ZoneInfo("Africa/Lagos")) > now:
                upcoming.append(row)
        except (TypeError, ValueError, OverflowError):
            continue
    return {
        "status": "OK",
        "as_of_date": report.get("as_of_date"),
        "generated_at_utc": report.get("generated_at_utc"),
        "published_at_utc": report.get("command_data_published_at_utc"),
        "publication_status": report.get("command_data_publication", "UNKNOWN"),
        "primary_provider_request": report.get("primary_provider_request"),
        "live_odds_sync": report.get("live_odds_sync"),
        "historical_data_coverage": report.get("historical_data_coverage"),
        "fixtures_received": report.get("fixtures_received", 0),
        "experimental_forecasts": sum(1 for row in rows if isinstance(row, dict) and row.get("status") == "EXPERIMENTAL_ONLY"),
        "fixtures_with_market_odds": report.get("fixtures_with_market_odds", 0),
        "warning": "Published forecasts are experimental and not validated for betting. The report may not be the latest live run.",
        "predictions": upcoming[:60],
    }

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
            report = load_latest_report()
            request_meta = report.get("primary_provider_request") or {}
            odds_meta = report.get("multi_source_odds_sync") or {}
            live_odds = report.get("live_odds_sync") or {}
            five = odds_meta.get("five_dollar") or {}
            odds_api = odds_meta.get("the_odds_api") or {}
            infer = odds_meta.get("infer_sports") or {}
            predictions = report.get("predictions") if isinstance(report.get("predictions"), list) else []
            five_rows = sum(1 for row in predictions if isinstance(row, dict) and row.get("five_dollar_market_odds"))
            odds_api_rows = sum(1 for row in predictions if isinstance(row, dict) and row.get("the_odds_api_market_odds"))
            infer_rows = sum(1 for row in predictions if isinstance(row, dict) and row.get("infer_sports_market_odds"))
            diagnostic = "\n".join([
                "VELTRIX MULTI-SOURCE ODDS DIAGNOSTIC",
                f"Report date: {report.get('as_of_date', 'not available')}",
                f"Primary fixture provider: {request_meta.get('provider', 'not reported')}",
                f"Primary fixture status: {request_meta.get('status', 'not reported')}",
                f"Fixtures received: {request_meta.get('fixtures_received', report.get('fixtures_received', 0))}",
                f"5DollarFootballAPI odds status: {five.get('status', 'not reported')}",
                f"Fixtures with 5Dollar odds: {five_rows}",
                f"The Odds API status: {odds_api.get('status', 'not reported')}",
                f"Sports queried: {', '.join(odds_api.get('sports_queried', [])) or 'none'}",
                f"Fixtures with The Odds API prices: {odds_api_rows}",
                f"The Odds API quota metadata: {odds_api.get('quota', {})}",
                f"InferSports status: {infer.get('status', 'not reported')}",
                f"Fixtures with InferSports prices: {infer_rows}",
                f"Combined odds status: {live_odds.get('status', 'not reported')}",
                f"Fixtures with matched market odds: {report.get('fixtures_with_market_odds', 0)}",
                "Odds markets are reference data only; model probabilities remain experimental.",
                "API-Football/API-Sports is suspended and is not called by this diagnostic.",
                "No API keys are shown and no provider request is made by this command.",
            ])
            _send_message(bot_token, chat_id, "🔔 🆕 NEW VELTRIX UPDATE\n━━━━━━━━━━━━━━━━━━━━\n" + diagnostic)
        except Exception:
            _send_message(bot_token, chat_id, "🔔 🆕 NEW VELTRIX UPDATE\n━━━━━━━━━━━━━━━━━━━━\nMULTI-SOURCE DIAGNOSTIC FAILED — published report details unavailable.")
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
        _send_message(
            bot_token, chat_id,
            handle_command(command, report=report, ledger=ledger,
                           odds_data=odds_data, odds_error=odds_error)
        )
    except Exception:
        # Do not expose the update, chat id, token, or Telegram request URL.
        raise HTTPException(status_code=502, detail="Telegram reply delivery failed") from None
    return JSONResponse({"ok": True})
