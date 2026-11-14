"""Authenticated Telegram webhook routes for Veltrix Football."""
from __future__ import annotations

import hmac
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException, Request as FastAPIRequest
from fastapi.responses import HTMLResponse, JSONResponse

from app.telegram_commands import handle_command
from app.report_artifacts import load_latest_report, load_dashboard_snapshot
from app.telegram_security import telegram_webhook_secret_token

app = FastAPI(title="Veltrix Football Command Centre")


def configure_publication_verifier(verifier) -> None:
    """Install the trusted server-side V2 certification/rights verifier at startup."""
    if not callable(verifier):
        raise TypeError("AUTHORITATIVE_PUBLICATION_VERIFIER_REQUIRED")
    app.state.publication_verifier = verifier


def _authoritative_publication_verifier():
    verifier = getattr(app.state, "publication_verifier", None)
    return verifier if callable(verifier) else None

DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#031017"><title>VELTRIX FOOTBALL AI — Intelligence Dashboard</title>
<style>
:root{color-scheme:dark;--bg:#020b11;--panel:#061720;--panel2:#071e28;--line:#123744;--text:#f2fbff;--muted:#89a7b4;--green:#00f0ad;--cyan:#35d8f5;--blue:#4e9aff;--amber:#ffd27a;--red:#ff6d81}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse at 50% -20%,#123947 0,transparent 55%),var(--bg);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--cyan)}button{font:inherit;cursor:pointer}.shell{max-width:1120px;margin:auto;min-height:100vh;padding-bottom:86px}
.topbar{padding:22px clamp(16px,4vw,38px) 18px;border-bottom:1px solid #11303b;background:linear-gradient(180deg,rgba(4,20,28,.97),rgba(2,11,17,.9));position:relative;overflow:hidden}
.topbar:after{content:"";position:absolute;left:0;right:0;bottom:0;height:2px;background:linear-gradient(90deg,transparent,var(--green),var(--cyan),transparent);opacity:.7}
.headrow{display:flex;align-items:center;justify-content:space-between;gap:14px}.brandbox{display:flex;align-items:center;gap:11px;min-width:0}.mark{font-weight:1000;font-size:38px;line-height:1;color:var(--green);text-shadow:0 0 20px #00f0ad55;letter-spacing:-.12em}.brand{font-size:clamp(17px,3vw,25px);font-weight:900;letter-spacing:.1em;line-height:1.15}.brand span{display:block;font-size:10px;letter-spacing:.48em;color:var(--green);margin-top:4px}.tagline{font-size:12px;color:var(--muted);margin-top:5px}.live{display:inline-flex;align-items:center;gap:7px;border:1px solid #08785e;background:#052c28;color:var(--green);border-radius:30px;padding:6px 11px;font-size:11px;font-weight:800;white-space:nowrap}.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green)}
main{padding:20px clamp(12px,3vw,30px)}.eyebrow{color:var(--green);font-weight:800;letter-spacing:.13em;text-transform:uppercase;font-size:10px}.sectionhead{display:flex;align-items:end;justify-content:space-between;gap:10px;margin:22px 2px 10px}.sectionhead h2{margin:0;font-size:18px;letter-spacing:-.02em}.muted{color:var(--muted)}.small{font-size:11px}.overview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.metric,.panel,.matchcard,.notice{background:linear-gradient(145deg,rgba(8,31,42,.97),rgba(4,17,25,.98));border:1px solid var(--line);border-radius:15px;box-shadow:inset 0 1px 0 #ffffff06}.metric{padding:13px}.metric .label{font-size:11px;color:var(--muted)}.metric .value{font-size:24px;font-weight:850;line-height:1.25;margin-top:5px}.metric .hint{font-size:10px;color:var(--green);margin-top:3px}
.notice{padding:11px 13px;margin-top:12px;color:#b7cdd6;font-size:11px;border-left:3px solid var(--cyan);overflow-wrap:anywhere}.notice.warn{border-left-color:var(--amber)}.feature{position:relative;overflow:hidden;border-radius:20px;padding:18px;background:radial-gradient(ellipse at 50% 0%,#0b4950 0,transparent 65%),linear-gradient(135deg,#061c27,#031017 75%);border:1px solid #147084;box-shadow:0 0 28px #00e5ff0b,inset 0 0 24px #00e5ff08}.feature:before{content:"";position:absolute;inset:0;pointer-events:none;background:linear-gradient(115deg,transparent 20%,#00f0ad09 50%,transparent 80%)}.featuretop{position:relative;display:flex;justify-content:space-between;gap:10px;align-items:start}.league{font-size:11px;color:var(--cyan);font-weight:750}.kickoff{font-size:11px;color:var(--muted);margin-top:3px}.forecastbadge{font-size:10px;color:var(--green);border:1px solid #08785e;border-radius:25px;padding:5px 8px;white-space:nowrap}.matchhero{position:relative;display:grid;grid-template-columns:1fr 56px 1fr;gap:8px;align-items:center;text-align:center;padding:23px 0 17px}.teamname{font-weight:850;font-size:clamp(14px,2.5vw,20px);overflow-wrap:anywhere}.teamcaption{font-size:10px;color:var(--muted);margin-top:3px}.versus{font-size:13px;color:#7e9ba7;font-weight:900}.probwrap{display:flex;align-items:center;justify-content:center;gap:18px;padding:15px 0 3px;border-top:1px solid #133642}.probmain{min-width:108px;text-align:center}.ring{width:96px;height:96px;border-radius:50%;margin:0 auto 8px;display:grid;place-items:center;position:relative;background:conic-gradient(var(--green) var(--p,0%),#163540 0)}.ring:before{content:"";position:absolute;inset:7px;border-radius:50%;background:#061720}.ringtext{position:relative;font-size:23px;font-weight:900}.ringtext small{font-size:11px}.ringlabel{font-size:10px;color:var(--muted)}.markets{flex:1;min-width:0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.market{border:1px solid #153c49;background:#03121a;border-radius:10px;padding:10px 7px;text-align:center;min-width:0}.market .mlabel{font-size:10px;color:var(--muted)}.market .mvalue{font-size:17px;font-weight:850;color:var(--text);overflow-wrap:anywhere}.market .msub{font-size:9px;color:var(--green)}.filters{display:flex;gap:8px;overflow-x:auto;padding:3px 0 10px}.filter{border:1px solid #163a46;background:#061721;color:#aac1ca;border-radius:25px;padding:8px 13px;font-size:11px;white-space:nowrap}.filter.active{border-color:#00b88a;background:#05372f;color:var(--green);box-shadow:0 0 15px #00f0ad12}.fixturelist{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.matchcard{padding:14px;min-width:0}.matchcard .teams{font-weight:800;font-size:14px;line-height:1.35;overflow-wrap:anywhere}.matchcard .meta{font-size:10px;color:var(--muted);margin:5px 0 11px}.chips{display:flex;gap:6px;flex-wrap:wrap}.chip{font-size:10px;border:1px solid #17404a;border-radius:7px;padding:5px 7px;color:#c9e5ed;background:#03121a}.chip b{color:var(--green);font-weight:800}.prices{font-size:10px;color:#a5c1cb;margin-top:10px;line-height:1.65;overflow-wrap:anywhere}.statusgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.statusitem{padding:13px}.statusitem .stitle{font-size:11px;color:var(--muted)}.statusitem .svalue{font-weight:800;margin-top:4px;overflow-wrap:anywhere}.footer{font-size:10px;color:var(--muted);margin:22px 2px 10px;line-height:1.8}.refresh{border:1px solid #13765e;color:var(--green);background:#052c27;border-radius:9px;padding:8px 12px;font-size:11px;font-weight:800}.empty{padding:24px 10px;text-align:center;color:var(--muted);border:1px dashed #19404c;border-radius:14px;font-size:12px}.bottomnav{position:fixed;bottom:0;left:0;right:0;z-index:10;background:rgba(2,13,20,.94);backdrop-filter:blur(18px);border-top:1px solid #153744;padding:9px max(12px,calc((100vw - 700px)/2)) calc(9px + env(safe-area-inset-bottom));display:flex;justify-content:space-around;gap:5px}.navitem{color:#7894a0;font-size:10px;text-align:center;text-decoration:none;min-width:0;flex:1}.navitem span{display:block;font-size:18px;line-height:1.4}.navitem.active{color:var(--green);font-weight:800}
@keyframes riseIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}@keyframes pulseGlow{0%,100%{box-shadow:0 0 0 #00f0ad00}50%{box-shadow:0 0 24px #00f0ad18}}@keyframes ringIn{from{transform:scale(.88);opacity:.5}to{transform:scale(1);opacity:1}}
.metric,.feature,.matchcard,.insightcard{animation:riseIn .45s ease both}.feature{animation:pulseGlow 4s ease-in-out infinite}.ring{animation:ringIn .55s ease-out both}.teamcrest{width:58px;height:58px;object-fit:contain;display:block;margin:0 auto 9px;filter:drop-shadow(0 0 8px #00d8ff18)}.teamfallback{width:58px;height:58px;display:grid;place-items:center;margin:0 auto 9px;border-radius:50%;font-size:18px;font-weight:900;color:var(--green);border:1px solid #1b6b76;background:radial-gradient(circle at 30% 25%,#15515b,#061720 70%)}.matchhero .teamname{font-size:clamp(13px,2.5vw,19px)}.feature .probwrap{display:grid;grid-template-columns:92px minmax(0,1fr);gap:12px;align-items:center}.feature .markets{grid-column:2;grid-row:1;grid-template-columns:repeat(3,minmax(0,1fr));width:100%;min-width:0}.feature .probmain{grid-column:1;grid-row:1;min-width:0}.feature .market{min-width:0;overflow:hidden}.feature .market .mlabel{overflow-wrap:anywhere}.feature .market .mvalue{font-size:clamp(13px,3.2vw,18px)}.feature .market .msub{font-size:9px;overflow-wrap:anywhere}.feature .prices{grid-column:1/-1;min-width:0;overflow-wrap:anywhere;padding:10px 11px;border:1px solid #123d48;border-radius:9px;background:#03131b;line-height:1.7;margin-top:0}.feature .probwrap .prices{grid-column:1/-1}.insights{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.insightcard{padding:13px;border:1px solid var(--line);border-radius:13px;background:linear-gradient(145deg,#08242d,#04131b)}.insighticon{color:var(--green);font-size:17px}.insighttitle{font-weight:800;font-size:12px;margin:5px 0}.insightbody{color:#a7c2cc;font-size:11px;line-height:1.6}.insightvalue{color:var(--green);font-weight:850}.filter{transition:background .18s,border-color .18s,transform .18s}.filter:active,.refresh:active{transform:scale(.97)}.matchcard{transition:transform .2s,border-color .2s}.matchcard:active{transform:translateY(-2px);border-color:#168b91}
@media(max-width:520px){.feature .probwrap{grid-template-columns:78px minmax(0,1fr);gap:9px}.feature .markets{gap:5px}.feature .market{padding:9px 4px}.feature .market .mlabel{font-size:9px}.feature .market .msub{font-size:8px}.teamcrest,.teamfallback{width:48px;height:48px}.insights{grid-template-columns:1fr 1fr}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;scroll-behavior:auto!important;transition:none!important}}
.reveal{opacity:0;transform:translateY(30px) scale(.985);transition:opacity .7s ease,transform .7s cubic-bezier(.2,.75,.2,1)}.reveal.in-view{opacity:1;transform:translateY(0) scale(1)}.sectionview{scroll-margin-top:16px;padding-top:8px;display:none}.sectionview.active{display:block}.section-divider{height:1px;margin:26px 0;background:linear-gradient(90deg,transparent,#147e83,transparent)}main>.section-divider{display:none}.overview-bottom{margin-top:18px}.prediction-card{margin-bottom:16px}.prediction-card .feature{margin:0}.prediction-card .open-details{display:flex;justify-content:space-between;align-items:center;margin-top:12px;color:var(--green);font-weight:800;font-size:12px}.market-list{display:grid;gap:12px}.market-fixture{padding:15px;border:1px solid var(--line);border-radius:16px;background:linear-gradient(135deg,#071e27,#04131b);animation:riseIn .5s ease both}.market-fixture h3{margin:0 0 5px;font-size:15px}.market-fixture .meta{margin-bottom:10px}.market-line{font-size:12px;color:#b8d0d9;line-height:1.8;padding-top:8px;border-top:1px solid #12313c}.status-detail{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.75;color:#a8c2cc}.statusitem.wide{grid-column:1/-1}.sectionhead h2{scroll-margin-top:16px}
@media(prefers-reduced-motion:reduce){.reveal{opacity:1;transform:none;transition:none}}
@media(min-width:760px){.featurelayout{display:grid;grid-template-columns:1.15fr .85fr;gap:14px;align-items:start}.featurelayout .sectionhead{margin-top:0}.feature{height:100%}.matchhero{padding:32px 0}.statusgrid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:520px){main{padding:14px 11px}.overview{gap:7px}.metric{padding:11px 9px}.metric .value{font-size:21px}.metric .label{font-size:10px}.feature{padding:14px}.matchhero{grid-template-columns:1fr 28px 1fr;padding:18px 0 14px}.probwrap{gap:10px;align-items:start}.ring{width:78px;height:78px}.ringtext{font-size:20px}.markets{gap:5px}.market{padding:8px 4px}.market .mvalue{font-size:14px}.market .mlabel{font-size:9px}.fixturelist{grid-template-columns:1fr}.brand{font-size:18px}.mark{font-size:33px}.tagline{font-size:10px}.live{padding:5px 8px}.statusgrid{grid-template-columns:1fr 1fr}}
</style></head><body><div class="shell">
<header class="topbar"><div class="headrow"><div><div class="brandbox"><div class="mark">V</div><div class="brand">VELTRIX<span>F O O T B A L L</span></div></div><div class="tagline">Command Centre · Football intelligence · Real published data</div></div><div class="live"><i class="dot"></i><span id="liveLabel">CHECKING DATA</span></div></div></header>
<main>
<section id="dashboardView" class="sectionview active">
<div class="sectionhead" style="margin-top:0"><div><div class="eyebrow">Match intelligence</div><h2>Featured prediction</h2></div><button class="refresh" id="refresh" onclick="loadDashboard()">↻ Refresh</button></div>
<div id="featured" class="empty">Loading the next eligible fixture…</div>
<div class="sectionhead"><div><div class="eyebrow">Model interpretation</div><h2>AI Insights · Recommended angles</h2></div></div>
<div id="insights" class="insights"><div class="empty">Preparing insights from available data…</div></div>
<div class="section-divider"></div>
<div class="sectionhead overview-bottom"><div><div class="eyebrow">Report snapshot</div><h2 id="overviewTitle">Report overview</h2></div></div>
<div id="reportFreshness" class="notice" role="status">Loading report freshness…</div><div class="overview"><div class="metric"><div class="label">Fixtures received</div><div class="value" id="fixtures">—</div><div class="hint">From published report</div></div><div class="metric"><div class="label">Eligible forecasts</div><div class="value" id="forecasts">—</div><div class="hint">Available model outputs</div></div><div class="metric"><div class="label">With market prices</div><div class="value" id="odds">—</div><div class="hint">Matched bookmaker quotes</div></div></div>
</section>
<div class="section-divider"></div>
<section id="predictionsView" class="sectionview">
<div class="sectionhead"><div><div class="eyebrow">Model output</div><h2>Predictions</h2></div><span class="small muted" id="fixtureCount">—</span></div>
<div class="filters" id="filters"><button class="filter active" data-filter="all" aria-pressed="true">All fixtures</button><button class="filter" data-filter="btts" aria-pressed="false">BTTS focus</button><button class="filter" data-filter="totals" aria-pressed="false">Over / Under</button></div>
<div id="predictions"><div class="empty">Loading fixtures…</div></div>
</section>
<div class="section-divider"></div>
<section id="marketView" class="sectionview">
<div class="sectionhead"><div><div class="eyebrow">Verified price feed</div><h2>Market odds</h2></div><span class="small muted" id="marketCount">Matched prices only</span></div>
<div id="marketOdds" class="market-list"><div class="empty">Loading matched market prices…</div></div>
</section>
<div class="section-divider"></div>
<section id="trackingView" class="sectionview">
<div class="sectionhead"><div><div class="eyebrow">Retrospective evaluation</div><h2>Paper tracking & results</h2></div></div>
<div class="notice">Paper tracking only · historical outcomes are not proof of profitability.</div>
<div class="sectionhead"><div><div class="eyebrow">Release controls</div><h2>Value validation</h2></div></div>
<div id="valueValidation" class="panel statusgrid" style="margin-top:12px"><div class="statusitem"><div class="stitle">Certificate</div><div class="svalue">Loading…</div></div></div>
<div id="trackingMetrics" class="panel statusgrid" style="margin-top:12px"><div class="statusitem"><div class="stitle">Ledger</div><div class="svalue">Loading…</div></div></div>
<div id="trackingModels" class="market-list" style="margin-top:12px"><div class="empty">Loading model metrics…</div></div>
<div class="sectionhead"><div><div class="eyebrow">Settled forecasts</div><h2>Match history</h2></div></div>
<div class="filters" id="historyFilters"><button class="filter active" data-history-filter="all" aria-pressed="true">All results</button><button class="filter" data-history-filter="wins" aria-pressed="false">Wins</button><button class="filter" data-history-filter="losses" aria-pressed="false">Losses</button><label class="filter" style="display:flex;align-items:center;gap:7px">Date <select id="historyDateSort" style="background:#061721;color:#d8edf3;border:0;outline:0"><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select></label></div>
<div id="historySummary" class="overview" style="margin-bottom:12px"></div>
<div id="trackingResults" class="market-list"><div class="empty">Loading results…</div></div>
</section>
<div class="section-divider"></div>
<section id="statusView" class="sectionview">
<div class="sectionhead"><div><div class="eyebrow">Data quality & providers</div><h2>System status</h2></div></div>
<div class="panel statusgrid" id="systemStatus"><div class="statusitem"><div class="stitle">Published report</div><div class="svalue">Checking…</div></div></div>
<div class="panel status-detail" id="statusDetails" style="margin-top:12px">Loading provider and historical coverage details…</div>
<div class="footer">Football data by <a href="https://5dollarfootballapi.com" target="_blank" rel="noopener noreferrer">5DollarFootballAPI</a>. Predictions include evidence-weighted estimates; value-bet verdicts are shown only when supported by the available evidence. Market prices are displayed only when matched to a fixture. Missing statistics are not invented; their coverage is not assumed complete. <span id="reporttime"></span></div>
</section>
</main></div>
<nav class="bottomnav"><a class="navitem active" href="#dashboardView" data-view="dashboardView"><span>⌂</span>Dashboard</a><a class="navitem" href="#predictionsView" data-view="predictionsView"><span>◎</span>Predictions</a><a class="navitem" href="#marketView" data-view="marketView"><span>▤</span>Market odds</a><a class="navitem" href="#trackingView" data-view="trackingView"><span>◷</span>Tracking</a><a class="navitem" href="#statusView" data-view="statusView"><span>▥</span>Status</a></nav>
<script>
let dashboardRows=[];let currentFilter='all';
function num(v){return v===null||v===undefined||v===''?NaN:Number(v)}
function fmt(v){const n=num(v);return Number.isFinite(n)?(n*100).toFixed(1)+'%':'—'}
function pct(v){const n=num(v);return Number.isFinite(n)?Math.max(0,Math.min(100,n*100)):0}
function text(el,value){el.textContent=value===null||value===undefined||value===''?'—':String(value)}
function marketPriceLines(m){
 const out=[];const odds=m.the_odds_api_market_odds||{};const markets=odds.markets||{};
 for(const [key,label] of [['h2h','Match result'],['btts','BTTS'],['totals','Over / Under']]){
  const market=(markets[key]||[])[0];if(!market)continue;
  const parts=(market.outcomes||[]).filter(o=>o&&Number.isFinite(Number(o.price))).map(o=>o.name+' '+Number(o.price).toFixed(2)+(o.point!==null&&o.point!==undefined?' ('+o.point+')':''));
  if(parts.length)out.push((market.bookmaker||'Bookmaker')+' '+label+': '+parts.join(' / '));
 }
 const five=(m.five_dollar_market_odds||{}).bookmakers||[];
 if(five.length){const b=five[0],bt=b.btts||{},ou=b.over_under||{};if(Number.isFinite(Number(bt.yes))&&Number.isFinite(Number(bt.no)))out.push('5Dollar BTTS: Yes '+Number(bt.yes).toFixed(2)+' / No '+Number(bt.no).toFixed(2));if(Number.isFinite(Number(ou.over))&&Number.isFinite(Number(ou.under)))out.push('5Dollar O/U '+(ou.line||2.5)+': Over '+Number(ou.over).toFixed(2)+' / Under '+Number(ou.under).toFixed(2))}
 return out;
}
function topProbability(m){const p=m.probabilities||{};const opts=[['Home',num(p.home_win)],['Draw',num(p.draw)],['Away',num(p.away_win)]].filter(x=>Number.isFinite(x[1]));opts.sort((a,b)=>b[1]-a[1]);return opts[0]||['Outcome',NaN]}
function hasModelForecast(m){const p=m&&m.probabilities;return Boolean(p&&typeof p==='object'&&Number.isFinite(num(p.home_win))&&Number.isFinite(num(p.draw))&&Number.isFinite(num(p.away_win))&&Number.isFinite(num(m.btts_yes))&&Number.isFinite(num(m.over_2_5)))}
async function fetchTeamBadge(team){
 try{const r=await fetch('https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t='+encodeURIComponent(team));if(!r.ok)return null;const d=await r.json();const rows=Array.isArray(d.teams)?d.teams:[];const normalized=team.toLowerCase().replace(/[^a-z0-9]/g,'');const match=rows.find(x=>String(x.strSport||'').toLowerCase()==='soccer'&&String(x.strTeam||'').toLowerCase().replace(/[^a-z0-9]/g,'')===normalized)||rows.find(x=>String(x.strSport||'').toLowerCase()==='soccer');return match?.strBadge||match?.strTeamBadge||null}catch(e){return null}
}
function teamVisual(name){
 const wrap=document.createElement('div');wrap.className='teamvisual';const img=document.createElement('img');img.className='teamcrest';img.alt=(name||'Team')+' crest';img.loading='lazy';img.style.display='none';const fallback=document.createElement('div');fallback.className='teamfallback';fallback.textContent=String(name||'FC').split(/\\s+/).slice(0,2).map(w=>w[0]||'').join('').toUpperCase();wrap.append(img,fallback);return {wrap,img,fallback};
}
function loadBadge(visual,name){fetchTeamBadge(name).then(url=>{if(!url)return;visual.img.onload=()=>{visual.img.style.display='block';visual.fallback.style.display='none'};visual.img.onerror=()=>{visual.img.style.display='none';visual.fallback.style.display='grid'};visual.img.src=url})}
function renderFeatured(m,targetId='featured',insightTarget='insights'){
 const box=document.getElementById(targetId);box.replaceChildren();if(!m){box.className='empty';box.textContent='No upcoming eligible fixture is available in the published report.';if(insightTarget)renderInsights(null,insightTarget);return}box.className='feature';
 const top=document.createElement('div');top.className='featuretop';const left=document.createElement('div');const league=document.createElement('div');league.className='league';league.textContent=m.league||'Competition unavailable';const kickoff=document.createElement('div');kickoff.className='kickoff';kickoff.textContent=m.kickoff_local||m.kickoff||'Kickoff not supplied';left.append(league,kickoff);const badge=document.createElement('div');badge.className='forecastbadge';const hasForecast=hasModelForecast(m);badge.textContent=hasForecast?(m.status==='LOW_HISTORY_FORECAST'?'LIMITED EVIDENCE':'MATCH ANALYSIS'):(m.status||'FORECAST UNAVAILABLE').replaceAll('_',' ');top.append(left,badge);
 const hero=document.createElement('div');hero.className='matchhero';const home=document.createElement('div');const hv=teamVisual(m.home_team);const hn=document.createElement('div');hn.className='teamname';hn.textContent=m.home_team||'Home team';const hc=document.createElement('div');hc.className='teamcaption';hc.textContent='HOME';home.append(hv.wrap,hn,hc);const vs=document.createElement('div');vs.className='versus';vs.textContent='VS';const away=document.createElement('div');const av=teamVisual(m.away_team);const an=document.createElement('div');an.className='teamname';an.textContent=m.away_team||'Away team';const ac=document.createElement('div');ac.className='teamcaption';ac.textContent='AWAY';away.append(av.wrap,an,ac);hero.append(home,vs,away);loadBadge(hv,m.home_team);loadBadge(av,m.away_team);
 const wrap=document.createElement('div');wrap.className='probwrap';
 if(hasForecast){
  const best=topProbability(m);const pw=document.createElement('div');pw.className='probmain';const ring=document.createElement('div');ring.className='ring';ring.style.setProperty('--p',pct(best[1])+'%');const rt=document.createElement('div');rt.className='ringtext';rt.textContent=fmt(best[1]);ring.append(rt);const rl=document.createElement('div');rl.className='ringlabel';rl.textContent=(best[0]==='Home'?m.home_team:best[0]==='Away'?m.away_team:'Draw')+' highest 1X2';pw.append(ring,rl);
  const mk=document.createElement('div');mk.className='markets';for(const [label,value,sub] of [['BTTS Yes',fmt(m.btts_yes),'model probability'],['Over 2.5',fmt(m.over_2_5),'model probability'],['Under 2.5',Number.isFinite(Number(m.over_2_5))?fmt(1-Number(m.over_2_5)):'—','derived estimate']]){const c=document.createElement('div');c.className='market';const l=document.createElement('div');l.className='mlabel';l.textContent=label;const v=document.createElement('div');v.className='mvalue';v.textContent=value;const su=document.createElement('div');su.className='msub';su.textContent=sub;c.append(l,v,su);mk.append(c)}wrap.append(pw,mk);
 }else{
  const unavailable=document.createElement('div');unavailable.className='notice warn';unavailable.textContent='Forecast unavailable for this fixture. Status: '+(m.status||'NOT REPORTED').replaceAll('_',' ')+'. The fixture remains visible; no probability has been fabricated.';wrap.append(unavailable);
 }
 const odds=marketPriceLines(m);if(odds.length){const price=document.createElement('div');price.className='prices';price.textContent='AVAILABLE MARKET PRICES · '+odds.join(' · ');wrap.append(price)}
 box.append(top,hero,wrap);if(insightTarget)renderInsights(m,insightTarget);
}
const VALUE_BET_MODEL_VALIDATED=false; // Enable only after repeated chronological out-of-sample validation.
function findValueBets(m){
 if(!VALUE_BET_MODEL_VALIDATED)return [];
 const markets=(m.the_odds_api_market_odds||{}).markets||{};const candidates=[
  {key:'h2h',label:'1X2 Home',p:num((m.probabilities||{}).home_win),names:[String(m.home_team||'').toLowerCase()]},
  {key:'h2h',label:'1X2 Draw',p:num((m.probabilities||{}).draw),names:['draw']},
  {key:'h2h',label:'1X2 Away',p:num((m.probabilities||{}).away_win),names:[String(m.away_team||'').toLowerCase()]},
  {key:'btts',label:'BTTS Yes',p:num(m.btts_yes),names:['yes','btts yes']},
  {key:'btts',label:'BTTS No',p:Number.isFinite(num(m.btts_yes))?1-num(m.btts_yes):NaN,names:['no','btts no']},
  {key:'totals',label:'Over 2.5',p:num(m.over_2_5),names:['over 2.5','over'],point:2.5},
  {key:'totals',label:'Under 2.5',p:Number.isFinite(num(m.over_2_5))?1-num(m.over_2_5):NaN,names:['under 2.5','under'],point:2.5}
 ];const bets=[];
 for(const c of candidates){
  if(!Number.isFinite(c.p)||c.p<=0||c.p>=1)continue;
  const list=markets[c.key]||[];const market=(list.find(x=>Number.isFinite(c.point)?Number(x.point)===c.point:true))||list[0];if(!market)continue;
  const outcome=(market.outcomes||[]).find(o=>c.names.includes(String(o.name||'').toLowerCase())&&Number.isFinite(Number(o.price)));if(!outcome)continue;
  const price=Number(outcome.price);if(price<=1)continue;const edge=c.p-1/price,ev=c.p*price-1;
  if(edge>=.05&&ev>=.05)bets.push({label:c.label,prob:c.p,price,edge,ev,bookmaker:market.bookmaker||'Matched bookmaker'});
 }
 return bets.sort((a,b)=>b.ev-a.ev);
}
function renderValueBet(m,box){
 const card=document.createElement('article');card.className='insightcard';
 const i=document.createElement('div');i.className='insighticon';i.textContent='◇';
 const t=document.createElement('div');t.className='insighttitle';t.textContent='Value Bet Verdict';
 const screen=m&&m.value_bet_screen&&typeof m.value_bet_screen==='object'?m.value_bet_screen:{};
 const markets=screen.markets&&typeof screen.markets==='object'?screen.markets:{};
 const candidates=Object.entries(markets).flatMap(([market,result])=>[
  ...(result&&Array.isArray(result.candidates)?result.candidates.map(candidate=>({market,candidate,paper:true})):[]),
  ...(result&&Array.isArray(result.paper_candidates)?result.paper_candidates.map(candidate=>({market,candidate,paper:true})):[])
 ]);
 const v=document.createElement('div');v.className='insightbody insightvalue';
 const d=document.createElement('div');d.className='insightbody';
 if(candidates.length){
  const best=candidates.sort((a,b)=>Number(b.candidate.edge_percentage_points||0)-Number(a.candidate.edge_percentage_points||0))[0];
  const c=best.candidate;
  v.textContent=(best.paper?'POTENTIAL EDGE · UNDER REVIEW':'APPROVED VALUE BET')+' · '+best.market+' · '+String(c.selection||'Selection')+' @ '+Number(c.decimal_odds||0).toFixed(2);
  d.textContent='Estimated edge '+Number(c.edge_percentage_points||0).toFixed(1)+' percentage points.'+(best.paper?' This is a research candidate, not an approved betting recommendation.':'');
 }else{
  v.textContent='NO QUALIFYING VALUE BET';
  d.textContent='Available bookmaker prices do not currently show a sufficiently supported edge.';
 }
 card.append(i,t,v,d);box.append(card);
}
function renderInsights(m,targetId='insights'){
 const box=document.getElementById(targetId);if(!box)return;box.replaceChildren();if(!m){box.textContent='No eligible fixture available for insight generation.';return}
 const x=m.expected_goals||{},homeX=num(x.home),awayX=num(x.away),btts=num(m.btts_yes),over=num(m.over_2_5),best=topProbability(m),rows=[];
 rows.push(['◉','Model lean',Number.isFinite(best[1])?(best[0]==='Home'?m.home_team:best[0]==='Away'?m.away_team:'Draw')+' leads at '+fmt(best[1]):'1X2 probability unavailable','Computed from published model probabilities.']);
 rows.push(['◎','BTTS outlook',Number.isFinite(btts)?(btts>=.55?'Higher estimated chance both teams score':btts<=.45?'Model leans toward at least one team not scoring':'No strong BTTS lean'):'BTTS probability unavailable',Number.isFinite(btts)?'Model estimate: '+fmt(btts):'No value supplied.']);
 rows.push(['↗','Goal total',Number.isFinite(over)?(over>=.55?'Model leans Over 2.5':over<=.45?'Model leans Under 2.5':'No strong 2.5-goal lean'):'Totals estimate unavailable',Number.isFinite(over)?'Over 2.5 estimate: '+fmt(over):'No value supplied.']);
 rows.push(['⌁','Expected goals',Number.isFinite(homeX)&&Number.isFinite(awayX)?m.home_team+' '+homeX.toFixed(2)+' · '+m.away_team+' '+awayX.toFixed(2):'Expected-goals data unavailable','Goal estimates from the published model; not live xG statistics.']);
 if(m.prediction_basis)rows.push(['⚑','Why this verdict',m.prediction_basis,m.evidence_grade==='VERY_LOW'?'Very limited verified match history is available.':'Based on the verified results and scoring rates available before kick-off.']);
 for(const [icon,title,value,desc] of rows){const card=document.createElement('article');card.className='insightcard';const a=document.createElement('div');a.className='insighticon';a.textContent=icon;const b=document.createElement('div');b.className='insighttitle';b.textContent=title;const c=document.createElement('div');c.className='insightbody insightvalue';c.textContent=value;const d=document.createElement('div');d.className='insightbody';d.textContent=desc;card.append(a,b,c,d);box.append(card)}
 renderValueBet(m,box);
}
function renderRows(){
 const box=document.getElementById('predictions');box.replaceChildren();let rows=dashboardRows;
 if(currentFilter==='btts')rows=rows.filter(m=>m.btts_yes!==null&&m.btts_yes!==undefined&&m.btts_yes!==''&&Number.isFinite(Number(m.btts_yes)));
 if(currentFilter==='totals')rows=rows.filter(m=>m.over_2_5!==null&&m.over_2_5!==undefined&&m.over_2_5!==''&&Number.isFinite(Number(m.over_2_5)));
 document.getElementById('fixtureCount').textContent=rows.length+' fixtures shown';
 if(!rows.length){const e=document.createElement('div');e.className='empty';e.textContent='No fixtures match this filter in the published data.';box.append(e);return}
 rows.forEach((m,i)=>{
  const card=document.createElement('article');card.className='prediction-card reveal';card.style.transitionDelay=Math.min(i*45,250)+'ms';
  const title=document.createElement('h3');title.className='prediction-title';title.textContent=(m.home_team||'Home')+' vs '+(m.away_team||'Away');
  const meta=document.createElement('div');meta.className='meta';meta.textContent=(m.league||'Competition')+' · '+(m.kickoff_local||m.kickoff||'Kickoff unavailable')+(m.fixture_visibility_note?' · '+m.fixture_visibility_note:'');
  const chips=document.createElement('div');chips.className='chips';
  const hasForecast=hasModelForecast(m);
  if(hasForecast){
   const p=m.probabilities;for(const [label,value] of [['1X2 Home',fmt(p.home_win)],['1X2 Draw',fmt(p.draw)],['1X2 Away',fmt(p.away_win)],['BTTS Yes',fmt(m.btts_yes)],['Over 2.5',fmt(m.over_2_5)],['Under 2.5',Number.isFinite(num(m.over_2_5))?fmt(1-num(m.over_2_5)):'—']]){
    const chip=document.createElement('span');chip.className='chip';chip.textContent=label+' '+value;chips.append(chip);
   }
  }else{
   const chip=document.createElement('span');chip.className='chip';chip.textContent='FORECAST UNAVAILABLE · '+(m.status||'STATUS NOT REPORTED');chips.append(chip);
  }
  const odds=marketPriceLines(m);const price=document.createElement('div');price.className='prices';price.textContent=odds.length?odds.join(' · '):'No matched market odds available';
  const open=document.createElement('button');open.type='button';open.className='refresh';open.textContent=hasForecast?'View AI Insights & Value Bet →':'View fixture status →';open.style.marginTop='12px';
  const detail=document.createElement('div');detail.hidden=true;detail.className='prediction-detail';detail.style.marginTop='14px';
  const close=document.createElement('button');close.type='button';close.className='refresh';close.textContent='← Back to predictions';
  const feature=document.createElement('div');const insightHead=document.createElement('div');insightHead.className='sectionhead';const heading=document.createElement('h2');heading.textContent='AI Insights';insightHead.append(heading);
  const insight=document.createElement('div');insight.className='insights';
  detail.append(close,feature,insightHead,insight);card.append(title,meta,chips,price,open,detail);box.append(card);
  feature.id='prediction-feature-'+i;insight.id='prediction-insights-'+i;
  open.addEventListener('click',()=>{detail.hidden=false;open.hidden=true;renderFeatured(m,feature.id,null);renderInsights(m,insight.id);detail.scrollIntoView({behavior:'smooth',block:'nearest'});});
  close.addEventListener('click',()=>{detail.hidden=true;open.hidden=false;});
 });
 observeReveals(box);
}
function renderMarketOdds(){
 const box=document.getElementById('marketOdds');box.replaceChildren();const rows=dashboardRows.filter(m=>marketPriceLines(m).length);
 document.getElementById('marketCount').textContent=rows.length+' fixtures with matched prices';
 if(!rows.length){const e=document.createElement('div');e.className='empty';e.textContent='No matched bookmaker prices are available in the published report.';box.append(e);return}
 rows.forEach((m,i)=>{const card=document.createElement('article');card.className='market-fixture reveal';card.style.transitionDelay=Math.min(i*70,350)+'ms';const title=document.createElement('h3');title.textContent=(m.home_team||'Home')+' vs '+(m.away_team||'Away');const meta=document.createElement('div');meta.className='meta';meta.textContent=(m.league||'Competition')+' · '+(m.kickoff_local||m.kickoff||'Kickoff unavailable');card.append(title,meta);for(const line of marketPriceLines(m)){const row=document.createElement('div');row.className='market-line';row.textContent=line;card.append(row)}box.append(card)});
 observeReveals(box);
}
function setFilter(f){currentFilter=f;document.querySelectorAll('.filter').forEach(b=>{const active=b.dataset.filter===f;b.classList.toggle('active',active);b.setAttribute('aria-pressed',active?'true':'false')});renderRows();const title=document.querySelector('#predictions');if(title){title.setAttribute('data-active-filter',f);title.style.animation='none';void title.offsetWidth;title.style.animation='riseIn .3s ease both'}document.getElementById('predictions').scrollIntoView({behavior:'smooth',block:'start'})}
document.getElementById('filters').addEventListener('click',e=>{const b=e.target.closest('button[data-filter]');if(b)setFilter(b.dataset.filter)});
function renderPaperTracking(d){
 const data=d.paper_tracking||{};
 const validation=document.getElementById('valueValidation');validation.replaceChildren();
 const certificate=d.value_validation_certificate||{};
 const calibration=d.goal_market_calibration||{};
 const validationValues=[
  ['Certificate',certificate.status||'LOCKED_INSUFFICIENT_EVIDENCE'],
  ['Approved markets',(certificate.approved_markets||[]).join(', ')||'None'],
  ['Goal calibration',calibration.status||'NOT_REPORTED'],
  ['Calibrated forecasts',String(calibration.applied_forecasts??0)+' / '+String(calibration.compatible_forecasts??0)],
  ['1X2 paper model versions',(data.value_model_versions||[]).join(', ')||'No settled value rows'],
  ['Goal calibration versions',(data.calibration_versions||[]).length]
 ];
 for(const [title,value] of validationValues){const el=document.createElement('div');el.className='statusitem';const t=document.createElement('div');t.className='stitle';t.textContent=title;const v=document.createElement('div');v.className='svalue';v.textContent=value;el.append(t,v);validation.append(el)}
 const valueMetrics=data.value_market_metrics_by_market||{};
 const valueEntries=Object.entries(valueMetrics);
 for(const [market,m] of valueEntries){const el=document.createElement('div');el.className='statusitem wide';const t=document.createElement('div');t.className='stitle';t.textContent='Prospective '+market.replaceAll('_',' ').toUpperCase();const v=document.createElement('div');v.className='svalue';const roi=m.paper_roi===null||m.paper_roi===undefined?NaN:Number(m.paper_roi);const lower=m.roi_lower_95_ci===null||m.roi_lower_95_ci===undefined?NaN:Number(m.roi_lower_95_ci);v.textContent=String(m.settled_bets??0)+' settled · ROI '+(Number.isFinite(roi)?(roi*100).toFixed(2)+'%':'—')+' · 95% lower bound '+(Number.isFinite(lower)?(lower*100).toFixed(2)+'%':'—');el.append(t,v);validation.append(el)}
 const metrics=document.getElementById('trackingMetrics');metrics.replaceChildren();
 if(!d.paper_tracking){metrics.innerHTML='<div class="statusitem wide"><div class="svalue">Paper-tracking ledger is not available yet.</div></div>';document.getElementById('trackingModels').innerHTML='<div class="empty">No model metrics published.</div>';document.getElementById('trackingResults').innerHTML='<div class="empty">No settled results published.</div>';return}
 const last=data.last_attempt||{};
 const values=[['Ledger status',data.model_status||'PAPER_TRACKING_ONLY'],['Evaluated report dates',data.evaluated_report_dates??0],['Last evaluation',last.status||'Not evaluated'],['Updated',data.updated_at_utc||'Unknown']];
 for(const [title,value] of values){const el=document.createElement('div');el.className='statusitem';const t=document.createElement('div');t.className='stitle';t.textContent=title;const v=document.createElement('div');v.className='svalue';v.textContent=value;el.append(t,v);metrics.append(el)}
 const modelBox=document.getElementById('trackingModels');modelBox.replaceChildren();const models=data.cumulative_metrics_by_model||{};const entries=Object.entries(models);
 if(!entries.length){const empty=document.createElement('div');empty.className='empty';empty.textContent='No completed forecasts scored yet.';modelBox.append(empty)}
 for(const [name,m] of entries){const card=document.createElement('article');card.className='market-fixture';const title=document.createElement('h3');const friendlyModelName=name.replace(/^experimental_/,'').replaceAll('_',' ');title.textContent=friendlyModelName;const line=document.createElement('div');line.className='market-line';const acc=Number(m.result_accuracy);line.textContent=String(m.matches??0)+' scored · accuracy '+(Number.isFinite(acc)?(acc*100).toFixed(1)+'%':'—')+' · Brier '+(Number.isFinite(Number(m.brier_score))?Number(m.brier_score).toFixed(3):'—')+' · Log loss '+(Number.isFinite(Number(m.log_loss))?Number(m.log_loss).toFixed(3):'—');card.append(title,line);modelBox.append(card)}
 const results=document.getElementById('trackingResults');results.replaceChildren();
 const rawRows=Array.isArray(data.scored_matches)?data.scored_matches.slice():[];
 const dayOf=row=>String(row.match_date||row.fixture_date||row.report_date||'').slice(0,10);
 const seenFixtures=new Set();const allRows=rawRows.filter(row=>{const fixture=String(row.fixture_id||'').trim();const fallback=[dayOf(row),String(row.home_team||'').toLowerCase().replace(/[^a-z0-9]/g,''),String(row.away_team||'').toLowerCase().replace(/[^a-z0-9]/g,'')].join('|');const key=fixture? 'id:'+fixture : 'teams:'+fallback;if(seenFixtures.has(key))return false;seenFixtures.add(key);return true;});
 const sortControl=document.getElementById('historyDateSort');const filterBox=document.getElementById('historyFilters');
 let historyFilter='all';
 const sortRows=rows=>rows.sort((a,b)=>{const delta=dayOf(b).localeCompare(dayOf(a));return sortControl&&sortControl.value==='oldest'?-delta:delta});
 const wins=allRows.filter(r=>r.correct===true),losses=allRows.filter(r=>r.correct===false);
 const summary=document.getElementById('historySummary');summary.replaceChildren();
 for(const [label,count] of [['Total settled',allRows.length],['Wins',wins.length],['Losses',losses.length]]){const metric=document.createElement('div');metric.className='metric';const l=document.createElement('div');l.className='label';l.textContent=label;const v=document.createElement('div');v.className='value';v.textContent=String(count);metric.append(l,v);summary.append(metric)}
 const renderHistory=()=>{results.replaceChildren();let selected=historyFilter==='wins'?wins:historyFilter==='losses'?losses:allRows;selected=sortRows(selected.slice());
 if(!selected.length){const empty=document.createElement('div');empty.className='empty';empty.textContent=allRows.length?'No '+historyFilter+' recorded in the settled history.':'No settled match results published yet.';results.append(empty);return}
 const groups=new Map();for(const row of selected){const day=dayOf(row)||'Date unknown';if(!groups.has(day))groups.set(day,[]);groups.get(day).push(row)}
 for(const [day,dayRows] of groups){const heading=document.createElement('div');heading.className='sectionhead';heading.style.margin='16px 2px 8px';const h=document.createElement('h2');h.textContent=day;const count=document.createElement('span');count.className='small muted';count.textContent=dayRows.length+' result'+(dayRows.length===1?'':'s');heading.append(h,count);results.append(heading);
 for(const row of dayRows){const card=document.createElement('article');card.className='market-fixture';const title=document.createElement('h3');title.textContent=(row.home_team||'Home')+' '+(row.home_goals??'—')+' – '+(row.away_goals??'—')+' '+(row.away_team||'Away');const line=document.createElement('div');line.className='market-line';line.textContent='Predicted '+(row.predicted||'—')+' · Actual '+(row.actual||'—')+' · '+(row.correct===true?'WIN':row.correct===false?'LOSS':'UNSCORED')+' · Model '+(row.model||'unknown');if(row.report_date&&row.report_date!==day)line.textContent+=' · Report '+row.report_date;card.append(title,line);results.append(card)}}};
 if(filterBox){filterBox.onclick=e=>{const button=e.target.closest('button[data-history-filter]');if(!button)return;historyFilter=button.dataset.historyFilter;filterBox.querySelectorAll('button[data-history-filter]').forEach(b=>{const active=b===button;b.classList.toggle('active',active);b.setAttribute('aria-pressed',active?'true':'false')});renderHistory()}}
 if(sortControl)sortControl.onchange=renderHistory;renderHistory();
}
function renderStatus(d){
 const box=document.getElementById('systemStatus');box.replaceChildren();const hist=d.historical_data_coverage||{};const odds=d.live_odds_sync||{};const primary=d.primary_provider_request||{};
 const validation=d.model_validation||{};const connection=d.data_connection||{};const discovery=d.fixture_discovery||{};const selectedSources=discovery.fixture_selection?.by_source_after_cap||{};const selectedSummary=Object.entries(selectedSources).map(([name,count])=>name+' '+count).join(' · ')||'not reported';const vals=[['Dashboard data',connection.status||'UNKNOWN'],['Report freshness',connection.freshness||'UNKNOWN'],['Report publication',d.publication_status||d.status||'UNKNOWN'],['Fixture source',(primary.provider||'Unknown')+' · '+(primary.status||'unknown')+' · '+(primary.fixtures_received??0)+' fixtures'],['Selected fixture sources',selectedSummary],['5DollarFootballAPI odds',(d.multi_source_odds_sync?.five_dollar?.status||'unknown')],['The Odds API',(d.multi_source_odds_sync?.the_odds_api?.status||odds.the_odds_api_status||'unknown')],['Historical coverage',hist.status||'not reported'],['Model validation',validation.status||'NOT_REPORTED']];
 for(const [title,value] of vals){const el=document.createElement('div');el.className='statusitem reveal';const t=document.createElement('div');t.className='stitle';t.textContent=title;const v=document.createElement('div');v.className='svalue';v.textContent=value;el.append(t,v);box.append(el)}
 const details=document.getElementById('statusDetails');const lines=[];
 lines.push('Forecast validation: '+(d.warning||'Predictions are evidence-weighted; value-bet eligibility is assessed separately.'));
 lines.push('Report freshness: '+(d.as_of_date||'date unavailable')+' · generated '+(d.generated_at_utc||'unknown')+' UTC · published '+(d.published_at_utc||'unknown')+' UTC.');
 lines.push('Dashboard data connection: '+(connection.status||'unknown')+' · freshness '+(connection.freshness||'unknown')+' · report age '+(connection.report_age_days??'unknown')+' days.');
 lines.push('Fixture provider: '+(primary.provider||'unknown')+' · '+(primary.status||'unknown')+' · fixtures received from primary provider '+(primary.fixtures_received??'unknown')+'.');
 const supplementalOdds=discovery.the_odds_api||{};const inferDiscovery=discovery.infersports||{};lines.push('Fixture discovery: The Odds API added '+(supplementalOdds.fixtures_added??0)+'; InferSports discovered '+(inferDiscovery.events_received??0)+' and added '+(inferDiscovery.fixtures_added??0)+'. Selected after the 25-fixture cap: '+Object.entries(selectedSources).map(([name,count])=>name+' '+count).join(', ')+'.');
 const remaining=Number(primary.requests_remaining);if(Number.isFinite(remaining))lines.push('Provider quota reported remaining: '+remaining+' requests.');
 lines.push('5Dollar odds: '+(d.multi_source_odds_sync?.five_dollar?.status||d.live_odds_sync?.five_dollar_status||'not reported')+'.');
 lines.push('The Odds API: '+(d.multi_source_odds_sync?.the_odds_api?.status||odds.the_odds_api_status||'not reported')+'. Matched fixtures: '+(odds.fixtures_with_market_odds??d.fixtures_with_market_odds??0)+'.');
 lines.push('Historical coverage: '+(hist.status||'not reported')+'.');if(Number(hist.provider_plan_limited_date_count)>0)lines.push('Provider-limited historical dates: '+hist.provider_plan_limited_date_count+'.');if(Number(hist.retryable_gap_date_count)>0)lines.push('Transient historical gaps queued for bounded retry: '+hist.retryable_gap_date_count+'.');
 const validationData=d.model_validation||{};const dataset=validationData.dataset||{};const historical=validationData.historical_1x2||{};const models=historical.full_sample_models||{};const market=historical.market_comparison_same_fixtures||{};const market1x2=market.market||{};const elo=models.elo||{};const poisson=models.poisson||{};
 if(validationData.status){lines.push('Validation dataset: '+(dataset.valid_rows??'—')+' valid matches · '+(dataset.competition_count??'—')+' competitions · '+(dataset.first_match_date||'—')+' to '+(dataset.last_match_date||'—')+'.');}
 if(historical.release_status){lines.push('1X2 release: '+historical.release_status+'. Elo '+(Number.isFinite(Number(elo.result_accuracy))?(Number(elo.result_accuracy)*100).toFixed(2)+'%':'—')+' accuracy vs market '+(Number.isFinite(Number(market1x2.result_accuracy))?(Number(market1x2.result_accuracy)*100).toFixed(2)+'%':'—')+' on '+(market1x2.matches??'—')+' same-fixture odds matches.');}
 const goalValidation=validationData.rolling_origin_goal_market_calibration||{};const goalMarkets=goalValidation.markets||{};const passedGoals=Object.entries(goalMarkets).filter(([,v])=>v&&v.status==='CALIBRATION_DIAGNOSTIC_PASS').map(([k])=>k.toUpperCase().replaceAll('_',' '));
 if(passedGoals.length){lines.push('BTTS / totals calibration: '+passedGoals.join(', ')+' passed all '+(goalValidation.folds_evaluated||0)+' chronological diagnostic folds; report-only, not betting certification.');}
 const oneXTwo=validationData.rolling_origin_1x2_calibration||{};const oneXTwoPass=Object.values(oneXTwo).filter(v=>v&&v.status==='ROLLING_ORIGIN_DIAGNOSTIC_ONLY'&&v.calibration_diagnostic_pass).length;
 if(oneXTwoPass){lines.push('1X2 calibration: '+oneXTwoPass+' model variants improved their own calibration in rolling folds, but neither beat the bookmaker benchmark; no calibration change deployed.');}
 const provenance=validationData.dataset_provenance||{};if(provenance.rights_status){lines.push('Historical source rights: '+provenance.rights_status+' · commercial use eligible: '+(provenance.commercial_use_eligible===true?'yes':'no')+'.');}
 const gaps=Array.isArray(hist.history_gaps)?hist.history_gaps:[];if(gaps.length){lines.push('Unresolved historical dates: '+gaps.join(', ')+'. Next retry: '+(hist.retry_after_date||'next scheduled bounded retry')+'.');}
 lines.push('Value-betting release: '+(validationData.release_controls?.value_betting||'LOCKED')+'.');
 details.textContent=lines.join('\\n');observeReveals(box);observeReveals(details.parentElement);
}
function observeReveals(root=document){
 const items=root.querySelectorAll?root.querySelectorAll('.reveal:not([data-observed])'):[];
 if(!('IntersectionObserver' in window)){items.forEach(el=>el.classList.add('in-view'));return}
 if(!window.veltrixObserver)window.veltrixObserver=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.add('in-view');window.veltrixObserver.unobserve(entry.target)}}),{threshold:.12,rootMargin:'0px 0px -5% 0px'});
 items.forEach(el=>{el.dataset.observed='1';window.veltrixObserver.observe(el)});
}
function setActiveView(id){
 document.querySelectorAll('.navitem[data-view]').forEach(n=>n.classList.toggle('active',n.dataset.view===id));
 document.querySelectorAll('.sectionview').forEach(section=>section.classList.toggle('active',section.id===id));
 window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('.navitem[data-view]').forEach(n=>n.addEventListener('click',e=>{e.preventDefault();setActiveView(n.dataset.view)}));
async function fetchWithDeadline(url,ms){
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),ms);
 try{return await fetch(url,{cache:'no-store',signal:controller.signal})}finally{clearTimeout(timer)}
}
async function fetchDashboardPayload(){
 let apiError=null;
 try{
  const response=await fetchWithDeadline('/api/dashboard-data',6500);
  if(response.ok){const payload=await response.json();if(payload&&payload.status==='OK'&&Array.isArray(payload.predictions))return payload;apiError=new Error('Dashboard API returned no published report')}
  else apiError=new Error('Dashboard API HTTP '+response.status);
 }catch(error){apiError=error}
 // Independent browser-side recovery path: the published report is a static,
 // public JSON snapshot. This keeps fixture visibility working if a serverless
 // function, GitHub API rate limit, or Vercel runtime has a transient failure.
 const stamp=Date.now();
 const rawUrl='https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/command-data/public-data/dashboard_snapshot.json?v='+stamp;
 try{
  const response=await fetchWithDeadline(rawUrl,7000);
  if(!response.ok)throw new Error('Published snapshot HTTP '+response.status);
  const report=await response.json();
  if(!report||!Array.isArray(report.predictions)||!report.as_of_date)throw new Error('Published snapshot failed validation');
  return await normalizeStaticReport(report);
 }catch(rawFallbackError){
  // Second CDN route is independent of raw.githubusercontent.com.
  try{
   const cdn='https://cdn.jsdelivr.net/gh/Nexora-Apparel/veltrix-football@command-data/public-data/dashboard_snapshot.json';
   const response=await fetchWithDeadline(cdn+'?v='+stamp,6000);
   if(!response.ok)throw new Error('Mirror HTTP '+response.status);
   const report=await response.json();
   if(!report||!Array.isArray(report.predictions)||!report.as_of_date)throw new Error('Mirror snapshot failed validation');
   return await normalizeStaticReport(report);
  }catch(mirrorError){
   // Final recovery route uses the GitHub Contents API; decode UTF-8 safely.
   try{
    const api='https://api.github.com/repos/Nexora-Apparel/veltrix-football/contents/public-data/dashboard_snapshot.json?ref=command-data&v='+stamp;
    const response=await fetchWithDeadline(api,5000);
    if(!response.ok)throw new Error('GitHub API HTTP '+response.status);
    const wrapper=await response.json();
    if(!wrapper||!wrapper.content)throw new Error('GitHub API returned no file content');
    const bytes=Uint8Array.from(atob(wrapper.content.replace(/\s/g,'')),c=>c.charCodeAt(0));
    const report=JSON.parse(new TextDecoder().decode(bytes));
    if(!report||!Array.isArray(report.predictions)||!report.as_of_date)throw new Error('GitHub API snapshot failed validation');
    return await normalizeStaticReport(report);
   }catch(apiFallbackError){
    throw new Error('Dashboard API, raw CDN, mirror CDN and GitHub API all failed: '+(apiFallbackError?.message||'unknown'));
   }
  }
 }
}
async function normalizeStaticReport(report){
 const visibleRows=report.predictions.map(row=>{
  if(!row||typeof row!=='object')return row;
  const kickoff=Date.parse(row.kickoff_local||row.kickoff||'');
  const phase=row.fixture_phase||(Number.isFinite(kickoff)?(kickoff>Date.now()?'UPCOMING':'KICKOFF_PASSED'):'KICKOFF_UNVERIFIED');
  const note=row.fixture_visibility_note||(phase==='KICKOFF_PASSED'?'Kickoff has passed; fixture remains visible in this report.':phase==='KICKOFF_UNVERIFIED'?'Kickoff could not be verified; fixture retained for visibility.':undefined);
  return {...row,fixture_phase:phase,...(note?{fixture_visibility_note:note}:{})};
 });
 const normalized = {
  ...report,status:'OK',predictions:visibleRows,
  as_of_date:report.as_of_date,generated_at_utc:report.generated_at_utc,
  published_at_utc:report.command_data_published_at_utc,
  fixtures_received:report.fixtures_received??report.predictions.length,
  available_forecasts:report.predictions.filter(x=>hasModelForecast(x)).length,
  fixtures_visible:visibleRows.length,
  unsupported_fixtures:report.predictions.filter(x=>!x||!['EXPERIMENTAL_ONLY','EXPERIMENTAL_LOW_DATA','LOW_HISTORY_FORECAST'].includes(x.status)).length,
  fixtures_with_market_odds:report.fixtures_with_market_odds??0,
  data_connection:{status:'CONNECTED',freshness:report.as_of_date===new Intl.DateTimeFormat('en-CA',{timeZone:'Africa/Lagos',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())?'CURRENT':'STALE',report_date:report.as_of_date,provider:(report.primary_provider_request||{}).provider,provider_status:(report.primary_provider_request||{}).status},
  model_validation:{status:'NOT_LOADED_FROM_STATIC_FALLBACK',dataset:{},historical_1x2:{},release_controls:{}},
  paper_tracking:null,
  warning:'Dashboard is using the published static report because the live API is temporarily unavailable. Fixtures remain visible; paper history is loaded independently.'
 };
 try{
  const url='https://raw.githubusercontent.com/Nexora-Apparel/veltrix-football/command-data/public-data/paper_tracking_ledger.json?v='+Date.now();
  const response=await fetchWithDeadline(url,3500);
  if(response.ok){
   const ledger=await response.json();
   if(ledger&&ledger.model_status==='PAPER_TRACKING_ONLY'&&Array.isArray(ledger.scored_matches)){
    normalized.paper_tracking={
     model_status:ledger.model_status,updated_at_utc:ledger.updated_at_utc,
     evaluated_report_dates:ledger.evaluated_report_dates,
     cumulative_metrics_by_model:ledger.cumulative_metrics_by_model||{},
     last_attempt:ledger.last_attempt||{},
     value_market_metrics_by_market:ledger.value_market_metrics_by_market||{},
     value_model_versions:ledger.value_model_versions||[],
     calibration_versions:ledger.calibration_versions||[],
     scored_matches:ledger.scored_matches
    };
   }
  }
 }catch(_ledgerFallbackError){}
 return normalized;
}
async function loadDashboard(){
 const btn=document.getElementById('refresh');btn.disabled=true;btn.textContent='Loading…';
 try{
  const d=await fetchDashboardPayload();dashboardRows=Array.isArray(d.predictions)?d.predictions:[];
  const reportDate=String(d.as_of_date||'');const connection=d.data_connection||{};const stale=connection.freshness==='STALE'||(!!reportDate&&connection.freshness!=='CURRENT');const reused=d.report_generation_status==='REUSED_SNAPSHOT_NOT_REFRESHED';
  const liveLabel=document.getElementById('liveLabel');if(liveLabel)liveLabel.textContent=connection.status==='CONNECTED'?(stale?'CONNECTED · STALE DATA':'DATA CONNECTED'):'DATA OFFLINE';
  const dateParts=new Intl.DateTimeFormat('en-CA',{timeZone:'Africa/Lagos',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());const today=dateParts.filter(p=>['year','month','day'].includes(p.type)).reduce((o,p)=>(o[p.type]=p.value,o),{});const todayKey=today.year+'-'+today.month+'-'+today.day;
  document.getElementById('overviewTitle').textContent=reportDate?(reportDate===todayKey?"Today's overview":'Report overview · '+reportDate):'Report overview';
  const localHour=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Africa/Lagos',hour:'2-digit',hourCycle:'h23'}).format(new Date()));const offline=connection.status!=='CONNECTED'||d.status!=='OK';const reportNotice=document.getElementById('reportFreshness');if(reportNotice){reportNotice.textContent=offline?(d.warning||'Dashboard data source is not connected. Published predictions could not be loaded.') :stale?'Published-data connection is working, but the latest report is '+reportDate+'. Today’s automated report is '+(localHour<6?'scheduled for 06:00 WAT':'overdue after 06:00 WAT')+'. Older fixtures remain visible in Predictions and are not treated as today’s featured picks.':reused?'The dashboard is connected, but this is a reused snapshot; no fresh fixture retrieval completed. '+(d.report_freshness_note||'Wait for the next successful live report.'):(dashboardRows.length?'Connected to the latest current-day published report.':'Connected, but no fixtures are present in the current report.');if(!offline&&!stale&&!reused&&dashboardRows.length){reportNotice.textContent+=' Predictions: '+(d.available_forecasts??0)+'; fixtures retained without forecasts: '+(d.unsupported_fixtures??0)+'. Unsupported fixtures remain visible; no predictions are fabricated.';}reportNotice.classList.toggle('warn',offline||stale||reused||!dashboardRows.length);}
  text(document.getElementById('fixtures'),d.fixtures_received);text(document.getElementById('forecasts'),d.available_forecasts);text(document.getElementById('odds'),d.fixtures_with_market_odds);
  const currentFixtures=stale?[]:dashboardRows.filter(m=>m&&m.fixture_phase==='UPCOMING');renderFeatured(currentFixtures.find(m=>['EXPERIMENTAL_ONLY','LOW_HISTORY_FORECAST'].includes(m.status))||currentFixtures[0]||null);renderRows();renderMarketOdds();renderPaperTracking(d);renderStatus(d);observeReveals(document);
  document.getElementById('reporttime').textContent='Report date '+(d.as_of_date||'unknown')+' · published '+(d.published_at_utc||'unknown')+' UTC';
 }catch(e){
  const liveLabel=document.getElementById('liveLabel');if(liveLabel)liveLabel.textContent='DATA OFFLINE';
  document.getElementById('reportFreshness').textContent='Dashboard data connection failed. Published predictions could not be loaded; retry the dashboard connection.';
  document.getElementById('featured').textContent='Published report unavailable. Please retry shortly.';
  document.getElementById('predictions').textContent='Dashboard data request failed.';
  document.getElementById('marketOdds').textContent='Market price data unavailable.';
  document.getElementById('statusDetails').textContent='Unable to load provider and historical coverage details. Please refresh.';
 }finally{btn.disabled=false;btn.textContent='↻ Refresh'}
}
loadDashboard();
</script></body></html>"""

@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(DASHBOARD_HTML)

@app.get("/api/dashboard-data")
def dashboard_data() -> dict:
    # The daily report is the critical dependency. Validation and paper-ledger
    # snapshots are optional panels and must never block fixture delivery.
    def _safe_load(loader):
        try:
            return loader()
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=1) as pool:
        report_future = pool.submit(
            _safe_load,
            lambda: load_dashboard_snapshot(_authoritative_publication_verifier()),
        )
        report = report_future.result()
        if not isinstance(report, dict):
            report = _safe_load(
                lambda: load_latest_report(_authoritative_publication_verifier())
            )
    # Legacy paper ledgers and legacy model-validation snapshots are not V2 evidence.
    ledger = None
    model_validation = None

    if not isinstance(report, dict):
        return {"status": "UNAVAILABLE", "warning": "No published report could be loaded.", "predictions": []}
    now = datetime.now(ZoneInfo("Africa/Lagos"))
    rows = report.get("predictions") if isinstance(report.get("predictions"), list) else []
    upcoming = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        # Fixture visibility is independent of forecast eligibility. Keep
        # unsupported competitions, insufficient-history rows and unverified
        # kickoff rows visible with their explicit status; never invent odds
        # or probabilities for them.
        raw = row.get("kickoff_local") or row.get("kickoff")
        try:
            kickoff = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=ZoneInfo("Africa/Lagos"))
            if kickoff.astimezone(ZoneInfo("Africa/Lagos")) > now:
                row.setdefault("fixture_phase", "UPCOMING")
            else:
                row.setdefault("fixture_phase", "KICKOFF_PASSED")
                row.setdefault("fixture_visibility_note", "Kickoff has passed; fixture remains visible in this report.")
            upcoming.append(row)
        except (TypeError, ValueError, OverflowError):
            row.setdefault("fixture_phase", "KICKOFF_UNVERIFIED")
            row.setdefault("fixture_visibility_note", "Kickoff could not be verified; fixture retained for visibility.")
            upcoming.append(row)
    def _valid_market_price(value) -> bool:
        try:
            price = float(value)
            return math.isfinite(price) and price > 1.0
        except (TypeError, ValueError, OverflowError):
            return False

    def has_matched_market_odds(row: dict) -> bool:
        odds = row.get("the_odds_api_market_odds")
        markets = odds.get("markets") if isinstance(odds, dict) else None
        if isinstance(markets, dict):
            for key in ("h2h", "btts", "totals"):
                for market in markets.get(key, []) if isinstance(markets.get(key), list) else []:
                    outcomes = market.get("outcomes") if isinstance(market, dict) else None
                    if isinstance(outcomes, list) and any(
                        isinstance(outcome, dict)
                        and _valid_market_price(outcome.get("price"))
                        for outcome in outcomes
                    ):
                        return True
        five = row.get("five_dollar_market_odds")
        bookmakers = five.get("bookmakers") if isinstance(five, dict) else None
        return isinstance(bookmakers, list) and any(
            isinstance(bookmaker, dict) and any(
                _valid_market_price(value)
                for group in bookmaker.values() if isinstance(group, dict)
                for value in group.values()
            )
            for bookmaker in bookmakers
        )

    # Never expose report-supplied candidate arrays as releasable dashboard cards.
    for row in upcoming:
        raw_screen = row.get("value_bet_screen")
        if not isinstance(raw_screen, dict):
            continue
        raw_markets = raw_screen.get("markets")
        safe_markets = {}
        if isinstance(raw_markets, dict):
            for market, details in raw_markets.items():
                if market not in {"1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"}:
                    continue
                if not isinstance(details, dict):
                    continue
                safe_markets[market] = {
                    "status": "DISABLED_UNVALIDATED",
                    "candidates": [],
                    "paper_candidates": [],
                    "candidate_count": 0,
                    "paper_candidate_count": 0,
                }
        row["value_bet_screen"] = {
            "status": "PAPER_ONLY_CANDIDATES",
            "model_validated": False,
            "alerts_enabled": False,
            "candidate_count": 0,
            "paper_candidate_count": 0,
            "markets": safe_markets,
        }

    matched_odds_rows = sum(1 for row in upcoming if has_matched_market_odds(row))
    live_odds = report.get("live_odds_sync") if isinstance(report.get("live_odds_sync"), dict) else {}
    report_odds_count = report.get("fixtures_with_market_odds")
    try:
        report_odds_count = int(report_odds_count)
    except (TypeError, ValueError):
        report_odds_count = 0
    live_odds_count = live_odds.get("fixtures_with_market_odds")
    try:
        live_odds_count = int(live_odds_count)
    except (TypeError, ValueError):
        live_odds_count = 0
    odds_count = matched_odds_rows

    report_date = str(report.get("as_of_date") or "")
    try:
        report_age_days = max((now.date() - datetime.fromisoformat(report_date).date()).days, 0)
    except (TypeError, ValueError, OverflowError):
        report_age_days = None

    paper_tracking = None
    if isinstance(ledger, dict):
        # Model-specific paper rows are retained in the source ledger for metrics,
        # but the dashboard results API exposes one canonical row per fixture.
        scored_rows = []
        seen_scored_fixtures = set()
        raw_scored_rows = ledger.get("scored_matches") if isinstance(ledger.get("scored_matches"), list) else []
        for scored_row in raw_scored_rows:
            if not isinstance(scored_row, dict):
                continue
            fixture_id = str(scored_row.get("fixture_id") or "").strip()
            if fixture_id:
                fixture_key = "id:" + fixture_id
            else:
                team_key = "|".join(
                    re.sub(r"[^a-z0-9]", "", str(scored_row.get(field) or "").casefold())
                    for field in ("home_team", "away_team")
                )
                fixture_key = "teams:" + str(scored_row.get("report_date") or "") + ":" + team_key
            if fixture_key in seen_scored_fixtures:
                continue
            seen_scored_fixtures.add(fixture_key)
            scored_rows.append(scored_row)
        paper_tracking = {
            "model_status": ledger.get("model_status", "PAPER_TRACKING_ONLY"),
            "updated_at_utc": ledger.get("updated_at_utc"),
            "evaluated_report_dates": ledger.get("evaluated_report_dates", 0),
            "cumulative_metrics_by_model": ledger.get("cumulative_metrics_by_model") or {},
            "last_attempt": ledger.get("last_attempt") or {},
            "value_market_metrics_by_market": ledger.get("value_market_metrics_by_market") or {},
            "value_validation_markets_by_model_version": ledger.get("value_validation_markets_by_model_version") or {},
            "value_validation_markets_by_calibration_version": ledger.get("value_validation_markets_by_calibration_version") or {},
            "value_model_versions": ledger.get("value_model_versions") or [],
            "calibration_versions": ledger.get("calibration_versions") or [],
            "scored_matches_model_rows": len(raw_scored_rows),
            "scored_matches_unique_fixtures": len(scored_rows),
            "scored_matches": [
                {
                    "fixture_id": row.get("fixture_id"),
                    "home_team": row.get("home_team"),
                    "away_team": row.get("away_team"),
                    "actual": row.get("actual"),
                    "predicted": row.get("predicted"),
                    "correct": row.get("correct"),
                    "home_goals": row.get("home_goals"),
                    "away_goals": row.get("away_goals"),
                    "report_date": row.get("report_date"),
                    "model": row.get("model"),
                }
                for row in scored_rows
            ],
            "notice": ledger.get("notice", "Retrospective paper evaluation only."),
        }
    return {
        "status": "OK",
        "as_of_date": report.get("as_of_date"),
        "generated_at_utc": report.get("generated_at_utc"),
        "published_at_utc": report.get("command_data_published_at_utc"),
        "publication_status": report.get("command_data_publication", "UNKNOWN"),
        "report_generation_status": report.get("publication_status", "UNKNOWN"),
        "report_freshness_note": report.get("publication_notice"),
        "data_connection": {
            "status": "CONNECTED",
            "freshness": "CURRENT" if report.get("as_of_date") == now.date().isoformat() else "STALE",
            "report_date": report.get("as_of_date"),
            "report_age_days": report_age_days,
            "published": report.get("command_data_publication") == "PUBLISHED",
            "provider": (report.get("primary_provider_request") or {}).get("provider") if isinstance(report.get("primary_provider_request"), dict) else None,
            "provider_status": (report.get("primary_provider_request") or {}).get("status") if isinstance(report.get("primary_provider_request"), dict) else None,
            "checked_at_local": now.isoformat(),
        },
        "primary_provider_request": report.get("primary_provider_request"),
        "fixture_discovery": report.get("fixture_discovery"),
        "multi_source_odds_sync": report.get("multi_source_odds_sync"),
        "live_odds_sync": report.get("live_odds_sync"),
        "historical_data_coverage": report.get("historical_data_coverage"),
        "fixtures_received": report.get("fixtures_received", 0),
        "available_forecasts": sum(1 for row in rows if isinstance(row, dict) and isinstance(row.get("probabilities"), dict) and row.get("status") in {"EXPERIMENTAL_ONLY", "EXPERIMENTAL_LOW_DATA", "LOW_HISTORY_FORECAST"}),
        "fixtures_visible": len(upcoming),
        "unsupported_fixtures": sum(1 for row in upcoming if isinstance(row, dict) and row.get("status") not in {"EXPERIMENTAL_ONLY", "EXPERIMENTAL_LOW_DATA", "LOW_HISTORY_FORECAST"}),
        "fixtures_with_market_odds": odds_count,
        "model_validation": model_validation or {"status": "NOT_REPORTED", "dataset": {}, "historical_1x2": {}, "rolling_origin_1x2_calibration": {}, "rolling_origin_goal_market_calibration": {}, "release_controls": {}},
        "goal_market_calibration": report.get("goal_market_calibration") or {
            "status": "NOT_REPORTED", "markets": [], "compatible_forecasts": 0,
            "applied_forecasts": 0,
        },
        "value_bet_screen": {
            "status": "PAPER_ONLY_CANDIDATES",
            "model_validated": False,
            "alerts_enabled": False,
            "markets": ["1X2", "BTTS", "OVER_UNDER_1_5", "OVER_UNDER_2_5", "OVER_UNDER_3_5"],
            "candidate_count": 0,
            "paper_candidate_count": 0,
        },
        # Published report JSON is not a trusted certificate. The dashboard API
        # exposes a fixed locked state until the signed release-token verifier
        # is wired into this read path.
        "value_validation_certificate": {
            "status": "LOCKED_SOURCE_ATTESTATION_REQUIRED",
            "approved_markets": [],
            "betting_validation": False,
            "alerts_enabled": False,
            "market_diagnostics": {},
            "note": "Report-supplied certificate fields are untrusted; value alerts remain disabled.",
        },
        "paper_tracking": paper_tracking,
        "warning": "Predictions are evidence-weighted estimates. Value-bet verdicts are shown only when supported by the available evidence. The report may not be the latest live run.",
        "predictions": upcoming[:60],
    }

# Persistent reply keyboard: users can tap features instead of typing commands.
KEYBOARD = {
    "keyboard": [
        [{"text": "1X2 Predictions"}, {"text": "BTTS"}],
        [{"text": "Over/Under Goals"}, {"text": "Value Bet"}],
        [{"text": "Results"}, {"text": "Performance"}],
        [{"text": "Today's Predictions"}, {"text": "Fixtures"}],
        [{"text": "Help"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Choose a Veltrix command…",
}
BUTTON_COMMANDS = {
    "1x2 predictions": "/1x2",
    "1x2": "/1x2",
    "over/under goals": "/overunder",
    "over under goals": "/overunder",
    "btts": "/btts",
    "value bet": "/value",
    "today's predictions": "/today",
    "todays predictions": "/today",
    "fixtures": "/fixtures",
    "results": "/results",
    "performance": "/performance",
    "paper tracking": "/results",
    "results & performance": "/performance",
    "status": "/status",
    "help": "/help",
}


def _split_telegram_text(text: str, limit: int = 3900) -> list[str]:
    """Split long command reports without silently discarding later fixtures."""
    remaining = str(text or "").strip()
    if not remaining:
        return ["No report text was generated."]
    chunks: list[str] = []
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at <= 0:
            split_at = limit
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _send_message(token: str, chat_id: str, text: str) -> None:
    """Deliver the complete reply in Telegram-safe chunks; never truncate reports."""
    for index, chunk in enumerate(_split_telegram_text(text)):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        }
        if index == 0:
            payload["reply_markup"] = KEYBOARD
        request = Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(payload).encode("utf-8"),
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
            report = load_latest_report(_authoritative_publication_verifier())
            if not isinstance(report, dict):
                raise RuntimeError("PUBLISHED_V2_REPORT_UNAVAILABLE")
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
                "Odds markets are reference data only; model probabilities remain estimates.",
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
            report = load_latest_report(_authoritative_publication_verifier())
            # No legacy paper ledger is passed into V2 Telegram commands.
            ledger = None
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
