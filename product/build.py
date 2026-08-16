"""
Trendlines — public product site generator (English, global audience).

Builds a customer-facing, subscription-gated site from the live pipeline data
(dashboard/data/*). The internal dashboard stays untouched as the research lab.

Pages: index (landing) · breakouts · supports · watchlist · pricing.

Paywall note: gating here is FRONT-END DEMO ONLY (localStorage flag + CSS blur).
Real gating must be server-side — see product/INTEGRATIONS.md.

Usage:  python -m product.build     (rerun after every dashboard.daily)
"""
import json
import os

import pandas as pd

OUT = 'product/site'
BRAND = 'Trendlines'
ALGO = 'Diago'          # the engine's name — from the Diagonals it hunts
ALGO_MARK = '◢'


# ---------------------------------------------------------------- design system

def css():
    return """
  :root {
    --bg:#F6F7F9; --surface:#FFFFFF; --ink:#0F1726; --ink2:#49556A; --ink3:#8A94A6;
    --line:#E4E8EF; --navy:#0D1B2E; --navy2:#13253D;
    --accent:#0E9382; --accent-ink:#0A6E62; --accent-soft:#E4F3F0;
    --rust:#C05C1D; --rust-soft:#F8ECE1; --danger:#A8323C;
    --radius:12px;
    --shadow:0 1px 2px rgba(13,27,46,.05), 0 10px 28px -14px rgba(13,27,46,.14);
  }
  * { box-sizing:border-box; margin:0; }
  html { scroll-behavior:smooth; }
  body { background:var(--bg); color:var(--ink); line-height:1.6;
         font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }
  a { color:inherit; text-decoration:none; }
  .num { font-variant-numeric:tabular-nums; }
  .wrap { max-width:1140px; margin:0 auto; padding:0 24px; }

  header.nav { position:sticky; top:0; z-index:50; background:rgba(246,247,249,.85);
    backdrop-filter:blur(12px); border-bottom:1px solid var(--line); }
  .nav-in { display:flex; align-items:center; gap:26px; height:64px; }
  .logo { display:flex; align-items:center; gap:10px; font-size:19px; font-weight:800; letter-spacing:-.02em; }
  .nav-links { display:flex; gap:4px; font-size:14px; font-weight:600; color:var(--ink2); }
  .nav-links a { padding:8px 13px; border-radius:8px; }
  .nav-links a:hover { background:var(--surface); color:var(--ink); }
  .nav-links a.on { background:var(--navy); color:#fff; }
  .nav-cta { margin-inline-start:auto; display:flex; gap:10px; align-items:center; }
  .btn { display:inline-block; font-weight:700; font-size:14.5px; border-radius:10px;
         padding:10px 20px; border:1px solid transparent; cursor:pointer; transition:all .15s; }
  .btn.primary { background:var(--accent); color:#fff; }
  .btn.primary:hover { background:var(--accent-ink); }
  .btn.ghost { border-color:var(--line); background:var(--surface); color:var(--ink); }
  .btn.ghost:hover { border-color:var(--ink3); }
  .btn.big { padding:14px 30px; font-size:16px; }
  .btn:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .sub-badge { font-size:12px; font-weight:700; color:var(--accent-ink); background:var(--accent-soft);
               padding:4px 10px; border-radius:99px; display:none; }
  body.subbed .sub-badge { display:inline-block; }
  body.subbed .hide-when-subbed { display:none; }

  .hero { background:var(--navy); color:#EAF0F7; position:relative; overflow:hidden; }
  .hero.warm { background:linear-gradient(118deg, #0D1B2E 0%, #241A1B 30%, #3C2212 56%, #59300F 78%, #2A1508 100%);
    background-size:260% 260%; animation:heroShift 16s ease-in-out infinite alternate; }
  @keyframes heroShift { from { background-position:0% 30%; } to { background-position:100% 70%; } }
  .hero .glow { position:absolute; border-radius:50%; filter:blur(70px); pointer-events:none;
    background:radial-gradient(circle, rgba(224,138,60,.30), rgba(224,138,60,0) 65%); }
  .hero .glow.g1 { width:560px; height:560px; top:-130px; right:-60px;
    animation:glowDrift 13s ease-in-out infinite alternate; }
  .hero .glow.g2 { width:380px; height:380px; bottom:-140px; left:16%;
    background:radial-gradient(circle, rgba(192,92,29,.22), rgba(192,92,29,0) 65%);
    animation:glowDrift 17s ease-in-out infinite alternate-reverse; }
  @keyframes glowDrift { from { transform:translate(0,0) scale(1); }
    to { transform:translate(-170px,120px) scale(1.3); } }
  .hero-lines { animation:floaty 12s ease-in-out infinite alternate; }
  @keyframes floaty { from { transform:translateY(0); } to { transform:translateY(-16px); } }
  .hero-lines path { stroke-dasharray:1700; stroke-dashoffset:1700; animation:drawLine 3.4s ease-out forwards; }
  .hero-lines path:nth-of-type(2) { animation-delay:.55s; }
  .hero-lines path:nth-of-type(3) { animation-delay:1.1s; }
  @keyframes drawLine { to { stroke-dashoffset:0; } }
  .hero-lines circle { transform-box:fill-box; transform-origin:center;
    animation:pulse 2.8s ease-in-out infinite; }
  .hero-lines circle:last-of-type { animation-delay:1.2s; }
  @keyframes pulse { 0%,100% { transform:scale(1); opacity:1; } 50% { transform:scale(1.8); opacity:.5; } }
  @media (prefers-reduced-motion: reduce) {
    .hero.warm, .cta-banner.warm, .hero-lines, .hero-lines path, .hero-lines circle, .hero .glow {
      animation:none; }
    .hero-lines path { stroke-dashoffset:0; }
  }
  .hero.warm .eyebrow { color:#F0A868; }
  .hero.warm h1 em { background:linear-gradient(90deg, #F0A868, #E07B2B);
    -webkit-background-clip:text; background-clip:text; color:transparent; }
  .hero.warm .btn.primary { background:linear-gradient(90deg, #C05C1D, #E08A3C); border:none; }
  .hero.warm .btn.primary:hover { filter:brightness(1.08); }
  .hero.warm .btn.ghost { border-color:#5A4232; color:#E3CDB8; }
  .stats.warm { background:linear-gradient(90deg, #16233A, #3A2415); }
  .stats.warm .v.up { color:#F0A868; }
  .stats.warm .stat { border-inline-start:1px solid rgba(240,168,104,.14); }
  .kicker.warm { color:var(--rust); }
  .steps.warm .step::before { background:linear-gradient(135deg, #C05C1D, #E08A3C); }
  .block.warm-wash { background:linear-gradient(180deg, #FCF2E7, #FFFFFF);
    border-block:1px solid #F2E2D2; }
  .cta-banner.warm { background:linear-gradient(120deg, #2A1508, #7A3D14 62%, #C05C1D 125%); }
  .cta-banner.warm p { color:#E3C8AE; }
  .cta-banner.warm .btn.primary { background:#fff; color:#9A4A16; }
  .cta-banner.warm .btn.primary:hover { background:#FDEFE2; }
  .hero-in { padding:88px 0 96px; position:relative; z-index:1; max-width:680px; }
  .hero .eyebrow { color:#7FD6C9; font-weight:700; font-size:13px; letter-spacing:.14em; text-transform:uppercase; }
  .hero h1 { font-size:clamp(34px, 5.4vw, 56px); line-height:1.1; font-weight:800;
             letter-spacing:-.028em; margin:14px 0 18px; text-wrap:balance; }
  .hero h1 em { font-style:normal; color:#5BC8B8; }
  .hero p.sub { font-size:18px; color:#A9B7C9; max-width:56ch; margin-bottom:30px; }
  .hero-cta { display:flex; gap:12px; flex-wrap:wrap; align-items:center; }
  .hero .fine { font-size:12.5px; color:#7788A0; margin-top:14px; }
  .hero-lines { position:absolute; inset:0; opacity:.5; pointer-events:none; }

  .stats { background:var(--navy2); color:#fff; border-top:1px solid rgba(255,255,255,.06); }
  .stats-in { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); }
  .stat { padding:22px 26px; border-inline-start:1px solid rgba(255,255,255,.07); }
  .stat .v { font-size:27px; font-weight:800; letter-spacing:-.02em; }
  .stat .v.up { color:#5BC8B8; }
  .stat .t { font-size:12.5px; color:#8FA0B5; margin-top:2px; }

  section.block { padding:76px 0; }
  .kicker { color:var(--accent-ink); font-weight:700; font-size:13px; letter-spacing:.12em; text-transform:uppercase; }
  h2.title { font-size:clamp(26px,3.4vw,36px); font-weight:800; letter-spacing:-.022em;
             margin:10px 0 12px; text-wrap:balance; }
  p.lede { color:var(--ink2); font-size:16.5px; max-width:64ch; }
  .cols3 { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; margin-top:38px; }
  .card { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
          padding:26px; box-shadow:var(--shadow); }
  .card .ic { width:44px; height:44px; border-radius:10px; display:flex; align-items:center;
              justify-content:center; margin-bottom:16px; font-size:20px; }
  .card h3 { font-size:17.5px; margin-bottom:8px; }
  .card p { font-size:14.5px; color:var(--ink2); }

  .tablecard { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
               box-shadow:var(--shadow); overflow:hidden; margin-top:30px; }
  .tablecard .thead { display:flex; align-items:center; gap:12px; padding:18px 22px;
                      border-bottom:1px solid var(--line); }
  .tablecard .thead h3 { font-size:16.5px; }
  .tablecard .thead .cnt { font-size:12.5px; font-weight:700; color:var(--accent-ink);
                           background:var(--accent-soft); border-radius:99px; padding:3px 11px; }
  .twrap { overflow-x:auto; }
  table.sig { border-collapse:collapse; width:100%; font-size:13.6px; min-width:840px; }
  table.sig th { text-align:left; font-size:11.5px; color:var(--ink3); font-weight:650;
                 letter-spacing:.04em; text-transform:uppercase; padding:10px 16px;
                 border-bottom:1px solid var(--line); background:var(--bg); white-space:nowrap; }
  table.sig td { padding:11px 16px; border-bottom:1px solid var(--line); white-space:nowrap; }
  table.sig tr:last-child td { border-bottom:none; }
  table.sig.side-brk thead th { background:#FBF2E9; color:#8A5A32; }
  table.sig.side-sup thead th { background:#E7F4F1; color:#256A5F; }
  td.tick { font-weight:800; font-size:14.5px; }
  .pill { font-size:11px; font-weight:700; padding:2px 9px; border-radius:99px; display:inline-block; }
  .pill.brk { background:var(--rust-soft); color:var(--rust); }
  .pill.sup { background:var(--accent-soft); color:var(--accent-ink); }
  .pill.q { background:var(--navy); color:#7FD6C9; }
  .conf-b { display:flex; align-items:center; gap:8px; }
  .conf-b i { display:block; height:6px; border-radius:3px; background:var(--accent); }
  .conf-b b { font-size:13px; }

  tr.locked td { filter:blur(7px); user-select:none; pointer-events:none; }
  body.subbed tr.locked td { filter:none; user-select:auto; pointer-events:auto; }
  .paywall { position:relative; }
  .paywall-overlay { position:absolute; inset:0; display:flex; flex-direction:column; gap:12px;
    align-items:center; justify-content:center; text-align:center;
    background:linear-gradient(180deg, rgba(246,247,249,0) 0%, rgba(246,247,249,.88) 34%, rgba(246,247,249,.97) 100%); }
  body.subbed .paywall-overlay { display:none; }
  .paywall-overlay h4 { font-size:19px; font-weight:800; }
  .paywall-overlay p { font-size:14px; color:var(--ink2); max-width:44ch; }

  .plans { display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:20px; margin-top:40px; }
  .plan { background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:30px;
          box-shadow:var(--shadow); position:relative; display:flex; flex-direction:column; text-align:left; }
  .plan.hot { border:2px solid var(--accent); }
  .plan .flag { position:absolute; top:-13px; inset-inline-start:24px; background:var(--accent);
                color:#fff; font-size:12px; font-weight:800; padding:3px 13px; border-radius:99px; }
  .plan h3 { font-size:17px; }
  .plan .price { font-size:42px; font-weight:800; letter-spacing:-.03em; margin:10px 0 2px; }
  .plan .price span { font-size:15px; font-weight:600; color:var(--ink2); }
  .plan .per { color:var(--ink3); font-size:13px; margin-bottom:20px; }
  .plan ul { list-style:none; padding:0; margin:0 0 26px; display:grid; gap:10px; font-size:14.5px; }
  .plan li { padding-inline-start:26px; position:relative; }
  .plan li::before { content:'✓'; position:absolute; inset-inline-start:0; color:var(--accent); font-weight:800; }
  .plan li.soon { color:var(--ink3); }
  .plan li.soon::before { content:'◷'; color:var(--ink3); }
  .plan .btn { margin-top:auto; text-align:center; }

  .steps { counter-reset:s; display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr));
           gap:18px; margin-top:38px; }
  .step { counter-increment:s; background:var(--surface); border:1px solid var(--line);
          border-radius:var(--radius); padding:26px; box-shadow:var(--shadow); }
  .step::before { content:counter(s); display:flex; width:38px; height:38px; align-items:center;
    justify-content:center; background:var(--navy); color:#fff; font-weight:800; border-radius:10px;
    margin-bottom:14px; font-size:16px; }
  details.faq { background:var(--surface); border:1px solid var(--line); border-radius:10px;
                padding:16px 20px; margin-top:10px; text-align:left; }
  details.faq summary { font-weight:700; cursor:pointer; font-size:15px; }
  details.faq p { margin-top:10px; color:var(--ink2); font-size:14.5px; }
  footer { background:var(--navy); color:#8FA0B5; padding:46px 0 40px; margin-top:80px; font-size:13px; }
  footer .flinks { display:flex; gap:22px; flex-wrap:wrap; margin-bottom:18px; color:#C6D2E0; font-weight:600; }
  footer .disc { max-width:92ch; line-height:1.7; font-size:12px; border-top:1px solid rgba(255,255,255,.08);
                 padding-top:18px; margin-top:18px; }
  .notice { background:var(--rust-soft); border:1px solid var(--rust); color:var(--rust);
            border-radius:10px; padding:12px 18px; font-size:13.5px; font-weight:600; margin-top:26px; }
  .diago { color:var(--accent); font-weight:800; }
  .hero .diago { color:#5BC8B8; }
  .mark { display:inline-block; transform:translateY(-1px); }
  .cta-banner { background:var(--navy); color:#EAF0F7; border-radius:18px; padding:44px 40px;
    display:flex; align-items:center; justify-content:space-between; gap:24px; flex-wrap:wrap;
    box-shadow:var(--shadow); }
  .cta-banner h2 { font-size:clamp(22px,3vw,30px); font-weight:800; letter-spacing:-.02em; max-width:34ch; }
  .cta-banner p { color:#A9B7C9; font-size:14.5px; margin-top:6px; }
  .pain { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:18px; margin-top:38px; }
  .pain .card b.no { color:var(--danger); }
  .view-toggle { display:inline-flex; gap:2px; background:var(--bg); border:1px solid var(--line);
    border-radius:9px; padding:3px; margin-bottom:10px; }
  .view-toggle button { font:inherit; font-size:12.5px; font-weight:700; color:var(--ink2);
    background:transparent; border:none; border-radius:7px; padding:6px 16px; cursor:pointer; }
  .view-toggle button.on { background:var(--surface); color:var(--ink);
    box-shadow:0 1px 3px rgba(13,27,46,.12); }
  .chart-view { display:none; }
  .chart-view.on { display:block; }
  .cap .chart-view.on { display:contents; }
  .chart-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }
  .chart-head .view-toggle { margin-bottom:0; }
  .price-block { margin-left:auto; text-align:right; }
  .pb-price { font-size:30px; font-weight:800; letter-spacing:-.02em; color:var(--ink); }
  .chg-pill { font-size:15px; font-weight:800; padding:4px 12px; border-radius:99px; }
  .chg-pill.up { background:var(--accent-soft); color:var(--accent-ink); }
  .chg-pill.dn { background:#FBE9E9; color:var(--danger); }
  .pb-cap { font-size:11.5px; color:var(--ink3); font-weight:600; }
  .pb-toggle { display:inline-flex; gap:2px; background:var(--bg); border:1px solid var(--line);
               border-radius:8px; padding:2px; }
  .pb-toggle button { font:inherit; font-size:11px; font-weight:800; color:var(--ink2);
    background:transparent; border:none; border-radius:6px; padding:3px 9px; cursor:pointer; }
  .pb-toggle button.on { background:var(--surface); color:var(--ink); box-shadow:0 1px 2px rgba(13,27,46,.12); }
  .tf-badge { font-size:17px; font-weight:800; letter-spacing:.08em; text-transform:uppercase;
    color:var(--navy); background:var(--bg); border:1.5px solid var(--line); border-radius:9px;
    padding:7px 16px; }
  .tlink { border-bottom:1.5px dashed var(--accent); }
  .tlink:hover { color:var(--accent-ink); }

  .heart { font:inherit; background:none; border:none; cursor:pointer; font-size:17px; line-height:1;
           color:var(--ink3); padding:2px 4px; border-radius:6px; transition:transform .12s, color .12s; }
  .heart:hover { transform:scale(1.25); color:#D33A52; }
  .heart.on { color:#D33A52; }
  .heart.big { font-size:27px; padding:4px 8px; align-self:center; }
  td.hcell { width:34px; padding-inline:10px 0 !important; }
  .date-strip { display:flex; gap:6px; overflow-x:auto; padding:4px 2px 12px; margin-top:24px;
                scrollbar-width:thin; }
  .dchip { flex:none; font:inherit; font-size:12.5px; font-weight:700; color:var(--ink2);
           background:var(--surface); border:1px solid var(--line); border-radius:99px;
           padding:6px 14px; cursor:pointer; transition:all .12s; }
  .dchip:hover { border-color:var(--ink3); }
  .dchip.on { background:var(--navy); color:#fff; border-color:var(--navy); }
  .dchip .dow { font-weight:600; color:inherit; opacity:.6; font-size:11px; margin-inline-start:4px; }
  .filter-bar { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
    box-shadow:var(--shadow); padding:16px 18px; margin-bottom:16px; display:flex; flex-wrap:wrap;
    gap:14px 18px; align-items:flex-end; }
  .filter-bar[hidden] { display:none; }
  .filter-bar label { display:flex; flex-direction:column; gap:5px; font-size:11px; font-weight:700;
    color:var(--ink3); text-transform:uppercase; letter-spacing:.05em; }
  .filter-bar input, .filter-bar select { font:inherit; font-size:13.5px; padding:7px 10px;
    border:1px solid var(--line); border-radius:8px; background:var(--bg); color:var(--ink); width:118px; }
  .filter-bar input:focus, .filter-bar select:focus { outline:2px solid var(--accent); border-color:transparent; }
  .filter-bar .fpair { display:flex; gap:6px; align-items:center; }
  .filter-bar .fpair input { width:84px; }
  .filter-bar .btn { padding:8px 16px; font-size:13px; }

  /* ---------- stock detail ---------- */
  .stock-head { display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; margin:44px 0 6px; }
  .stock-head h1 { font-size:34px; font-weight:800; letter-spacing:-.02em; }
  .stock-head .co { color:var(--ink2); font-size:16px; }
  .stock-grid { display:grid; grid-template-columns:320px 1fr; gap:22px; margin-top:22px; align-items:start; }
  @media (max-width:900px) { .stock-grid { grid-template-columns:1fr; } }
  .info-panel { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
                box-shadow:var(--shadow); padding:22px; }
  .info-panel h3 { font-size:13px; color:var(--ink3); text-transform:uppercase; letter-spacing:.06em; margin-bottom:12px; }
  .kv { display:flex; justify-content:space-between; gap:12px; padding:7px 0; border-bottom:1px solid var(--line);
        font-size:13.8px; }
  .kv:last-child { border-bottom:none; }
  .kv b { font-weight:700; }
  .kv span { color:var(--ink2); }
  .about { font-size:13.5px; color:var(--ink2); line-height:1.65; margin-top:14px; }
  .conf-card { border-radius:var(--radius); padding:22px 26px; display:flex; align-items:center; gap:22px;
               box-shadow:var(--shadow); margin-bottom:18px; }
  .conf-card .score { font-size:52px; font-weight:800; letter-spacing:-.03em; line-height:1; white-space:nowrap; flex:none; }
  .conf-card .score small { font-size:20px; font-weight:700; opacity:.75; }
  .conf-card .lbl { font-size:13px; font-weight:700; text-transform:uppercase; letter-spacing:.08em; opacity:.85; }
  .conf-card .sub2 { font-size:13px; opacity:.85; margin-top:3px; }
  .chart-card { background:var(--surface); border:1px solid var(--line); border-radius:var(--radius);
                box-shadow:var(--shadow); padding:20px; }
  .chart-card .cap { display:flex; gap:12px; align-items:center; font-size:12.5px; color:var(--ink3);
                     margin-top:10px; flex-wrap:wrap; }
  .legend-dot { display:inline-block; width:10px; height:10px; border-radius:3px; vertical-align:-1px; }
  @media (max-width:720px) { .nav-links { display:none; } }
"""


