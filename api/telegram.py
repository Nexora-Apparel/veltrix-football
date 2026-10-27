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
from app.api_football_odds import APIFootballClient, APIFootballError

app = FastAPI(title="Veltrix Football Command Centre")

DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#090b10"><title>Veltrix Football</title>
<style>
:root{color-scheme:dark;--bg:#03080f;--panel:rgba(8,20,32,.9);--line:rgba(38,184,219,.23);--text:#f1f8ff;--muted:#8fa9bc;--accent:#12e6ad;--blue:#2da9ff;--warn:#f7c96c;--danger:#ff657a;--glow:0 0 28px rgba(18,230,173,.07)}
*{box-sizing:border-box}
html{min-height:100%;background:var(--bg);scroll-behavior:smooth}
body{margin:0;color:var(--text);font:14px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(ellipse at 50% -20%,rgba(19,105,161,.28),transparent 55%),radial-gradient(ellipse at 100% 40%,rgba(18,230,173,.055),transparent 38%),var(--bg);min-height:100vh}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.12;background-image:linear-gradient(rgba(72,160,190,.08) 1px,transparent 1px),linear-gradient(90deg,rgba(72,160,190,.08) 1px,transparent 1px);background-size:34px 34px;mask-image:linear-gradient(to bottom,black,transparent 80%)}
header{position:relative;padding:25px 18px 23px;background:linear-gradient(135deg,rgba(8,24,39,.97),rgba(3,8,15,.88));border-bottom:1px solid var(--line);box-shadow:0 12px 38px rgba(0,0,0,.22)}
.wrap{max-width:960px;margin:auto}
.brand{display:flex;align-items:center;gap:10px;font-size:12px;letter-spacing:.2em;color:var(--accent);font-weight:900}
.brand:before{content:"V";display:grid;place-items:center;width:30px;height:30px;border:1px solid rgba(18,230,173,.55);border-radius:9px;background:linear-gradient(145deg,rgba(18,230,173,.2),rgba(45,169,255,.1));font-size:17px;box-shadow:0 0 22px rgba(18,230,173,.13)}
h1{font-size:clamp(27px,5vw,38px);line-height:1.08;letter-spacing:-.04em;margin:16px 0 8px;font-weight:850}
.sub{color:var(--muted);font-size:12px}
header .sub{font-size:13px;max-width:600px}
main{position:relative;padding:22px 16px 100px;max-width:960px;margin:auto}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.metric,.card,.notice{position:relative;overflow:hidden;background:linear-gradient(145deg,rgba(11,28,43,.94),rgba(5,14,24,.96));border:1px solid var(--line);border-radius:17px;padding:17px;box-shadow:var(--glow);backdrop-filter:blur(14px)}
.metric:before{content:"";position:absolute;top:0;left:18px;right:45%;height:1px;background:linear-gradient(90deg,transparent,var(--accent),transparent);opacity:.75}
.label{color:var(--muted);font-size:11px;letter-spacing:.06em;text-transform:uppercase}
.value{font-size:clamp(23px,4vw,30px);font-weight:850;letter-spacing:-.04em;margin-top:7px;color:#f4fbff;font-variant-numeric:tabular-nums}
.metric:nth-child(2) .value{color:var(--accent)}.metric:nth-child(3) .value{color:var(--blue)}
h2{font-size:18px;letter-spacing:-.025em;margin:27px 0 7px}
#reporttime{overflow-wrap:anywhere;margin-bottom:12px}
.notice{margin-top:14px;color:#d5e8f5;font-size:12px;border-color:rgba(247,201,108,.3);background:linear-gradient(120deg,rgba(70,51,17,.25),rgba(8,20,32,.94));}
.card{margin:12px 0;padding:17px 17px 16px;transition:border-color .2s,transform .2s}
.card:hover{border-color:rgba(18,230,173,.48);transform:translateY(-2px)}
.teams{font-size:17px;font-weight:800;letter-spacing:-.025em}
.league{color:var(--muted);font-size:11px;margin:5px 0 13px}
.row{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px 14px;border-top:1px solid var(--line);padding-top:12px;margin-top:13px;color:#dcebf5;font-size:12px;font-variant-numeric:tabular-nums}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:10px;letter-spacing:.09em;font-weight:800;color:var(--warn);border:1px solid rgba(247,201,108,.3);background:rgba(247,201,108,.07);padding:5px 9px;border-radius:999px;white-space:nowrap}
.pill:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--warn);box-shadow:0 0 8px rgba(247,201,108,.6)}
.empty{color:var(--muted);padding:22px 0;font-size:13px}
.footer{color:var(--muted);font-size:11px;margin:25px 0 16px;line-height:1.7}
button{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:linear-gradient(110deg,rgba(18,230,173,.15),rgba(45,169,255,.12));color:var(--accent);border:1px solid rgba(18,230,173,.38);border-radius:11px;padding:11px 15px;font-weight:750;font-size:12px;cursor:pointer;transition:background .2s,border-color .2s}
button:hover{background:rgba(18,230,173,.2);border-color:var(--accent)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
@media(min-width:700px){main{padding-top:28px}.metric,.card,.notice{border-radius:19px}.grid{gap:15px}}
@media(max-width:520px){header{padding:21px 16px 19px}.grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}main{padding:17px 12px 90px}.metric{padding:12px 10px;border-radius:13px}.label{font-size:9px;letter-spacing:.025em}.value{font-size:22px}.metric:last-child{grid-column:auto}h1{font-size:29px}.card{padding:15px;border-radius:15px}.teams{font-size:15px}.row{gap:8px;font-size:11px}.notice{padding:13px;font-size:11px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important}}
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
if(d.historical_data_coverage&&d.historical_data_coverage.status==='GAPPED_OR_STALE'){const cov=d.historical_data_coverage;notice+=' Historical results have coverage gaps; forecasts may use incomplete recent history.';if(Number(cov.provider_plan_limited_date_count)>0){notice+=' '+cov.provider_plan_limited_date_count+' historical date(s) are inaccessible on the API-Football plan and will not be retried automatically.';}if(Number(cov.retryable_gap_date_count)>0){notice+=' '+cov.retryable_gap_date_count+' transient gap date(s) remain queued for bounded retry.';}}
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
        "api_football_request": report.get("api_football_request"),
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
