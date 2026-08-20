"""
Diago promo film generator -> product/promo/film.html

A deterministic 88s animated film (1280x720) on ONE master CSS timeline:
every element animates via its own @keyframes with absolute-time percentages,
`animation: <name> 88s linear 1 both`. No JS. That makes it freezable at any
timestamp (animation-delay:-Ts + paused) so render_film.py can rasterize it
frame-by-frame into an MP4, and narration can be timed to exact seconds.

Scenes:
  S1  0-10   Hook: a diagonal draws, headline.
  S2 10-22   Problem: wall of mini-charts, "2,259 stocks", "you can't watch them all".
  S3 22-41   Breakout demo (candles -> line -> breakout -> arrow -> alert).
  S4 41-56   Support demo (rally -> plunge to the line -> bounce -> alert).
  S5 56-72   Proof: score card, stat tiles, losers published.
  S6 72-88   CTA: brand, offer, disclaimer.

Usage: python3 -m product.promo.make_film
"""
import math
import os
import random

D = 88.0                       # master duration, seconds
W, H = 1280, 720
NAVY, INK2 = '#0D1B2E', '#A9B7C9'
TEAL, TEAL_L = '#0E9382', '#5BC8B8'
RUST, AMBER = '#C05C1D', '#F0A868'
UP, DN = '#14B8A2', '#D97B6C'

_kf = []


def pct(t):
    return f'{t / D * 100:.3f}%'


def kf(name, stops):
    """stops: list of (time_seconds, css) — compiled to absolute percentages."""
    body = ' '.join(f'{pct(t)} {{{css}}}' for t, css in stops)
    _kf.append(f'@keyframes {name} {{ {body} }}')
    return f'animation:{name} {D}s linear 1 both;'


def fade_in_out(name, t_in, t_out, dur_in=0.8, dur_out=1.0, base='', shown=''):
    return kf(name, [
        (0, f'opacity:0;{base}'),
        (t_in, f'opacity:0;{base}'),
        (t_in + dur_in, f'opacity:1;{shown}'),
        (t_out, f'opacity:1;{shown}'),
        (t_out + dur_out, 'opacity:0;'),
        (D, 'opacity:0;'),
    ])


# ---------------------------------------------------------------- candlestick scene builder