LOGO = """<svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
<rect width="26" height="26" rx="6" fill="#0D1B2E"/>
<path d="M4 19 L13 8 L17 12 L22 5" stroke="#5BC8B8" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="22" cy="5" r="2" fill="#5BC8B8"/></svg>"""

JS = """
<script>
function isSub(){try{const t=localStorage.getItem('tl_trial_until');return t&&Date.now()<+t;}catch(e){return false;}}
function applySub(){document.body.classList.toggle('subbed', isSub());}
function startTrial(){try{localStorage.setItem('tl_trial_until', String(Date.now()+7*864e5));}catch(e){}
  applySub(); alert('Your 7-day free trial is active (demo mode). All lists are now unlocked.');}
function endTrial(){try{localStorage.removeItem('tl_trial_until');}catch(e){} applySub();}
function setChartView(v){
  document.querySelectorAll('.chart-view').forEach(d=>d.classList.toggle('on', d.dataset.view===v));
  document.querySelectorAll('.view-toggle button').forEach(b=>b.classList.toggle('on', b.dataset.view===v));
  try{localStorage.setItem('tl_chart_view', v);}catch(e){}}
function setPxPeriod(p){
  const pill=document.getElementById('chg-pill'); if(!pill) return;
  const v=parseFloat(pill.dataset[p]);
  if(isNaN(v)){ pill.textContent='—'; pill.className='chg-pill'; }
  else{ pill.textContent=(v>=0?'+':'')+v.toFixed(2)+'%';
        pill.className='chg-pill '+(v>=0?'up':'dn'); }
  document.querySelectorAll('.pb-toggle button').forEach(b=>b.classList.toggle('on', b.dataset.p===p));
}
document.addEventListener('DOMContentLoaded', ()=>{ if(document.getElementById('chg-pill')) setPxPeriod('d'); });
function getWL(){try{return JSON.parse(localStorage.getItem('tl_wl')||'[]');}catch(e){return [];}}
function saveWL(a){try{localStorage.setItem('tl_wl', JSON.stringify(a));}catch(e){}}
function toggleWatch(t){let a=getWL(); a=a.includes(t)?a.filter(x=>x!==t):a.concat([t]);
  saveWL(a); paintHearts(); if(typeof renderMyWL==='function') renderMyWL();}
function paintHearts(){const a=getWL();
  document.querySelectorAll('.heart').forEach(b=>{const on=a.includes(b.dataset.t);
    b.classList.toggle('on',on); b.textContent=on?'\\u2665':'\\u2661';
    b.title=on?'Remove from my watchlist':'Add to my watchlist';});}
function scoreOf(c){if(c==null||isNaN(c))return null;
  const x=Math.min(1,Math.max(0,(c-35)/35)); return Math.round((6+4*x)*10)/10;}
function scoreColor(s){const l=62-(s-6)/4*38; return 'hsl(158,52%,'+l.toFixed(0)+'%)';}
document.addEventListener('DOMContentLoaded', ()=>{ paintHearts();
  if(typeof renderMyWL==='function') renderMyWL(); });
function runCounter(el){
  const target=parseFloat(el.dataset.count), pre=el.dataset.prefix||'', suf=el.dataset.suffix||'';
  const fmt=v=>pre+Math.round(v).toLocaleString('en-US')+suf;
  if(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches){
    el.textContent=fmt(target); return;}
  const dur=2000; let start=null, done=false;
  const step=ts=>{ if(done) return; if(start===null) start=ts;
    const p=Math.min(1,(ts-start)/dur);
    el.textContent=fmt(target*(1-Math.pow(1-p,4)));
    if(p<1) requestAnimationFrame(step); else done=true; };
  requestAnimationFrame(step);
  setTimeout(()=>{ done=true; el.textContent=fmt(target); }, dur+200);
}
document.addEventListener('DOMContentLoaded', ()=>{
  document.querySelectorAll('[data-count]').forEach(runCounter);
});
document.addEventListener('DOMContentLoaded', ()=>{
  if(document.querySelector('.chart-view')){
    let v='candles'; try{v=localStorage.getItem('tl_chart_view')||'candles';}catch(e){}
    setChartView(v);}});
document.addEventListener('DOMContentLoaded', applySub);
</script>
"""


