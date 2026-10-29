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
<meta name="theme-color" content="#031017"><title>VELTRIX FOOTBALL — Intelligence Dashboard</title>
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
.reveal{opacity:0;transform:translateY(30px) scale(.985);transition:opacity .7s ease,transform .7s cubic-bezier(.2,.75,.2,1)}.reveal.in-view{opacity:1;transform:translateY(0) scale(1)}.sectionview{scroll-margin-top:16px;padding-top:8px};display:none}.sectionview.active{display:block}.section-divider{height:1px;margin:26px 0;background:linear-gradient(90deg,transparent,#147e83,transparent)}.overview-bottom{margin-top:18px}.prediction-card{margin-bottom:16px}.prediction-card .feature{margin:0}.prediction-card .open-details{display:flex;justify-content:space-between;align-items:center;margin-top:12px;color:var(--green);font-weight:800;font-size:12px}.market-list{display:grid;gap:12px}.market-fixture{padding:15px;border:1px solid var(--line);border-radius:16px;background:linear-gradient(135deg,#071e27,#04131b);animation:riseIn .5s ease both}.market-fixture h3{margin:0 0 5px;font-size:15px}.market-fixture .meta{margin-bottom:10px}.market-line{font-size:12px;color:#b8d0d9;line-height:1.8;padding-top:8px;border-top:1px solid #12313c}.status-detail{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.75;color:#a8c2cc}.statusitem.wide{grid-column:1/-1}.sectionhead h2{scroll-margin-top:16px}
@media(prefers-reduced-motion:reduce){.reveal{opacity:1;transform:none;transition:none}}
@media(min-width:760px){.featurelayout{display:grid;grid-template-columns:1.15fr .85fr;gap:14px;align-items:start}.featurelayout .sectionhead{margin-top:0}.feature{height:100%}.matchhero{padding:32px 0}.statusgrid{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:520px){main{padding:14px 11px}.overview{gap:7px}.metric{padding:11px 9px}.metric .value{font-size:21px}.metric .label{font-size:10px}.feature{padding:14px}.matchhero{grid-template-columns:1fr 28px 1fr;padding:18px 0 14px}.probwrap{gap:10px;align-items:start}.ring{width:78px;height:78px}.ringtext{font-size:20px}.markets{gap:5px}.market{padding:8px 4px}.market .mvalue{font-size:14px}.market .mlabel{font-size:9px}.fixturelist{grid-template-columns:1fr}.brand{font-size:18px}.mark{font-size:33px}.tagline{font-size:10px}.live{padding:5px 8px}.statusgrid{grid-template-columns:1fr 1fr}}
</style></head><body><div class="shell">
<header class="topbar"><div class="headrow"><div><div class="brandbox"><div class="mark">V</div><div class="brand">VELTRIX<span>F O O T B A L L</span></div></div><div class="tagline">Command Centre · Football intelligence · Real published data</div></div><div class="live"><i class="dot"></i><span id="liveLabel">REPORT</span></div></div></header>
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
<section id="statusView" class="sectionview">
<div class="sectionhead"><div><div class="eyebrow">Data quality & providers</div><h2>System status</h2></div></div>
<div class="panel statusgrid" id="systemStatus"><div class="statusitem"><div class="stitle">Published report</div><div class="svalue">Checking…</div></div></div>
<div class="panel status-detail" id="statusDetails" style="margin-top:12px">Loading provider and historical coverage details…</div>
<div class="footer">Football data by <a href="https://5dollarfootballapi.com" target="_blank" rel="noopener noreferrer">5DollarFootballAPI</a>. Forecasts are experimental and have not been validated for betting. Market prices are displayed only when matched to a fixture. Missing statistics are not invented; their coverage is not assumed complete. <span id="reporttime"></span></div>
</section>
</main></div>
<nav class="bottomnav"><a class="navitem active" href="#dashboardView" data-view="dashboardView"><span>⌂</span>Dashboard</a><a class="navitem" href="#predictionsView" data-view="predictionsView"><span>◎</span>Predictions</a><a class="navitem" href="#marketView" data-view="marketView"><span>▤</span>Market odds</a><a class="navitem" href="#statusView" data-view="statusView"><span>▥</span>Status</a></nav>
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
async function fetchTeamBadge(team){
 try{const r=await fetch('https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t='+encodeURIComponent(team));if(!r.ok)return null;const d=await r.json();const rows=Array.isArray(d.teams)?d.teams:[];const normalized=team.toLowerCase().replace(/[^a-z0-9]/g,'');const match=rows.find(x=>String(x.strSport||'').toLowerCase()==='soccer'&&String(x.strTeam||'').toLowerCase().replace(/[^a-z0-9]/g,'')===normalized)||rows.find(x=>String(x.strSport||'').toLowerCase()==='soccer');return match?.strBadge||match?.strTeamBadge||null}catch(e){return null}
}
function teamVisual(name){
 const wrap=document.createElement('div');wrap.className='teamvisual';const img=document.createElement('img');img.className='teamcrest';img.alt=(name||'Team')+' crest';img.loading='lazy';img.style.display='none';const fallback=document.createElement('div');fallback.className='teamfallback';fallback.textContent=String(name||'FC').split(/\s+/).slice(0,2).map(w=>w[0]||'').join('').toUpperCase();wrap.append(img,fallback);return {wrap,img,fallback};
}
function loadBadge(visual,name){fetchTeamBadge(name).then(url=>{if(!url)return;visual.img.onload=()=>{visual.img.style.display='block';visual.fallback.style.display='none'};visual.img.onerror=()=>{visual.img.style.display='none';visual.fallback.style.display='grid'};visual.img.src=url})}
function renderFeatured(m,targetId='featured',insightTarget='insights'){
 const box=document.getElementById(targetId);box.replaceChildren();if(!m){box.className='empty';box.textContent='No upcoming eligible fixture is available in the published report.';if(insightTarget)renderInsights(null,insightTarget);return}box.className='feature';
 const top=document.createElement('div');top.className='featuretop';const left=document.createElement('div');const league=document.createElement('div');league.className='league';league.textContent=m.league||'Competition unavailable';const kickoff=document.createElement('div');kickoff.className='kickoff';kickoff.textContent=m.kickoff_local||m.kickoff||'Kickoff not supplied';left.append(league,kickoff);const badge=document.createElement('div');badge.className='forecastbadge';badge.textContent='EXPERIMENTAL MODEL';top.append(left,badge);
 const hero=document.createElement('div');hero.className='matchhero';const home=document.createElement('div');const hv=teamVisual(m.home_team);const hn=document.createElement('div');hn.className='teamname';hn.textContent=m.home_team||'Home team';const hc=document.createElement('div');hc.className='teamcaption';hc.textContent='HOME';home.append(hv.wrap,hn,hc);const vs=document.createElement('div');vs.className='versus';vs.textContent='VS';const away=document.createElement('div');const av=teamVisual(m.away_team);const an=document.createElement('div');an.className='teamname';an.textContent=m.away_team||'Away team';const ac=document.createElement('div');ac.className='teamcaption';ac.textContent='AWAY';away.append(av.wrap,an,ac);hero.append(home,vs,away);loadBadge(hv,m.home_team);loadBadge(av,m.away_team);
 const wrap=document.createElement('div');wrap.className='probwrap';const best=topProbability(m);const pw=document.createElement('div');pw.className='probmain';const ring=document.createElement('div');ring.className='ring';ring.style.setProperty('--p',pct(best[1])+'%');const rt=document.createElement('div');rt.className='ringtext';rt.textContent=fmt(best[1]);ring.append(rt);const rl=document.createElement('div');rl.className='ringlabel';rl.textContent=(best[0]==='Home'?m.home_team:best[0]==='Away'?m.away_team:'Draw')+' highest 1X2';pw.append(ring,rl);
 const mk=document.createElement('div');mk.className='markets';for(const [label,value,sub] of [['BTTS Yes',fmt(m.btts_yes),'model probability'],['Over 2.5',fmt(m.over_2_5),'model probability'],['Under 2.5',Number.isFinite(Number(m.over_2_5))?fmt(1-Number(m.over_2_5)):'—','derived estimate']]){const c=document.createElement('div');c.className='market';const l=document.createElement('div');l.className='mlabel';l.textContent=label;const v=document.createElement('div');v.className='mvalue';v.textContent=value;const su=document.createElement('div');su.className='msub';su.textContent=sub;c.append(l,v,su);mk.append(c)}wrap.append(pw,mk);
 const odds=marketPriceLines(m);if(odds.length){const price=document.createElement('div');price.className='prices';price.textContent='AVAILABLE MARKET PRICES · '+odds.join(' · ');wrap.append(price)}
 box.append(top,hero,wrap);if(insightTarget)renderInsights(m,insightTarget);
}
function findValueBets(m){
 const markets=(m.the_odds_api_market_odds||{}).markets||{};const candidates=[
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
 const bets=findValueBets(m),card=document.createElement('article');card.className='insightcard';
 const i=document.createElement('div');i.className='insighticon';i.textContent=bets.length?'◆':'◇';
 const t=document.createElement('div');t.className='insighttitle';t.textContent='AI Value Bet';
 const v=document.createElement('div');v.className='insightbody insightvalue';const d=document.createElement('div');d.className='insightbody';
 if(bets.length){const b=bets[0];v.textContent=b.label+' · '+b.bookmaker+' @ '+b.price.toFixed(2);d.textContent='Model probability '+fmt(b.prob)+' · market implied '+fmt(1/b.price)+' · estimated edge '+(100*b.edge).toFixed(1)+' percentage points · expected return '+(100*b.ev).toFixed(1)+'% per unit stake. Experimental estimate only.'}
 else{v.textContent='No qualifying value bet identified';d.textContent='No matched BTTS or Over/Under price clears the 5-point probability-edge and 5% expected-return thresholds. No bet is recommended from this result.'}
 card.append(i,t,v,d);box.append(card);
}
function renderInsights(m,targetId='insights'){
 const box=document.getElementById(targetId);if(!box)return;box.replaceChildren();if(!m){box.textContent='No eligible fixture available for insight generation.';return}
 const x=m.expected_goals||{},homeX=num(x.home),awayX=num(x.away),btts=num(m.btts_yes),over=num(m.over_2_5),best=topProbability(m),rows=[];
 rows.push(['◉','Model lean',Number.isFinite(best[1])?(best[0]==='Home'?m.home_team:best[0]==='Away'?m.away_team:'Draw')+' leads at '+fmt(best[1]):'1X2 probability unavailable','Computed from published model probabilities.']);
 rows.push(['◎','BTTS outlook',Number.isFinite(btts)?(btts>=.55?'Higher estimated chance both teams score':btts<=.45?'Model leans toward at least one team not scoring':'No strong BTTS lean'):'BTTS probability unavailable',Number.isFinite(btts)?'Model estimate: '+fmt(btts):'No value supplied.']);
 rows.push(['↗','Goal total',Number.isFinite(over)?(over>=.55?'Model leans Over 2.5':over<=.45?'Model leans Under 2.5':'No strong 2.5-goal lean'):'Totals estimate unavailable',Number.isFinite(over)?'Over 2.5 estimate: '+fmt(over):'No value supplied.']);
 rows.push(['⌁','Expected goals',Number.isFinite(homeX)&&Number.isFinite(awayX)?m.home_team+' '+homeX.toFixed(2)+' · '+m.away_team+' '+awayX.toFixed(2):'Expected-goals data unavailable','Goal estimates from the published model; not live xG statistics.']);
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
  const meta=document.createElement('div');meta.className='meta';meta.textContent=(m.league||'Competition')+' · '+(m.kickoff_local||m.kickoff||'Kickoff unavailable');
  const chips=document.createElement('div');chips.className='chips';
  for(const [label,value] of [['BTTS Yes',fmt(m.btts_yes)],['Over 2.5',fmt(m.over_2_5)],['Under 2.5',Number.isFinite(num(m.over_2_5))?fmt(1-num(m.over_2_5)):'—']]){
   const chip=document.createElement('span');chip.className='chip';chip.textContent=label+' '+value;chips.append(chip);
  }
  const odds=marketPriceLines(m);const price=document.createElement('div');price.className='prices';price.textContent=odds.length?odds.join(' · '):'No matched market odds available';
  const open=document.createElement('button');open.type='button';open.className='refresh';open.textContent='View AI Insights & Value Bet →';open.style.marginTop='12px';
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
function renderStatus(d){
 const box=document.getElementById('systemStatus');box.replaceChildren();const hist=d.historical_data_coverage||{};const odds=d.live_odds_sync||{};const primary=d.primary_provider_request||{};
 const vals=[['Report publication',d.publication_status||d.status||'UNKNOWN'],['Fixture source',(primary.provider||'Unknown')+' · '+(primary.status||'unknown')],['The Odds API',odds.the_odds_api_status||'unknown'],['Historical coverage',hist.status||'not reported']];
 for(const [title,value] of vals){const el=document.createElement('div');el.className='statusitem reveal';const t=document.createElement('div');t.className='stitle';t.textContent=title;const v=document.createElement('div');v.className='svalue';v.textContent=value;el.append(t,v);box.append(el)}
 const details=document.getElementById('statusDetails');const lines=[];
 lines.push('Forecast validation: '+(d.warning||'Experimental model; not validated for betting.'));
 lines.push('Report freshness: '+(d.as_of_date||'date unavailable')+' · generated '+(d.generated_at_utc||'unknown')+' UTC · published '+(d.published_at_utc||'unknown')+' UTC.');
 lines.push('Fixture provider: '+(primary.provider||'unknown')+' · '+(primary.status||'unknown')+'.');
 const remaining=Number(primary.requests_remaining);if(Number.isFinite(remaining))lines.push('Provider quota reported remaining: '+remaining+' requests.');
 lines.push('5Dollar odds: '+(d.multi_source_odds_sync?.five_dollar?.status||d.live_odds_sync?.five_dollar_status||'not reported')+'.');
 lines.push('The Odds API: '+(d.multi_source_odds_sync?.the_odds_api?.status||odds.the_odds_api_status||'not reported')+'. Matched fixtures: '+(odds.fixtures_with_market_odds??d.fixtures_with_market_odds??0)+'.');
 lines.push('Historical coverage: '+(hist.status||'not reported')+'.');if(Number(hist.provider_plan_limited_date_count)>0)lines.push('Provider-limited historical dates: '+hist.provider_plan_limited_date_count+'.');if(Number(hist.retryable_gap_date_count)>0)lines.push('Transient historical gaps queued for bounded retry: '+hist.retryable_gap_date_count+'.');
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
async function loadDashboard(){
 const btn=document.getElementById('refresh');btn.disabled=true;btn.textContent='Loading…';
 try{
  const r=await fetch('/api/dashboard-data',{cache:'no-store'});if(!r.ok)throw new Error('Dashboard data unavailable');const d=await r.json();dashboardRows=Array.isArray(d.predictions)?d.predictions:[];
  const reportDate=String(d.as_of_date||'');const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Africa/Lagos',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  document.getElementById('overviewTitle').textContent=reportDate?(reportDate===today?"Today's overview":'Report overview · '+reportDate):'Report overview';
  const stale=!!reportDate&&reportDate!==today;const reportNotice=document.getElementById('reportFreshness');if(reportNotice){reportNotice.textContent=stale?'Showing the saved report from '+reportDate+'. It is not today’s report; refresh the data pipeline for current fixtures.':(dashboardRows.length?'Current-day report loaded.':'No upcoming matches found in the current report.');reportNotice.classList.toggle('warn',stale||!dashboardRows.length);}
  text(document.getElementById('fixtures'),d.fixtures_received);text(document.getElementById('forecasts'),d.experimental_forecasts);text(document.getElementById('odds'),d.fixtures_with_market_odds);
  renderFeatured(dashboardRows[0]);renderRows();renderMarketOdds();renderStatus(d);observeReveals(document);
  document.getElementById('reporttime').textContent='Report date '+(d.as_of_date||'unknown')+' · published '+(d.published_at_utc||'unknown')+' UTC';
 }catch(e){
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