def candle_chart(prefix, candles, line_p, side, t0, geom, alert_text, score,
                 caption, t_line, t_break, t_alert, stagger=0.22):
    """Build one signal-story chart. Times are absolute (seconds on the master
    timeline). Returns SVG string. candles[20] is the event candle."""
    x0, y0, cw_, ch_ = geom            # chart box inside the stage svg
    n = len(candles)
    p_hi = max(h for _, h, _, _ in candles) * 1.04
    p_lo = min(l for _, _, l, _ in candles) * 0.96

    def X(i):
        return x0 + (i + 0.5) * cw_ / n

    def Y(p):
        return y0 + (p_hi - p) / (p_hi - p_lo) * ch_

    lx1, ly1 = X(1), Y(line_p(1))
    lx2, ly2 = X(21.4), Y(line_p(21.4))
    llen = math.hypot(lx2 - lx1, ly2 - ly1)
    line_color = RUST if side == 'upper' else '#1FCFAF'
    parts = []

    # caption chip
    a = kf(f'{prefix}cap', [(0, 'opacity:0;'), (t0, 'opacity:0;'), (t0 + 0.6, 'opacity:1;'),
                            (t0 + 99 if t0 + 99 < D else D - 0.1, 'opacity:1;')][:3] + [(D, 'opacity:1;')])
    parts.append(f'<text x="{x0}" y="{y0 - 18}" font-size="17" font-weight="700" fill="#8FA0B5" '
                 f'font-family="system-ui" letter-spacing=".1em" style="{a}">{caption}</text>')

    bw = cw_ / n * 0.55
    for i, (o, hh, ll, c) in enumerate(candles):
        color = UP if c >= o else DN
        y_top, y_bot = Y(max(o, c)), Y(min(o, c))
        body = (f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{Y(hh):.1f}" y2="{Y(ll):.1f}" '
                f'stroke="{color}" stroke-width="2"/>'
                f'<rect x="{X(i) - bw / 2:.1f}" y="{y_top:.1f}" width="{bw:.1f}" '
                f'height="{max(2.5, y_bot - y_top):.1f}" fill="{color}" rx="2"/>')
        if i == 20:   # the event candle: grows + glows at t_break
            anim = kf(f'{prefix}c{i}', [
                (0, 'opacity:0; transform:scaleY(.15);'),
                (t_break, 'opacity:0; transform:scaleY(.15);'),
                (t_break + 0.5, f'opacity:1; transform:scaleY(1.08); filter:drop-shadow(0 0 14px {AMBER});'),
                (t_break + 0.8, 'transform:scaleY(1);'),
                (t_break + 2.6, f'filter:drop-shadow(0 0 10px {AMBER});'),
                (t_break + 4.0, 'filter:none;'),
                (D, 'opacity:1;'),
            ])
            parts.append(f'<g style="{anim}transform-box:fill-box;transform-origin:50% 100%">{body}</g>')
        else:
            ta = t0 + 0.8 + (i if i < 20 else i + 6) * stagger
            if i > 20:
                ta = t_alert + 1.0 + (i - 21) * 0.5      # rally lands after the alert
            anim = kf(f'{prefix}c{i}', [
                (0, 'opacity:0; transform:translateY(12px);'),
                (ta, 'opacity:0; transform:translateY(12px);'),
                (ta + 0.35, 'opacity:1; transform:none;'),
                (D, 'opacity:1;'),
            ])
            parts.append(f'<g style="{anim}">{body}</g>')

    # trendline draw + anchor dots
    anim = kf(f'{prefix}line', [
        (0, f'stroke-dashoffset:{llen:.0f};'),
        (t_line, f'stroke-dashoffset:{llen:.0f};'),
        (t_line + 2.0, 'stroke-dashoffset:0;'),
        (D, 'stroke-dashoffset:0;'),
    ])
    parts.append(f'<line x1="{lx1:.1f}" y1="{ly1:.1f}" x2="{lx2:.1f}" y2="{ly2:.1f}" stroke="{line_color}" '
                 f'stroke-width="3.5" stroke-dasharray="{llen:.0f}" style="{anim}"/>')
    for k, (nm, i, td) in enumerate((('d1', 1, t_line + 0.3), ('d2', 11, t_line + 1.2))):
        anim = kf(f'{prefix}{nm}', [
            (0, 'opacity:0; transform:scale(.2);'),
            (td, 'opacity:0; transform:scale(.2);'),
            (td + 0.35, 'opacity:1; transform:scale(1);'),
            (D, 'opacity:1;'),
        ])
        parts.append(f'<g style="{anim}transform-box:fill-box;transform-origin:center">'
                     f'<circle cx="{X(i):.1f}" cy="{Y(line_p(i)):.1f}" r="8" fill="{line_color}" '
                     f'stroke="{NAVY}" stroke-width="3"/></g>')

    # arrow above/below the event candle
    ax = X(20)
    o20, h20, l20, c20 = candles[20]
    tip = Y(h20) - 22 if side == 'upper' else Y(l20) + 20
    arrow = f'<path d="M{ax:.1f} {tip:.1f} l-13 17 h8 v14 h10 v-14 h8 z" fill="{AMBER}"/>'
    anim = kf(f'{prefix}arr', [
        (0, 'opacity:0; transform:translateY(26px);'),
        (t_break + 0.9, 'opacity:0; transform:translateY(26px);'),
        (t_break + 1.4, 'opacity:1; transform:none;'),
        (D, 'opacity:1;'),
    ])
    parts.append(f'<g style="{anim}">{arrow}</g>')

    # alert toast
    tx, ty = x0 + cw_ - 360, y0 - 4
    anim = kf(f'{prefix}toast', [
        (0, 'opacity:0; transform:translateX(36px);'),
        (t_alert, 'opacity:0; transform:translateX(36px);'),
        (t_alert + 0.5, 'opacity:1; transform:none;'),
        (D, 'opacity:1;'),
    ])
    parts.append(
        f'<g style="{anim}filter:drop-shadow(0 10px 26px rgba(0,0,0,.45))">'
        f'<rect x="{tx}" y="{ty}" width="348" height="86" rx="16" fill="#FFFFFF"/>'
        f'<text x="{tx + 22}" y="{ty + 36}" font-size="19" font-weight="800" fill="#0F1726" '
        f'font-family="system-ui"><tspan fill="{line_color}">◢</tspan>  Diago Alert · just now</text>'
        f'<text x="{tx + 22}" y="{ty + 64}" font-size="16" font-weight="600" fill="#49556A" '
        f'font-family="system-ui">{alert_text}</text>'
        f'<rect x="{tx + 262}" y="{ty + 47}" width="66" height="24" rx="12" fill="hsl(158,52%,32%)"/>'
        f'<text x="{tx + 295}" y="{ty + 64}" font-size="14" font-weight="800" fill="#fff" '
        f'font-family="system-ui" text-anchor="middle">{score}</text></g>')
    return ''.join(parts)