def nav(active):
    links = [('index.html', 'Home', 'home'), ('breakouts.html', 'Breakout Signals', 'brk'),
             ('supports.html', 'Support Signals', 'sup'), ('watchlist.html', 'Watchlist', 'wl'),
             ('pricing.html', 'Pricing', 'price')]
    a = ''.join(f'<a href="{h}" class="{"on" if k == active else ""}">{t}</a>' for h, t, k in links)
    return (f'<header class="nav"><div class="wrap nav-in">'
            f'<a class="logo" href="index.html">{LOGO}{BRAND}</a>'
            f'<nav class="nav-links">{a}</nav>'
            f'<div class="nav-cta"><span class="sub-badge">Subscriber · demo</span>'
            f'<a class="btn ghost hide-when-subbed" href="pricing.html">Sign in</a>'
            f'<a class="btn primary hide-when-subbed" href="pricing.html">Start free trial</a></div>'
            f'</div></header>')


def footer(stamp):
    return (f'<footer><div class="wrap">'
            f'<div class="flinks"><a href="index.html">{BRAND}</a><a href="breakouts.html">Breakout Signals</a>'
            f'<a href="supports.html">Support Signals</a><a href="watchlist.html">Watchlist</a>'
            f'<a href="pricing.html">Pricing</a></div>'
            f'<div>Market data as of {stamp} · scanning 2,200+ stocks every trading day</div>'
            f'<div class="disc"><b>Disclaimer:</b> All content on this site — including signals, stock lists and '
            f'performance figures — is provided for informational and research purposes only and does not '
            f'constitute investment advice, a recommendation, or an offer to buy or sell any security. '
            f'Performance shown is based on historical simulations; simulated results have inherent limitations '
            f'and past performance is not indicative of future results. Trading securities involves substantial '
            f'risk of loss. Always do your own research and consult a licensed professional.</div>'
            f'</div></footer>')


def page(title, active, stamp, body, desc='', base=''):
    return (f'<!doctype html><html lang="en" dir="ltr"><head><meta charset="utf-8">{base}'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="description" content="{desc}">'
            f'<title>{title}</title><style>{css()}</style></head><body>'
            f'{nav(active)}{body}{footer(stamp)}{JS}</body></html>')


# ---------------------------------------------------------------- data

def load_data():
    meta = json.load(open('dashboard/data/meta.json'))

    def read(name):
        try:
            return pd.read_csv(f'dashboard/data/{name}')
        except Exception:
            return pd.DataFrame()

    frames = []
    for uni, label in (('russell', 'Russell 2000'), ('nasdaq', 'Nasdaq 100'), ('sp500', 'S&P 500')):
        for side in ('upper', 'under'):
            f = read(f'table_{side}_{uni}.csv')
            if len(f):
                f['universe'] = label
                f['side_key'] = side
                frames.append(f)
    cand = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    q_open = read('quality_open.csv')

    hframes = []
    for uni, label in (('russell', 'Russell 2000'), ('nasdaq', 'Nasdaq 100'), ('sp500', 'S&P 500')):
        h = read(f'events_recent_{uni}.csv')
        if len(h):
            h['universe'] = label
            hframes.append(h)
    hist = pd.concat(hframes, ignore_index=True) if hframes else pd.DataFrame()
    if len(hist):
        hist['side_key'] = hist['side'].map({'upper_breakout': 'upper', 'under_touch': 'under'})
        hist = hist[hist['days_since_anchor'] >= 50]
        # under-side history keeps only touches that held (closed above the line);
        # closed_above survives the CSV round-trip as 1.0/0.0
        held = pd.to_numeric(hist['closed_above'], errors='coerce').fillna(0) > 0
        hist = hist[(hist['side_key'] == 'upper') | held]
        hist = hist.reset_index(drop=True)
    return meta, cand, q_open, hist


def history_payload(hist, side):
    """{date: [row-dicts sorted by confidence desc]} for one side, dates desc."""
    if not len(hist):
        return {}
    h = hist[hist['side_key'] == side].copy()
    h = h.sort_values('confidence', ascending=False, na_position='last')
    out = {}
    for d in sorted(h['event_date'].unique(), reverse=True):
        rows = []
        for _, r in h[h['event_date'] == d].iterrows():
            conf = r.get('confidence')
            rows.append({
                't': r['ticker'], 'u': r['universe'],
                'c': round(float(r['close']), 2), 'l': round(float(r['line']), 2),
                'g': round(float(r['gap_vs_line_pct']), 1),
                'a1': str(r['anchor1'])[:10], 'a2': str(r['anchor2'])[:10],
                'dsa': int(r['days_since_anchor']),
                'cf': None if pd.isna(conf) else round(float(conf), 1),
            })
        out[str(d)[:10]] = rows
    return out


def fmt(v, pat='{:.2f}', dash='—'):
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return dash
        return pat.format(float(v))
    except (TypeError, ValueError):
        return dash


def conf_bar(v):
    from product.stock_pages import conf_to_score, score_color
    if v is None or pd.isna(v):
        return '<span class="conf-b"><b>—</b></span>'
    s = conf_to_score(v)
    bg, _ = score_color(s)
    w = 10 + (s - 6) / 4 * 52
    return (f'<span class="conf-b"><i style="width:{w:.0f}px;background:{bg}"></i>'
            f'<b class="num">{s:.1f}<span style="color:var(--ink3);font-weight:600"> /10</span></b></span>')


def row_tint(i, n, side):
    """Row background fading top -> bottom in the table's side hue; the table is
    ranked, so the strongest signal is the most saturated."""
    hue = '192,92,29' if side == 'upper' else '14,147,130'
    a = 0.13 * (1 - i / max(1, n - 1)) if n > 1 else 0.13
    if a < 0.015:
        return ''
    return (f' style="background:linear-gradient(90deg, rgba({hue},{a:.3f}), '
            f'rgba({hue},{a * 0.3:.3f}) 55%, rgba({hue},0))"')


def score_stripe(conf):
    from product.stock_pages import conf_to_score, score_color
    if conf is None or pd.isna(conf):
        return 'var(--line)'
    return score_color(conf_to_score(conf))[0]


def signal_rows(df, side, quality_tickers, locked_after=1):
    rows = []
    n = len(df)
    for i, (_, r) in enumerate(df.iterrows()):
        locked = ' class="locked"' if i >= locked_after else ''
        pill = ('<span class="pill brk">Breakout</span>' if side == 'upper'
                else '<span class="pill sup">Support</span>')
        qbadge = (' <span class="pill q">Quality ✦</span>'
                  if side == 'under' and r['ticker'] in quality_tickers else '')
        dist = -r['gap_vs_line_pct'] if side == 'upper' else r['gap_vs_line_pct']
        rows.append(
            f'<tr{locked}{row_tint(i, n, side)}>'
            f'<td class="hcell" style="box-shadow:inset 3px 0 0 {score_stripe(r.get("confidence"))}">'
            f'<button class="heart" data-t="{r["ticker"]}" '
            f'onclick="toggleWatch(\'{r["ticker"]}\')">♡</button></td>'
            f'<td class="tick"><a class="tlink" href="stock/{r["ticker"]}.html">{r["ticker"]}</a>{qbadge}</td>'
            f'<td>{pill}</td><td>{r["universe"]}</td>'
            f'<td class="num">{fmt(r["close"])}</td>'
            f'<td class="num">{fmt(r["line"])}</td>'
            f'<td class="num">{fmt(dist, "{:+.1f}%")}</td>'
            f'<td class="num">{str(r.get("anchor1", ""))[:10]} → {str(r.get("anchor2", ""))[:10]}</td>'
            f'<td class="num">{int(r["days_since_anchor"])}d</td>'
            f'<td>{conf_bar(r.get("confidence"))}</td></tr>')
    return ''.join(rows)


def date_strip(payload):
    chips = ['<button class="dchip on" onclick="renderDay(\'cur\',this)">Current</button>',
             '<button class="dchip" onclick="showFiltered(this)">⚙ Filtered</button>']
    for d in payload:
        ts = pd.Timestamp(d)
        chips.append(f'<button class="dchip" onclick="renderDay(\'{d}\',this)">'
                     f'{ts.strftime("%b %d")}<span class="dow">{ts.strftime("%a")}</span></button>')
    return '<div class="date-strip">' + ''.join(chips) + '</div>'


def filter_bar(payload, side):
    dates = list(payload)
    dmax, dmin = (dates[0], dates[-1]) if dates else ('', '')
    dist_lbl = 'Max above line %' if side == 'under' else 'Max distance %'
    return f"""
  <div class="filter-bar" id="filter-bar" hidden>
    <label>Index
      <select id="f-uni" onchange="applyFilters()"><option value="">All</option>
      <option>Russell 2000</option><option>Nasdaq 100</option><option>S&amp;P 500</option></select></label>
    <label>From
      <input type="date" id="f-from" value="{dmin}" min="{dmin}" max="{dmax}" onchange="applyFilters()"></label>
    <label>To
      <input type="date" id="f-to" value="{dmax}" min="{dmin}" max="{dmax}" onchange="applyFilters()"></label>
    <label>Min Diago score
      <select id="f-score" onchange="applyFilters()"><option value="">Any</option>
      <option value="6.5">6.5+</option><option value="7">7+</option><option value="7.5">7.5+</option>
      <option value="8">8+</option><option value="8.5">8.5+</option><option value="9">9+</option></select></label>
    <label>Price $
      <span class="fpair"><input type="number" id="f-pmin" placeholder="min" oninput="applyFilters()">–<input
        type="number" id="f-pmax" placeholder="max" oninput="applyFilters()"></span></label>
    <label>{dist_lbl}
      <input type="number" id="f-dist" placeholder="any" step="0.5" oninput="applyFilters()"></label>
    <label>Min line age (days)
      <input type="number" id="f-age" placeholder="any" oninput="applyFilters()"></label>
    <label>Ticker
      <input id="f-tick" placeholder="e.g. AAPL" oninput="applyFilters()" style="text-transform:uppercase"></label>
    <button class="btn ghost" onclick="resetFilters()">Reset</button>
  </div>"""