BRK_CANDLES = [
    (97, 99.5, 94, 95), (95, 100, 93, 94), (94, 96, 90, 91), (91, 94, 88, 89),
    (89, 93.5, 87, 92), (92, 95.5, 90, 90.5), (90.5, 94.4, 88, 89), (89, 91, 85, 86),
    (86, 90, 84, 88.5), (88.5, 91.2, 86, 87), (87, 89, 83, 84), (84, 89, 82, 83),
    (83, 86, 80, 81), (81, 84, 78, 79.5), (79.5, 83, 77.5, 82), (82, 84.6, 80, 81),
    (81, 83, 78.5, 79.5), (79.5, 82.4, 78, 81.5), (79, 80.8, 77.5, 79.8), (79.8, 80.1, 78.5, 79.9),
    (79.9, 85, 79.5, 84),
    (84, 87, 82.5, 86), (86, 90, 85, 89), (89, 91.5, 87, 88), (88, 94, 87.5, 93),
]
SUP_CANDLES = [
    (77.5, 79, 75.6, 78), (78, 79.5, 76.0, 78.5), (78.5, 81.5, 77.5, 81), (81, 84, 80, 83.5),
    (83.5, 86.5, 82.5, 86), (86, 88.5, 85, 87.5), (87.5, 88, 84.5, 85), (85, 86, 83, 83.8),
    (83.8, 84.5, 82, 82.6), (82.6, 83.5, 81.8, 82.2), (82.2, 83, 81.7, 82), (82, 83.5, 81.5, 83),
    (83, 86, 82.5, 85.5), (85.5, 88.5, 84.5, 88), (88, 91, 87, 90.5), (90.5, 93.5, 89.5, 93),
    (93, 96, 92, 95.5), (95.5, 97.5, 94.5, 96.5), (96.5, 97, 92.5, 93), (93, 93.5, 88.5, 89),
    (89, 92.5, 86.5, 92),
    (92, 94.5, 91, 94), (94, 96.5, 93, 96), (96, 97, 94.5, 95), (95, 99, 94.5, 98.5),
]