def history_js(payload, side):
    dist_lbl = 'Above line' if side == 'under' else 'To line'
    filt_head = (f'<th></th><th>Ticker</th><th>Date</th><th>Signal</th><th>Index</th><th>Price</th>'
                 f'<th>Trendline</th><th>{dist_lbl}</th><th>Line anchors</th><th>Line age</th><th>Diago score</th>')
    return f"""
<script>
const HIST = {json.dumps(payload)};
const SIDE = {json.dumps(side)};
const ALL = Object.entries(HIST).flatMap(([d, rows]) => rows.map(r => Object.assign({{}}, r, {{d: d}})));
const FILT_HEAD = {json.dumps(filt_head)};
let ORIG = null;
function saveOrig(){{
  if(ORIG !== null) return;
  ORIG = {{body: document.querySelector('table.sig tbody').innerHTML,
    head: document.querySelector('table.sig thead tr').innerHTML,
    cnt: document.getElementById('tbl-cnt').textContent,
    pw: document.getElementById('pw-count').textContent}};
}}
function rowHtml(r, i, withDate, n){{
  const pill = SIDE==='upper' ? '<span class="pill brk">Breakout</span>'
                              : '<span class="pill sup">Support</span>';
  const s = scoreOf(r.cf);
  const bar = s==null ? '<span class="conf-b"><b>\\u2014</b></span>'
    : '<span class="conf-b"><i style="height:6px;border-radius:3px;display:block;width:'
      +(10+(s-6)/4*52).toFixed(0)+'px;background:'+scoreColor(s)
      +'"></i><b class="num">'+s.toFixed(1)
      +'<span style="color:var(--ink3);font-weight:600"> /10</span></b></span>';
  const dist = SIDE==='upper' ? -r.g : r.g;
  const hue = SIDE==='upper' ? '192,92,29' : '14,147,130';
  const a = n>1 ? 0.13*(1-i/(n-1)) : 0.13;
  const tint = a>=0.015 ? ' style="background:linear-gradient(90deg, rgba('+hue+','+a.toFixed(3)
    +'), rgba('+hue+','+(a*0.3).toFixed(3)+') 55%, rgba('+hue+',0))"' : '';
  const stripe = s==null ? 'var(--line)' : scoreColor(s);
  return '<tr'+(i>=1?' class="locked"':'')+tint+'>'
    +'<td class="hcell" style="box-shadow:inset 3px 0 0 '+stripe
    +'"><button class="heart" data-t="'+r.t+'" onclick="toggleWatch(\\''+r.t+'\\')">\\u2661</button></td>'
    +'<td class="tick"><a class="tlink" href="stock/'+r.t+'.html">'+r.t+'</a></td>'
    +(withDate ? '<td class="num">'+r.d+'</td>' : '')
    +'<td>'+pill+'</td><td>'+r.u+'</td>'
    +'<td class="num">'+r.c.toFixed(2)+'</td><td class="num">'+r.l.toFixed(2)+'</td>'
    +'<td class="num">'+(dist>=0?'+':'')+dist.toFixed(1)+'%</td>'
    +'<td class="num">'+r.a1+' \\u2192 '+r.a2+'</td><td class="num">'+r.dsa+'d</td>'
    +'<td>'+bar+'</td></tr>';
}}
function setChip(btn){{ document.querySelectorAll('.dchip').forEach(b=>b.classList.toggle('on', b===btn)); }}
function renderDay(d, btn){{
  const tb = document.querySelector('table.sig tbody'); if(!tb) return;
  saveOrig(); setChip(btn);
  document.getElementById('filter-bar').hidden = true;
  document.querySelector('table.sig thead tr').innerHTML = ORIG.head;
  if(d === 'cur'){{
    tb.innerHTML = ORIG.body;
    document.getElementById('tbl-cnt').textContent = ORIG.cnt;
    document.getElementById('pw-count').textContent = ORIG.pw;
    syncOverlay(null); paintHearts(); return;
  }}
  const rows = HIST[d] || [];
  tb.innerHTML = rows.length ? rows.map((r,i)=>rowHtml(r,i,false,rows.length)).join('')
  : '<tr><td colspan="10" style="text-align:center;color:var(--ink3);padding:28px">No signals printed on this day</td></tr>';
  document.getElementById('tbl-cnt').textContent = rows.length+' signals \\u00b7 '+d;
  document.getElementById('pw-count').textContent =
    '{ALGO} found '+Math.max(0, rows.length-1)+' more signals on '+d;
  syncOverlay(rows.length);
  paintHearts();
}}
function showFiltered(btn){{
  saveOrig(); setChip(btn);
  document.getElementById('filter-bar').hidden = false;
  applyFilters();
}}
function applyFilters(){{
  const fb = document.getElementById('filter-bar');
  if(fb.hidden) return;
  const v = id => document.getElementById(id).value;
  let rows = ALL.slice();
  const uni = v('f-uni');            if(uni)  rows = rows.filter(r=>r.u===uni);
  const from = v('f-from');          if(from) rows = rows.filter(r=>r.d>=from);
  const to = v('f-to');              if(to)   rows = rows.filter(r=>r.d<=to);
  const sc = parseFloat(v('f-score'));
  if(!isNaN(sc)) rows = rows.filter(r=>{{const s=scoreOf(r.cf); return s!=null && s>=sc;}});
  const pmin = parseFloat(v('f-pmin')); if(!isNaN(pmin)) rows = rows.filter(r=>r.c>=pmin);
  const pmax = parseFloat(v('f-pmax')); if(!isNaN(pmax)) rows = rows.filter(r=>r.c<=pmax);
  const dmax = parseFloat(v('f-dist')); if(!isNaN(dmax)) rows = rows.filter(r=>Math.abs(r.g)<=dmax);
  const age = parseFloat(v('f-age'));   if(!isNaN(age))  rows = rows.filter(r=>r.dsa>=age);
  const tq = v('f-tick').trim().toUpperCase();
  if(tq) rows = rows.filter(r=>r.t.indexOf(tq)===0);
  rows.sort((a,b)=> a.d===b.d ? ((b.cf||0)-(a.cf||0)) : (a.d<b.d ? 1 : -1));
  document.querySelector('table.sig thead tr').innerHTML = FILT_HEAD;
  const tb = document.querySelector('table.sig tbody');
  tb.innerHTML = rows.length ? rows.map((r,i)=>rowHtml(r,i,true,rows.length)).join('')
  : '<tr><td colspan="11" style="text-align:center;color:var(--ink3);padding:28px">No signals match these filters</td></tr>';
  document.getElementById('tbl-cnt').textContent = rows.length+' signals \\u00b7 filtered \\u00b7 6 weeks';
  document.getElementById('pw-count').textContent =
    '{ALGO} found '+Math.max(0, rows.length-1)+' more matching signals';
  syncOverlay(rows.length);
  paintHearts();
}}
function resetFilters(){{
  ['f-uni','f-score','f-pmin','f-pmax','f-dist','f-age','f-tick'].forEach(id=>{{
    document.getElementById(id).value='';}});
  const ds = Object.keys(HIST);
  if(ds.length){{ document.getElementById('f-from').value = ds[ds.length-1];
                  document.getElementById('f-to').value = ds[0]; }}
  applyFilters();
}}
function syncOverlay(n){{
  const ov = document.querySelector('.paywall-overlay'), pw = document.querySelector('.paywall');
  if(!ov || !pw) return;
  const subbed = document.body.classList.contains('subbed');
  ov.style.display = (n !== null && n <= 1) ? 'none' : '';
  pw.style.minHeight = (!subbed && n !== null && n > 1 && n < 5) ? '340px' : '';
}}
</script>"""


def signals_table(df, side, quality_tickers, title, stamp):
    dist_lbl = 'Above line' if side == 'under' else 'To line'
    head = (f'<tr><th></th><th>Ticker</th><th>Signal</th><th>Index</th><th>Price</th><th>Trendline</th>'
            f'<th>{dist_lbl}</th><th>Line anchors</th><th>Line age</th><th>Diago score</th></tr>')
    return (
        f'<div class="tablecard"><div class="thead"><h3>{title}</h3>'
        f'<span class="cnt num" id="tbl-cnt">{len(df)} signals · {stamp}</span></div>'
        f'<div class="paywall"><div class="twrap"><table class="sig side-{"brk" if side == "upper" else "sup"}"><thead>{head}</thead>'
        f'<tbody>{signal_rows(df, side, quality_tickers)}</tbody></table></div>'
        f'<div class="paywall-overlay"><h4 id="pw-count">{ALGO} found {max(0, len(df) - 1)} more signals today</h4>'
        f'<p>Unlock every signal, every score, and {ALGO}\'s tracking wallet — first 7 days free.</p>'
        f'<a class="btn primary big" href="pricing.html">Unlock all signals</a></div></div></div>')


# ---------------------------------------------------------------- pages

def hero_svg():
    return """<svg class="hero-lines" viewBox="0 0 1200 520" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
<defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="0">
<stop offset="0" stop-color="#F0A868" stop-opacity="0"/><stop offset="1" stop-color="#F0A868" stop-opacity=".6"/>
</linearGradient></defs>
<path d="M-50 430 L300 300 L520 360 L820 170 L1250 60" stroke="url(#g1)" stroke-width="2" fill="none"/>
<path d="M-50 480 L260 400 L560 430 L900 300 L1250 220" stroke="#4A3423" stroke-width="1.4" fill="none"/>
<path d="M-50 240 L340 330 L640 260 L980 380 L1250 330" stroke="#4A3423" stroke-width="1.2" fill="none" opacity=".7"/>
<circle cx="820" cy="170" r="4" fill="#F0A868"/><circle cx="300" cy="300" r="3.5" fill="#8A5A32"/>
</svg>"""




def _demo_scene(prefix, cfg, t0, t1):
    """One scene of the looping hero demo. Its internal timeline (0-100) is
    mapped onto [t0, t1]% of the shared 26s loop, so scenes alternate."""
    import math
    candles = cfg['candles']
    W, H, ML, MR, MT, MB = 880, 380, 22, 60, 16, 20
    n = len(candles)
    plot_w, plot_h = W - ML - MR, H - MT - MB
    p_hi, p_lo = cfg['p_hi'], cfg['p_lo']
    line_p = cfg['line_p']
    side = cfg['side']

    def m(p):
        return t0 + p * (t1 - t0) / 100.0

    def X(i):
        return ML + (i + 0.5) * plot_w / n

    def Y(p):
        return MT + (p_hi - p) / (p_hi - p_lo) * plot_h

    lx1, ly1, lx2, ly2 = X(1), Y(line_p(1)), X(21.2), Y(line_p(21.2))
    llen = math.hypot(lx2 - lx1, ly2 - ly1)
    angle = math.degrees(math.atan2(ly2 - ly1, lx2 - lx1))

    UP, DN = '#14B8A2', '#D97B6C'
    LINE, ARROW = cfg['line_color'], '#F0A868'
    cw = plot_w / n * 0.55
    kf, parts = [], []

    def keyframe(name, appear, extra_in='', extra_out=''):
        kf.append(
            f'@keyframes {name} {{ 0%,{m(appear):.2f}% {{opacity:0;{extra_in}}} '
            f'{m(appear + 1.8):.2f}% {{opacity:1;{extra_out}}} {m(94):.2f}% {{opacity:1;{extra_out}}} '
            f'{m(100):.2f}%,100% {{opacity:0;}} }}')

    grid = ''
    for p in (100, 92, 84, 76):
        grid += (f'<line x1="{ML}" x2="{W - MR}" y1="{Y(p):.1f}" y2="{Y(p):.1f}" stroke="#26364E" stroke-width="1"/>'
                 f'<text x="{W - MR + 8}" y="{Y(p) + 4:.1f}" font-size="11" fill="#5C6E88" '
                 f'font-family="system-ui" style="font-variant-numeric:tabular-nums">{p}</text>')
    keyframe(f'{prefix}Grid', 0.5)
    parts.append(f'<g style="animation:{prefix}Grid 26s linear infinite">{grid}'
                 f'<text x="{ML + 2}" y="{MT + 14}" font-size="12" font-weight="700" fill="#8FA0B5" '
                 f'font-family="system-ui" letter-spacing=".08em">{cfg["caption"]}</text></g>')

    appear = {**{i: 3 + i * 2.0 for i in range(20)}, 20: 61, 21: 74, 22: 77, 23: 80, 24: 83}
    for i, (o, h, l, c) in enumerate(candles):
        color = UP if c >= o else DN
        y_top, y_bot = Y(max(o, c)), Y(min(o, c))
        body = (f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{Y(h):.1f}" y2="{Y(l):.1f}" '
                f'stroke="{color}" stroke-width="1.4"/>'
                f'<rect x="{X(i) - cw / 2:.1f}" y="{y_top:.1f}" width="{cw:.1f}" '
                f'height="{max(2.0, y_bot - y_top):.1f}" fill="{color}" rx="1.5"/>')
        if i == 20:
            kf.append(
                f'@keyframes {prefix}Brk {{ 0%,{m(61):.2f}% {{opacity:0; transform:scaleY(.15);}} '
                f'{m(63.5):.2f}% {{opacity:1; transform:scaleY(1.07); filter:drop-shadow(0 0 10px rgba(240,168,104,.95));}} '
                f'{m(65):.2f}% {{transform:scaleY(1);}} '
                f'{m(70):.2f}% {{filter:drop-shadow(0 0 9px rgba(240,168,104,.8));}} '
                f'{m(76):.2f}% {{filter:none;}} {m(94):.2f}% {{opacity:1;}} {m(100):.2f}%,100% {{opacity:0;}} }}')
            parts.append(f'<g style="animation:{prefix}Brk 26s linear infinite;transform-box:fill-box;'
                         f'transform-origin:50% 100%">{body}</g>')
        else:
            keyframe(f'{prefix}C{i}', appear[i], 'transform:translateY(9px);', 'transform:none;')
            parts.append(f'<g style="animation:{prefix}C{i} 26s linear infinite">{body}</g>')

    kf.append(
        f'@keyframes {prefix}Line {{ 0%,{m(46):.2f}% {{opacity:1; stroke-dashoffset:{llen:.0f};}} '
        f'{m(57):.2f}% {{stroke-dashoffset:0;}} {m(94):.2f}% {{opacity:1; stroke-dashoffset:0;}} '
        f'{m(100):.2f}%,100% {{opacity:0; stroke-dashoffset:0;}} }}')
    parts.append(f'<line x1="{lx1:.1f}" y1="{ly1:.1f}" x2="{lx2:.1f}" y2="{ly2:.1f}" stroke="{LINE}" '
                 f'stroke-width="2.4" stroke-dasharray="{llen:.0f}" '
                 f'style="animation:{prefix}Line 26s linear infinite"/>')
    for nm, i, pct in ((f'{prefix}D1', 1, 46.5), (f'{prefix}D2', 11, 51.5)):
        keyframe(nm, pct, 'transform:scale(.3);', 'transform:scale(1);')
        parts.append(f'<g style="animation:{nm} 26s linear infinite;transform-box:fill-box;'
                     f'transform-origin:center"><circle cx="{X(i):.1f}" cy="{Y(line_p(i)):.1f}" r="5.5" '
                     f'fill="{LINE}" stroke="#0D1B2E" stroke-width="2"/></g>')

    lbl_dy = -12 if side == 'upper' else 20
    lbl_x, lbl_y = X(5), Y(line_p(5)) + lbl_dy
    keyframe(f'{prefix}Lbl', 57)
    parts.append(f'<text x="{lbl_x:.1f}" y="{lbl_y:.1f}" font-size="11.5" font-weight="700" '
                 f'fill="{LINE}" font-family="system-ui" transform="rotate({angle:.1f} {lbl_x:.1f} {lbl_y:.1f})" '
                 f'style="animation:{prefix}Lbl 26s linear infinite">{cfg["label"]}</text>')

    ax = X(20)
    tip_y = Y(cfg['arrow_p']) - 26 if side == 'upper' else Y(cfg['arrow_p']) + 12
    arrow = f'<path d="M{ax:.1f} {tip_y:.1f} l-9 12 h5.5 v10 h7 v-10 h5.5 z" fill="{ARROW}"/>'
    kf.append(f'@keyframes {prefix}Arr {{ 0%,{m(63.5):.2f}% {{opacity:0; transform:translateY(20px);}} '
              f'{m(66.5):.2f}% {{opacity:1; transform:none;}} {m(94):.2f}% {{opacity:1;}} '
              f'{m(100):.2f}%,100% {{opacity:0;}} }}')
    parts.append(f'<g style="animation:{prefix}Arr 26s linear infinite">{arrow}</g>')

    tx, ty = W - MR - 268, MT + 26
    toast = (
        f'<rect x="{tx}" y="{ty}" width="252" height="64" rx="12" fill="#FFFFFF"/>'
        f'<text x="{tx + 16}" y="{ty + 26}" font-size="13.5" font-weight="800" fill="#0F1726" '
        f'font-family="system-ui"><tspan fill="{LINE}">◢</tspan>  Diago Alert · just now</text>'
        f'<text x="{tx + 16}" y="{ty + 47}" font-size="12.5" font-weight="600" fill="#49556A" '
        f'font-family="system-ui">{cfg["toast"]}</text>'
        f'<rect x="{tx + 186}" y="{ty + 34}" width="52" height="19" rx="9.5" fill="hsl(158,52%,32%)"/>'
        f'<text x="{tx + 212}" y="{ty + 47.5}" font-size="11" font-weight="800" fill="#fff" '
        f'font-family="system-ui" text-anchor="middle">{cfg["score"]}</text>')
    kf.append(f'@keyframes {prefix}Toast {{ 0%,{m(68):.2f}% {{opacity:0; transform:translateX(26px);}} '
              f'{m(70.5):.2f}% {{opacity:1; transform:none;}} {m(94):.2f}% {{opacity:1;}} '
              f'{m(100):.2f}%,100% {{opacity:0;}} }}')
    parts.append(f'<g style="animation:{prefix}Toast 26s linear infinite;'
                 f'filter:drop-shadow(0 6px 18px rgba(0,0,0,.35))">{toast}</g>')

    svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;display:block" role="img" '
           f'aria-label="{cfg["aria"]}">' + ''.join(parts) + '</svg>')
    return kf, svg


def hero_demo():
    """Two alternating animated scenes on one 26s loop: a resistance breakout,
    then a support bounce — each: chart draws, diagonal forms, event fires,
    arrow + Diago alert pop."""
    breakout = {
        'side': 'upper', 'p_hi': 103.0, 'p_lo': 74.0,
        'line_p': lambda i: 100 - 1.1 * (i - 1),
        'line_color': '#E08A3C',
        'caption': 'TICKR · RESISTANCE BREAKOUT · SIMULATED',
        'label': 'resistance diagonal',
        'toast': 'TICKR broke its diagonal', 'score': '8.4/10', 'arrow_p': 86.2,
        'aria': 'Animated illustration: a resistance diagonal forms, price breaks out, Diago sends an alert',
        'candles': [
            (97, 99.5, 94, 95), (95, 100, 93, 94), (94, 96, 90, 91), (91, 94, 88, 89),
            (89, 93.5, 87, 92), (92, 95.5, 90, 90.5), (90.5, 94.4, 88, 89), (89, 91, 85, 86),
            (86, 90, 84, 88.5), (88.5, 91.2, 86, 87), (87, 89, 83, 84), (84, 89, 82, 83),
            (83, 86, 80, 81), (81, 84, 78, 79.5), (79.5, 83, 77.5, 82), (82, 84.6, 80, 81),
            (81, 83, 78.5, 79.5), (79.5, 82.4, 78, 81.5), (79, 80.8, 77.5, 79.8), (79.8, 80.1, 78.5, 79.9),
            (79.9, 85, 79.5, 84),
            (84, 87, 82.5, 86), (86, 90, 85, 89), (89, 91.5, 87, 88), (88, 94, 87.5, 93),
        ],
    }
    support = {
        # gentler diagonal (0.55/bar); price rallies far above it, then plunges
        # back to the same line and bounces — two touches, one dramatic retest
        'side': 'under', 'p_hi': 102.0, 'p_lo': 72.0,
        'line_p': lambda i: 76 + 0.55 * (i - 1),
        'line_color': '#1FCFAF',
        'caption': 'TICKR · SUPPORT BOUNCE · SIMULATED',
        'label': 'support diagonal',
        'toast': 'TICKR held its support line', 'score': '8.1/10', 'arrow_p': 85.5,
        'aria': 'Animated illustration: a support diagonal forms, price bounces off it, Diago sends an alert',
        'candles': [
            (77.5, 79, 75.6, 78), (78, 79.5, 76.0, 78.5), (78.5, 81.5, 77.5, 81), (81, 84, 80, 83.5),
            (83.5, 86.5, 82.5, 86), (86, 88.5, 85, 87.5), (87.5, 88, 84.5, 85), (85, 86, 83, 83.8),
            (83.8, 84.5, 82, 82.6), (82.6, 83.5, 81.8, 82.2), (82.2, 83, 81.7, 82), (82, 83.5, 81.5, 83),
            (83, 86, 82.5, 85.5), (85.5, 88.5, 84.5, 88), (88, 91, 87, 90.5), (90.5, 93.5, 89.5, 93),
            (93, 96, 92, 95.5), (95.5, 97.5, 94.5, 96.5), (96.5, 97, 92.5, 93), (93, 93.5, 88.5, 89),
            (89, 92.5, 86.5, 92),
            (92, 94.5, 91, 94), (94, 96.5, 93, 96), (96, 97, 94.5, 95), (95, 99, 94.5, 98.5),
        ],
    }
    kfA, svgA = _demo_scene('dcA', breakout, 0, 50)
    kfB, svgB = _demo_scene('dcB', support, 50, 100)
    css = '\n'.join(kfA + kfB) + """
  .demo-card { background:linear-gradient(135deg, #0D1B2E 0%, #1C2233 55%, #241A1B 100%);
    border-radius:18px; padding:18px 16px 12px; margin-top:28px;
    box-shadow:0 18px 50px -18px rgba(13,27,46,.45); }
  .demo-stack { display:grid; }
  .demo-stack svg { grid-area:1/1; }
  @media (prefers-reduced-motion: reduce) {
    .demo-card svg * { animation:none !important; opacity:1 !important;
      transform:none !important; stroke-dashoffset:0 !important; }
    .demo-stack svg:last-child { display:none; }
  }"""
    return f"""
<section class="block" style="padding:64px 0"><div class="wrap">
  <div class="kicker warm">Watch it happen</div>
  <h2 class="title">A diagonal breaks — or holds. {ALGO} alerts you.</h2>
  <div class="demo-card"><div class="demo-stack">{svgA}{svgB}</div></div>
</div></section>
<style>{css}</style>"""