def build():
    random.seed(7)
    scenes = []

    # ---------------- S1 hook (0-10)
    a_line = kf('s1line', [(0, 'stroke-dashoffset:1500;'), (0.5, 'stroke-dashoffset:1500;'),
                           (3.5, 'stroke-dashoffset:0;'), (D, 'stroke-dashoffset:0;')])
    a_dot = kf('s1dot', [(0, 'opacity:0;'), (3.3, 'opacity:0;'), (3.7, 'opacity:1;'), (D, 'opacity:1;')])
    a_h1 = fade_in_out('s1h1', 2.2, 8.8, base='transform:translateY(16px);', shown='transform:none;')
    a_mark = fade_in_out('s1mark', 4.2, 8.8)
    s1 = f'''
  <div class="scene" style="{fade_in_out('s1', 0, 8.9, dur_in=0.01)}">
    <svg viewBox="0 0 1280 720" class="fill">
      <line x1="-40" y1="620" x2="1320" y2="120" stroke="{AMBER}" stroke-width="3"
            stroke-dasharray="1500" style="{a_line}" opacity=".9"/>
      <circle cx="985" cy="243" r="9" fill="{AMBER}" style="{a_dot}"/>
    </svg>
    <div class="center" style="top:408px">
      <div style="{a_h1}font-size:52px;font-weight:800;letter-spacing:-.02em;color:#EAF0F7;
           text-align:center;max-width:900px;line-height:1.15">The market leaves clues<br>in its diagonals.</div>
      <div style="{a_mark}margin-top:26px;font-size:20px;color:{AMBER};font-weight:700;
           letter-spacing:.14em">◢ &nbsp;D I A G O</div>
    </div>
  </div>'''
    scenes.append(s1)

    # ---------------- S2 problem (10-22)
    minis = []
    for k in range(28):
        col, row = k % 7, k // 7
        x, y = 40 + col * 175, 60 + row * 132
        pts, p = [], 50 + random.random() * 30
        for j in range(12):
            p += random.uniform(-7, 7)
            pts.append(f'{x + 10 + j * 12.5},{y + 90 - p * 0.8}')
        t = 10.6 + k * 0.12
        anim = kf(f's2m{k}', [(0, 'opacity:0; transform:translateY(10px);'),
                              (t, 'opacity:0; transform:translateY(10px);'),
                              (t + 0.3, 'opacity:.85; transform:none;'), (D, 'opacity:.85;')])
        minis.append(f'<g style="{anim}"><rect x="{x}" y="{y}" width="155" height="100" rx="10" '
                     f'fill="#13253D" stroke="#22364F"/>'
                     f'<polyline points="{" ".join(pts)}" fill="none" '
                     f'stroke="{random.choice([TEAL_L, DN, "#7FD6C9", AMBER])}" stroke-width="2"/></g>')
    a_t1 = fade_in_out('s2t1', 14.6, 20.8, base='transform:translateY(14px);', shown='transform:none;')
    a_dim = kf('s2dim', [(0, 'opacity:0;'), (17.6, 'opacity:0;'), (18.4, 'opacity:.9;'),
                         (20.8, 'opacity:.9;'), (21.8, 'opacity:0;'), (D, 'opacity:0;')])
    a_t2 = fade_in_out('s2t2', 18.2, 20.8, base='transform:scale(.94);', shown='transform:scale(1);')
    s2 = f'''
  <div class="scene" style="{fade_in_out('s2', 9.9, 21.0, dur_in=0.9)}">
    <svg viewBox="0 0 1280 620" style="position:absolute;top:0;width:1280px;height:620px">{''.join(minis)}</svg>
    <div class="center" style="top:560px">
      <div style="{a_t1}font-size:34px;font-weight:800;color:#EAF0F7">
        <span style="color:{AMBER}">2,259 stocks.</span> Rescanned every single night.</div>
    </div>
    <div style="{a_dim}position:absolute;inset:0;background:{NAVY}"></div>
    <div class="center" style="top:300px">
      <div style="{a_t2}font-size:56px;font-weight:800;color:#EAF0F7;letter-spacing:-.02em">
        You can't watch them all.</div>
    </div>
  </div>'''
    scenes.append(s2)

    # ---------------- S3 breakout (22-41)
    chart3 = candle_chart('s3', BRK_CANDLES, lambda i: 100 - 1.1 * (i - 1), 'upper',
                          22.6, (90, 150, 1100, 440), 'TICKR broke its diagonal', '8.4/10',
                          'RESISTANCE BREAKOUT · SIMULATED',
                          t_line=29.0, t_break=32.2, t_alert=34.6)
    a_s3t = fade_in_out('s3t', 37.2, 39.8, base='transform:translateY(12px);', shown='transform:none;')
    s3 = f'''
  <div class="scene" style="{fade_in_out('s3', 21.9, 40.0, dur_in=0.9)}">
    <svg viewBox="0 0 1280 720" class="fill">{chart3}</svg>
    <div class="center" style="top:645px">
      <div style="{a_s3t}font-size:30px;font-weight:800;color:#EAF0F7">
        Every breakout — <span style="color:{AMBER}">the moment it prints.</span></div>
    </div>
  </div>'''
    scenes.append(s3)

    # ---------------- S4 support (41-56)
    chart4 = candle_chart('s4', SUP_CANDLES, lambda i: 76 + 0.55 * (i - 1), 'under',
                          41.4, (90, 150, 1100, 440), 'TICKR held its support line', '8.1/10',
                          'SUPPORT BOUNCE · SIMULATED',
                          t_line=45.6, t_break=48.6, t_alert=50.6, stagger=0.16)
    a_s4t = fade_in_out('s4t', 52.6, 54.8, base='transform:translateY(12px);', shown='transform:none;')
    s4 = f'''
  <div class="scene" style="{fade_in_out('s4', 40.9, 55.0, dur_in=0.9)}">
    <svg viewBox="0 0 1280 720" class="fill">{chart4}</svg>
    <div class="center" style="top:645px">
      <div style="{a_s4t}font-size:30px;font-weight:800;color:#EAF0F7">
        Support bounces too — <span style="color:#1FCFAF">Diago's strongest setup.</span></div>
    </div>
  </div>'''
    scenes.append(s4)

    # ---------------- S5 proof (56-72)
    a_card = fade_in_out('s5card', 56.8, 70.8, base='transform:scale(.9);', shown='transform:scale(1);')
    tiles = ''
    for k, txt in enumerate(('72,000+ historical setups behind every score',
                             'Every signal tracked from the day it prints',
                             'Losses published. Nothing deleted.')):
        t = 59.4 + k * 0.9
        anim = kf(f's5tile{k}', [(0, 'opacity:0; transform:translateX(24px);'),
                                 (t, 'opacity:0; transform:translateX(24px);'),
                                 (t + 0.5, 'opacity:1; transform:none;'), (70.8, 'opacity:1;'),
                                 (71.8, 'opacity:0;'), (D, 'opacity:0;')])
        tiles += (f'<div style="{anim}background:#13253D;border:1px solid #22364F;border-radius:14px;'
                  f'padding:20px 24px;font-size:20px;font-weight:650;color:#D7E1EC">'
                  f'<span style="color:{TEAL_L};font-weight:800;margin-right:10px">✓</span>{txt}</div>')
    rows = ''
    perf = [('NDLS', '+307%', TEAL_L), ('AEHR', '+296%', TEAL_L), ('TWST', '+195%', TEAL_L),
            ('PARA', '−94%', '#F08A8A'), ('ALHC', '−41%', '#F08A8A')]
    for k, (tk, r, col) in enumerate(perf):
        t = 64.2 + k * 0.5
        anim = kf(f's5r{k}', [(0, 'opacity:0; transform:translateY(10px);'),
                              (t, 'opacity:0; transform:translateY(10px);'),
                              (t + 0.4, 'opacity:1; transform:none;'), (70.8, 'opacity:1;'),
                              (71.8, 'opacity:0;'), (D, 'opacity:0;')])
        rows += (f'<div style="{anim}display:flex;justify-content:space-between;padding:11px 20px;'
                 f'border-bottom:1px solid #22364F;font-size:19px;font-weight:700;color:#EAF0F7">'
                 f'<span>{tk}</span><span style="color:{col};font-variant-numeric:tabular-nums">{r}</span></div>')
    a_s5t = fade_in_out('s5t', 66.0, 70.8, base='transform:translateY(10px);', shown='transform:none;')
    s5 = f'''
  <div class="scene" style="{fade_in_out('s5', 55.9, 71.0, dur_in=0.9)}">
    <div style="{a_card}position:absolute;left:100px;top:120px;width:400px;background:hsl(158,52%,30%);
         border-radius:22px;padding:38px 40px;color:#fff;box-shadow:0 24px 60px -20px rgba(0,0,0,.5)">
      <div style="font-size:15px;font-weight:800;letter-spacing:.1em;opacity:.85">DIAGO CONFIDENCE</div>
      <div style="font-size:92px;font-weight:800;line-height:1.05;margin-top:8px">8.4<span
        style="font-size:34px;opacity:.7"> / 10</span></div>
    </div>
    <div style="position:absolute;left:100px;top:400px;width:400px;display:flex;flex-direction:column;gap:14px">{tiles}</div>
    <div style="position:absolute;right:100px;top:120px;width:560px;background:#0F1E33;border:1px solid #22364F;
         border-radius:18px;overflow:hidden">
      <div style="padding:16px 20px;font-size:15px;font-weight:800;letter-spacing:.08em;color:#8FA0B5;
           border-bottom:1px solid #22364F">SIGNAL PERFORMANCE · 2026 · SIMULATED</div>{rows}</div>
    <div class="center" style="top:640px">
      <div style="{a_s5t}font-size:32px;font-weight:800;color:#EAF0F7">
        We publish the <span style="color:#F08A8A">losers</span> too.</div>
    </div>
  </div>'''
    scenes.append(s5)

    # ---------------- S6 CTA (72-88)
    a_logo = fade_in_out('s6logo', 73.0, 87.9, base='transform:scale(.85);', shown='transform:scale(1);')
    a_l1 = fade_in_out('s6l1', 75.2, 87.9, base='transform:translateY(14px);', shown='transform:none;')
    a_l2 = fade_in_out('s6l2', 78.0, 87.9, base='transform:translateY(14px);', shown='transform:none;')
    a_l3 = fade_in_out('s6l3', 80.6, 87.9)
    s6 = f'''
  <div class="scene" style="{fade_in_out('s6', 71.9, 87.9, dur_in=1.0)}
       background:linear-gradient(120deg, #2A1508, #7A3D14 62%, #C05C1D 125%)">
    <div class="center" style="top:170px">
      <div style="{a_logo}display:flex;align-items:center;gap:22px">
        <svg width="84" height="84" viewBox="0 0 26 26"><defs>
          <linearGradient id="pw" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stop-color="#0E9382"/><stop offset="1" stop-color="#14B4A0"/></linearGradient>
          <linearGradient id="pb" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stop-color="#C05C1D"/><stop offset="1" stop-color="#F0A868"/></linearGradient></defs>
          <path d="M3 23 L23 23 L23 3 Z" fill="url(#pw)" stroke="url(#pw)" stroke-width="3"
                stroke-linejoin="round"/>
          <path d="M2 16.5 L16 2.5" stroke="url(#pb)" stroke-width="4.6" stroke-linecap="round"/></svg>
        <div style="font-size:76px;font-weight:800;color:#fff;letter-spacing:-.02em">Diago</div>
      </div>
      <div style="{a_l1}font-size:34px;font-weight:700;color:#FDEBD9;margin-top:40px;text-align:center">
        Your ranked shortlist is ready tomorrow at dawn.</div>
      <div style="{a_l2}font-size:26px;font-weight:800;color:#fff;margin-top:26px;background:rgba(255,255,255,.14);
           border:1px solid rgba(255,255,255,.25);padding:14px 36px;border-radius:99px">
        7 days free &nbsp;·&nbsp; then $5/month</div>
      <div style="{a_l3}font-size:15px;color:#E3C8AE;margin-top:44px">
        Simulated results shown · Statistics, not promises · Not investment advice</div>
    </div>
  </div>'''
    scenes.append(s6)

    bg = kf('bgdrift', [(0, 'background-position:0% 40%;'), (D, 'background-position:100% 60%;')])
    html = f'''<!doctype html><html><head><meta charset="utf-8"><title>Diago — promo film</title>
<style>
* {{ margin:0; box-sizing:border-box; }}
html, body {{ background:#000; }}
#stage {{ position:relative; width:{W}px; height:{H}px; overflow:hidden;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  background:linear-gradient(118deg, #0D1B2E 0%, #16233A 45%, #241A1B 80%, #3C2212 100%);
  background-size:220% 220%; {bg} }}
.scene {{ position:absolute; inset:0; }}
.fill {{ position:absolute; inset:0; width:{W}px; height:{H}px; }}
.center {{ position:absolute; left:0; right:0; display:flex; flex-direction:column; align-items:center; }}
{chr(10).join(_kf)}
</style></head><body><div id="stage">{''.join(scenes)}</div></body></html>'''
    out = os.path.join(os.path.dirname(__file__), 'film.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'film written: {out} ({len(html) // 1024} KB, {len(_kf)} keyframe tracks, {D:.0f}s)')


if __name__ == '__main__':
    build()