def build_index(meta, cand, stamp):
    n_brk = int((cand['side_key'] == 'upper').sum())
    n_sup = int((cand['side_key'] == 'under').sum())
    n_all = n_brk + n_sup
    q = meta.get('quality', {})
    # the one free signal of the day, as a teaser card
    ev = cand[(cand['status'] != 'APPROACHING') & cand['confidence'].notna()]
    top = ev.sort_values('confidence', ascending=False).iloc[0] if len(ev) else None
    teaser = ''
    if top is not None:
        side = 'Breakout' if top['side_key'] == 'upper' else 'Support bounce'
        pill = 'brk' if top['side_key'] == 'upper' else 'sup'
        teaser = f"""
      <a class="card" href="stock/{top['ticker']}.html" style="display:block;border:2px solid var(--rust)">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
          <span class="pill {pill}">{side}</span>
          <span style="font-size:12px;color:var(--ink3)">Today's free signal · {stamp}</span></div>
        <h3 style="font-size:24px">{top['ticker']} <span style="color:var(--ink2);font-weight:600;font-size:15px">${top['close']:,.2f}</span></h3>
        <p style="margin-top:6px">{ALGO} score <b class="num" style="color:var(--rust)">{6 + 4 * min(1, max(0, (top['confidence'] - 35) / 35)):.1f} / 10</b> · full analysis →</p>
      </a>"""
    body = f"""
<div class="hero warm"><div class="wrap"><div class="hero-in">
  <div class="eyebrow"><span class="mark">{ALGO_MARK}</span> Meet {ALGO} — the diagonal-hunting engine</div>
  <h1>The market leaves clues in its diagonals.<br><em>{ALGO} finds every one. Daily.</em></h1>
  <p class="sub">Every night {ALGO} maps the trendlines of <b>2,259 U.S. stocks</b> and scores every
  breakout and support bounce. You wake up to a ranked shortlist — not 2,259 charts.</p>
  <div class="hero-cta">
    <a class="btn primary big" href="pricing.html">Get {ALGO}'s full list — 7 days free</a>
    <a class="btn ghost big" style="background:transparent;color:#C6D2E0;border-color:#31465F" href="breakouts.html">See today's free signal</a>
  </div>
  <div class="fine">No credit card · 2-minute start · cancel anytime</div>
</div></div><div class="glow g1"></div><div class="glow g2"></div>{hero_svg()}</div>

<div class="stats warm"><div class="wrap stats-in">
  <div class="stat"><div class="v up num" data-count="{q.get('ret_pct', 0):.0f}" data-prefix="+" data-suffix="%">+{q.get('ret_pct', 0):.0f}%</div><div class="t">{ALGO}'s tracked wallet since Jan 2024 (simulated)</div></div>
  <div class="stat"><div class="v num" data-count="{n_all}">{n_all}</div><div class="t">Signals {ALGO} is flagging right now</div></div>
  <div class="stat"><div class="v num" data-count="2259">2,259</div><div class="t">Stocks scanned — every single day</div></div>
  <div class="stat"><div class="v num" data-count="72000" data-suffix="+">72,000+</div><div class="t">Historical setups behind every score</div></div>
</div></div>
\n{hero_demo()}\n
<section class="block"><div class="wrap">
  <div class="kicker warm">The problem</div>
  <h2 class="title">The best setups don't wait for you to find them</h2>
  <div class="pain">
    <div class="card"><b class="no">✗ You can't watch 2,259 charts.</b>
      <p>The week's best setup is usually on a chart you never opened.</p></div>
    <div class="card"><b class="no">✗ Late signals are dead signals.</b>
      <p>Once it's trending on social media, the entry is gone.</p></div>
    <div class="card"><b class="no">✗ Gut feeling doesn't compound.</b>
      <p>Without a measured probability, every trade is a coin flip.</p></div>
  </div>
</div></section>

<section class="block" style="padding-top:0"><div class="wrap">
  <div class="kicker warm">Meet {ALGO} {ALGO_MARK}</div>
  <h2 class="title">One engine. Three obsessions.</h2>
  <p class="lede">Named for the diagonals it hunts. Three things, relentlessly:</p>
  <div class="steps warm">
    <div class="step"><h3>Maps every diagonal</h3><p style="color:var(--ink2);font-size:14.5px">
      Resistance and support lines for Russell 2000, Nasdaq 100 and S&amp;P 500 — redrawn nightly.</p></div>
    <div class="step"><h3>Catches the moment</h3><p style="color:var(--ink2);font-size:14.5px">
      Every breakout and support touch, flagged the day it prints.</p></div>
    <div class="step"><h3>Tells you the odds</h3><p style="color:var(--ink2);font-size:14.5px">
      A 6–10 score, calibrated on 72,000+ historical setups.</p></div>
  </div>
</div></section>

<section class="block warm-wash"><div class="wrap">
  <div class="kicker warm">Proof, live</div>
  <h2 class="title">{ALGO} flagged {n_all} stocks today. Here's one — free.</h2>
  <p class="lede">The top signal is free, every day. Subscribers see all {n_all}.</p>
  <div style="display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));margin-top:26px">
    {teaser}
    <a class="card" href="breakouts.html" style="display:block"><h3>📈 Breakout signals ({n_brk})</h3>
      <p>Stocks clearing their resistance diagonal — ranked by {ALGO}'s score →</p></a>
    <a class="card" href="supports.html" style="display:block"><h3>🛡️ Support signals ({n_sup})</h3>
      <p>Stocks bouncing off rising support — {ALGO}'s strongest setup →</p></a>
  </div>
</div></section>

<section class="block"><div class="wrap">
  <div class="kicker warm">Radical transparency</div>
  <h2 class="title">We publish {ALGO}'s losses, too</h2>
  <p class="lede">{ALGO}'s tracking wallet records <b>every</b> signal — wins, losses, drawdowns —
  and never deletes a trade. A track record, not a highlight reel.</p>
</div></section>

<section class="block" style="padding-top:0"><div class="wrap">
  <div class="cta-banner warm">
    <div><h2>Tomorrow at dawn, {ALGO} will scan 2,259 stocks.<br>Be the first to see what it found.</h2>
    <p>7 days free · then $5/month or $45/year · cancel in one click</p></div>
    <a class="btn primary big" href="pricing.html">Start free — see everything</a>
  </div>
</div></section>
"""
    return page(f'{BRAND} — {ALGO}, the Diagonal-Hunting Signal Engine', 'home', stamp, body,
                f'{ALGO} scans 2,259 stocks daily, flags every breakout and support bounce, and scores each 6-10 on calibrated historical odds.')


def build_signals_page(kind, meta, cand, q_open, hist, stamp):
    side = 'upper' if kind == 'brk' else 'under'
    df = cand[(cand['side_key'] == side) & (cand['status'] != 'APPROACHING')].copy()
    df = df.sort_values(['confidence'], ascending=False, na_position='last')
    qt = set(q_open['ticker']) if len(q_open) else set()
    payload = history_payload(hist, side)
    if kind == 'brk':
        title = 'Breakout Signals'
        sub = ('Stocks that closed above their resistance diagonal in the last few sessions. '
               f'{ALGO} ranks them by calibrated confidence — its research found repeat breakouts of a mature line to be the most reliable setup on this side.')
    else:
        title = 'Support Signals'
        sub = ('Stocks that touched their support diagonal and held above it — the strongest-performing setup '
               f'in {ALGO}\'s backtests. The ✦ badge marks signals that also pass its stricter Quality gate.')
    body = f"""
<section class="block"><div class="wrap">
  <div class="kicker">{stamp} · refreshed every trading morning</div>
  <h2 class="title">{title}</h2>
  <p class="lede">{sub}</p>
  <p style="font-size:13px;color:var(--ink3);margin-top:20px;font-weight:600">Browse by the day {ALGO}
  flagged the signal — or hit ⚙ Filtered to search all 6 weeks by index, score, price and more.
  Tap ♡ on any ticker to add it to your watchlist.</p>
  {date_strip(payload)}
  {filter_bar(payload, side)}
  {signals_table(df, side, qt, title, stamp)}
  <div class="notice">⚠️ Signals are algorithmic output, not investment advice. Confidence is a calibrated
  statistical probability — not a guarantee.</div>
</div></section>
{history_js(payload, side)}
"""
    return page(f'{title} — {BRAND}', kind, stamp, body)


def build_watchlist(meta, cand, hist, stamp):
    df = cand[cand['status'] == 'APPROACHING'].copy()
    df['absdist'] = df['gap_vs_line_pct'].abs()
    df = df.sort_values('absdist')
    rows = []
    for i, (_, r) in enumerate(df.iterrows()):
        locked = ' class="locked"' if i >= 1 else ''
        side_pill = ('<span class="pill brk">Nearing breakout</span>' if r['side_key'] == 'upper'
                     else '<span class="pill sup">Nearing support</span>')
        hue = '192,92,29' if r['side_key'] == 'upper' else '14,147,130'
        a = 0.13 * (1 - i / max(1, len(df) - 1)) if len(df) > 1 else 0.13
        tint = (f' style="background:linear-gradient(90deg, rgba({hue},{a:.3f}), '
                f'rgba({hue},{a * 0.3:.3f}) 55%, rgba({hue},0))"') if a >= 0.015 else ''
        rows.append(f'<tr{locked}{tint}><td class="hcell" style="box-shadow:inset 3px 0 0 rgba({hue},.55)">'
                    f'<button class="heart" data-t="{r["ticker"]}" '
                    f'onclick="toggleWatch(\'{r["ticker"]}\')">♡</button></td>'
                    f'<td class="tick"><a class="tlink" href="stock/{r["ticker"]}.html">{r["ticker"]}</a></td><td>{side_pill}</td>'
                    f'<td>{r["universe"]}</td><td class="num">{fmt(r["close"])}</td>'
                    f'<td class="num">{fmt(r["line"])}</td>'
                    f'<td class="num">{fmt(abs(r["gap_vs_line_pct"]), "{:.1f}%")}</td>'
                    f'<td class="num">{int(r["days_since_anchor"])}d</td></tr>')

    # ticker -> latest known state, for rendering the user's saved list
    tickmap = {}
    if len(hist):
        h = hist.sort_values('event_date')
        for _, r in h.iterrows():
            tickmap[r['ticker']] = {'p': round(float(r['close']), 2),
                                    'k': 'B' if r['side_key'] == 'upper' else 'S',
                                    'd': str(r['event_date'])[:10]}
    for _, r in cand.iterrows():
        k = ('AB' if r['side_key'] == 'upper' else 'AS') if r['status'] == 'APPROACHING' \
            else ('B' if r['side_key'] == 'upper' else 'S')
        tickmap[r['ticker']] = {'p': round(float(r['close']), 2), 'k': k, 'd': stamp}

    my_wl = f"""
  <div class="tablecard" style="margin-top:26px"><div class="thead"><h3>♥ My watchlist</h3>
    <span class="cnt num" id="mywl-cnt"></span></div>
  <div class="twrap"><table class="sig" style="min-width:520px"><thead>
  <tr><th></th><th>Ticker</th><th>Latest signal</th><th>Last price</th></tr>
  </thead><tbody id="mywl-body"></tbody></table></div></div>
<script>
const TICKMAP = {json.dumps(tickmap)};
function renderMyWL(){{
  const el = document.getElementById('mywl-body'); if(!el) return;
  const a = getWL();
  document.getElementById('mywl-cnt').textContent = a.length + ' saved';
  if(!a.length){{
    el.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--ink3);padding:24px">'
      +'Tap the \\u2661 next to any ticker \\u2014 on any page \\u2014 to save it here. Stored on this device.</td></tr>';
    return;
  }}
  const L = {{B:'<span class="pill brk">Breakout</span>', S:'<span class="pill sup">Support</span>',
             AB:'<span class="pill brk">Nearing breakout</span>', AS:'<span class="pill sup">Nearing support</span>'}};
  el.innerHTML = a.map(t=>{{
    const m = TICKMAP[t] || {{}};
    return '<tr><td class="hcell"><button class="heart on" data-t="'+t+'" onclick="toggleWatch(\\''+t+'\\')">\\u2665</button></td>'
      +'<td class="tick"><a class="tlink" href="stock/'+t+'.html">'+t+'</a></td>'
      +'<td>'+(L[m.k]||'<span style="color:var(--ink3)">\\u2014</span>')
      +(m.d?' <span style="color:var(--ink3);font-size:11px" class="num">'+m.d+'</span>':'')+'</td>'
      +'<td class="num">'+(m.p!=null?m.p.toFixed(2):'\\u2014')+'</td></tr>';
  }}).join('');
  paintHearts();
}}
</script>"""
    body = f"""
<section class="block"><div class="wrap">
  <div class="kicker">{stamp}</div>
  <h2 class="title">Watchlist — closest to the line</h2>
  <p class="lede">Your saved tickers, plus the stocks within 3% of their trendline — the most likely
  candidates to print a signal in the coming sessions. Subscribers get notified the moment it happens.</p>
  {my_wl}
  <div class="tablecard" style="margin-top:26px"><div class="thead"><h3>Approaching the line</h3><span class="cnt num">{len(df)} stocks</span></div>
  <div class="paywall"><div class="twrap"><table class="sig"><thead>
  <tr><th></th><th>Ticker</th><th>Status</th><th>Index</th><th>Price</th><th>Trendline</th><th>Distance</th><th>Line age</th></tr>
  </thead><tbody>{''.join(rows)}</tbody></table></div>
  <div class="paywall-overlay"><h4>The full watchlist is for subscribers</h4>
  <p>Know which stocks are about to touch their line — before it happens. First 7 days free.</p>
  <a class="btn primary big" href="pricing.html">Unlock the watchlist</a></div></div></div>
</div></section>
"""
    return page(f'Watchlist — {BRAND}', 'wl', stamp, body)


def build_pricing(meta, stamp):
    body = f"""
<section class="block"><div class="wrap" style="text-align:center">
  <div class="kicker">Simple pricing</div>
  <h2 class="title">First 7 days free. Always.</h2>
  <p class="lede" style="margin:0 auto">No credit card for the trial, no fine print.
  If the platform isn't worth $5 to you — don't pay.</p>
  <div class="plans">
    <div class="plan">
      <h3>Free</h3>
      <div class="price">$0</div><div class="per">forever</div>
      <ul><li>One unlocked signal per list, every day</li><li>Methodology pages</li><li>Cumulative performance stats</li></ul>
      <a class="btn ghost" href="breakouts.html">See today's signals</a>
    </div>
    <div class="plan hot">
      <span class="flag">Most popular</span>
      <h3>Monthly</h3>
      <div class="price">$5<span> / month</span></div><div class="per">after your 7-day free trial</div>
      <ul>
        <li>Every breakout & support signal, unblurred</li>
        <li>Confidence scores & quality badges on all signals</li>
        <li>Full watchlist — know before the signal prints</li>
        <li>Tracking wallet — transparent record of every call</li>
        <li class="soon">WhatsApp alerts from Diago — coming soon</li>
      </ul>
      <button class="btn primary" onclick="startTrial()">Start 7-day free trial</button>
    </div>
    <div class="plan">
      <h3>Annual</h3>
      <div class="price">$45<span> / year</span></div><div class="per">$3.75/month · save 25%</div>
      <ul>
        <li>Everything in Monthly</li>
        <li>Price locked for a full year</li>
        <li>Priority access to new features</li>
        <li class="soon">WhatsApp alerts from Diago — coming soon</li>
      </ul>
      <button class="btn ghost" onclick="startTrial()">Start 7-day free trial</button>
    </div>
  </div>
  <p style="color:var(--ink3);font-size:12.5px;margin-top:22px">Secure checkout launching soon · buttons currently
  enable a full 7-day demo mode · <a href="#" onclick="endTrial();return false" style="text-decoration:underline">end demo</a></p>

  <div style="max-width:720px;margin:70px auto 0">
    <h2 class="title" style="font-size:24px">Frequently asked questions</h2>
    <details class="faq"><summary>Who — or what — is Diago?</summary>
      <p>Diago is our signal engine, named after the diagonals it hunts. It's not a chatbot and it has
      no opinions — it's a quantitative system that maps trendlines, detects events and scores them
      statistically. We gave it a name because you'll be hearing from it every morning.</p></details>
    <details class="faq"><summary>What exactly is a diagonal trendline?</summary>
      <p>A line connecting declining highs (resistance) or rising lows (support) on a logarithmic scale.
      Breaking such a line — especially a mature one — is one of the most established technical signals.
      Our engine simply finds and ranks them across thousands of stocks simultaneously, which is
      impossible to do by hand.</p></details>
    <details class="faq"><summary>What does "confidence" mean?</summary>
      <p>A calibrated probability that the signal resolves profitably over a 20-trading-day horizon,
      based on tens of thousands of historical signals. Calibrated means that when we say 60%,
      similar setups actually worked about 60% of the time historically. It's statistics — not a promise.</p></details>
    <details class="faq"><summary>Are the performance numbers real?</summary>
      <p>They come from a precise simulation of the system's rules on real market data, including
      out-of-sample periods the model never saw in training. We show losses and drawdowns, not just
      the wins. Still — past performance never guarantees future results.</p></details>
    <details class="faq"><summary>Can I cancel anytime?</summary>
      <p>Yes, in one click, and you keep access until the end of the period you paid for.</p></details>
  </div>
</div></section>
"""
    return page(f'Pricing — {BRAND}', 'price', stamp, body)


def main():
    meta, cand, q_open, hist = load_data()
    stamp = meta['last_date']
    os.makedirs(OUT, exist_ok=True)
    pages = {
        'index.html': build_index(meta, cand, stamp),
        'breakouts.html': build_signals_page('brk', meta, cand, q_open, hist, stamp),
        'supports.html': build_signals_page('sup', meta, cand, q_open, hist, stamp),
        'watchlist.html': build_watchlist(meta, cand, hist, stamp),
        'pricing.html': build_pricing(meta, stamp),
    }
    for name, html in pages.items():
        with open(f'{OUT}/{name}', 'w', encoding='utf-8') as f:
            f.write(html)
    print(f"product site built (EN): {len(pages)} pages -> {OUT}/ (data as of {stamp})")

    # stock pages for every current candidate PLUS every ticker that appears in
    # the 6-week signal history, so historical rows always link somewhere
    union = cand
    if len(hist):
        extra = (hist.sort_values('event_date')
                     .drop_duplicates('ticker', keep='last'))
        extra = extra[~extra['ticker'].isin(set(cand['ticker']))]
        union = pd.concat([cand, extra], ignore_index=True)
    from product import stock_pages
    stock_pages.build_all(
        union,
        lambda title, active, s, body, desc='': page(title, active, s, body, desc, base='<base href="../">'),
        stamp, OUT)


if __name__ == '__main__':
    main()
