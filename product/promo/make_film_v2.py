"""
Diago promo film v2 — "The Loss We Published" -> product/promo/film_v2.html

Implements the marketer's creative doc (creative_v2.md) verbatim:
  S1  0-6    Cold open: the published loss (PARA -94%), alone on black.
  S2  6-12   The wins stack in ABOVE the loss — the red row never fades.
  S3 12-22   Hard cut: wall of charts, 0->2,259 count-up, diagonals draw,
             one chart scales up and breaks out.
  S4 22-31   The alert toast -> the 8.4/10 score card.
  S5 31-38   Support bounce — Diago's strongest setup.
  S6 38-45   Warm CTA end card, compliance line persistent.

Same deterministic single-timeline technique as v1 (freezable per frame).
Usage: python3 -m product.promo.make_film_v2
"""
import math
import os
import random

D = 45.0
W, H = 1280, 720
NAVY = '#0D1B2E'
TEAL, TEAL_L = '#0E9382', '#5BC8B8'
RUST, AMBER = '#C05C1D', '#F0A868'
UP, DN, RED = '#14B8A2', '#D97B6C', '#F26D6D'

_kf = []


def pct(t):
    return f'{t / D * 100:.3f}%'


def kf(name, stops):
    body = ' '.join(f'{pct(t)} {{{css}}}' for t, css in stops)
    _kf.append(f'@keyframes {name} {{ {body} }}')
    return f'animation:{name} {D}s linear 1 both;'


def appear(name, t_in, dur=0.5, t_out=None, dur_out=0.8, base='transform:translateY(12px);', shown='transform:none;'):
    stops = [(0, f'opacity:0;{base}'), (t_in, f'opacity:0;{base}'), (t_in + dur, f'opacity:1;{shown}')]
    if t_out is not None:
        stops += [(t_out, f'opacity:1;{shown}'), (t_out + dur_out, 'opacity:0;'), (D, 'opacity:0;')]
    else:
        stops += [(D, f'opacity:1;{shown}')]
    return kf(name, stops)


def perf_row(name, ticker, ret, color, anim):
    return f'''
    <div style="{anim}display:flex;justify-content:space-between;align-items:baseline;width:460px;
         background:#0F1726;border:1px solid #22364F;border-radius:14px;padding:20px 28px">
      <span style="font-size:26px;font-weight:800;color:#EAF0F7;letter-spacing:.02em">{ticker}</span>
      <span style="display:flex;align-items:baseline;gap:14px">
        <span style="font-size:12px;color:#5C6E88;font-weight:600;letter-spacing:.08em">SIMULATED</span>
        <span style="font-size:30px;font-weight:800;color:{color};font-variant-numeric:tabular-nums;
              {('text-shadow:0 0 22px ' + color + '66;') if color == RED else ''}">{ret}</span>
      </span>
    </div>'''


def candle_chart(prefix, candles, line_p, side, geom, t0, stagger, t_line, t_break,
                 caption='', arrow=True):
    """Same engine as v1, no toast (toasts are scene-level in v2)."""
    x0, y0, cw_, ch_ = geom
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
    if caption:
        a = kf(f'{prefix}cap', [(0, 'opacity:0;'), (t0, 'opacity:0;'), (t0 + 0.5, 'opacity:1;'), (D, 'opacity:1;')])
        parts.append(f'<text x="{x0}" y="{y0 - 16}" font-size="16" font-weight="700" fill="#8FA0B5" '
                     f'font-family="system-ui" letter-spacing=".1em" style="{a}">{caption}</text>')
    bw = cw_ / n * 0.55
    for i, (o, hh, ll, c) in enumerate(candles):
        color = UP if c >= o else DN
        y_top, y_bot = Y(max(o, c)), Y(min(o, c))
        body = (f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{Y(hh):.1f}" y2="{Y(ll):.1f}" '
                f'stroke="{color}" stroke-width="2"/>'
                f'<rect x="{X(i) - bw / 2:.1f}" y="{y_top:.1f}" width="{bw:.1f}" '
                f'height="{max(2.5, y_bot - y_top):.1f}" fill="{color}" rx="2"/>')
        if i == 20:
            anim = kf(f'{prefix}c{i}', [
                (0, 'opacity:0; transform:scaleY(.15);'),
                (t_break, 'opacity:0; transform:scaleY(.15);'),
                (t_break + 0.45, f'opacity:1; transform:scaleY(1.08); filter:drop-shadow(0 0 14px {AMBER});'),
                (t_break + 0.7, 'transform:scaleY(1);'),
                (t_break + 2.4, f'filter:drop-shadow(0 0 10px {AMBER});'),
                (t_break + 3.6, 'filter:none;'),
                (D, 'opacity:1;'),
            ])
            parts.append(f'<g style="{anim}transform-box:fill-box;transform-origin:50% 100%">{body}</g>')
        else:
            ta = t0 + i * stagger if i < 20 else t_break + 1.2 + (i - 21) * 0.35
            anim = kf(f'{prefix}c{i}', [
                (0, 'opacity:0; transform:translateY(12px);'),
                (ta, 'opacity:0; transform:translateY(12px);'),
                (ta + 0.3, 'opacity:1; transform:none;'),
                (D, 'opacity:1;'),
            ])
            parts.append(f'<g style="{anim}">{body}</g>')
    anim = kf(f'{prefix}line', [
        (0, f'stroke-dashoffset:{llen:.0f};'),
        (t_line, f'stroke-dashoffset:{llen:.0f};'),
        (t_line + 1.6, 'stroke-dashoffset:0;'),
        (D, 'stroke-dashoffset:0;'),
    ])
    parts.append(f'<line x1="{lx1:.1f}" y1="{ly1:.1f}" x2="{lx2:.1f}" y2="{ly2:.1f}" stroke="{line_color}" '
                 f'stroke-width="3.5" stroke-dasharray="{llen:.0f}" style="{anim}"/>')
    for nm, i, td in ((f'{prefix}d1', 1, t_line + 0.25), (f'{prefix}d2', 11, t_line + 0.95)):
        anim = kf(nm, [(0, 'opacity:0; transform:scale(.2);'), (td, 'opacity:0; transform:scale(.2);'),
                       (td + 0.3, 'opacity:1; transform:scale(1);'), (D, 'opacity:1;')])
        parts.append(f'<g style="{anim}transform-box:fill-box;transform-origin:center">'
                     f'<circle cx="{X(i):.1f}" cy="{Y(line_p(i)):.1f}" r="8" fill="{line_color}" '
                     f'stroke="{NAVY}" stroke-width="3"/></g>')
    if arrow:
        ax = X(20)
        o20, h20, l20, c20 = candles[20]
        tip = Y(h20) - 22 if side == 'upper' else Y(l20) + 20
        anim = kf(f'{prefix}arr', [(0, 'opacity:0; transform:translateY(24px);'),
                                   (t_break + 0.8, 'opacity:0; transform:translateY(24px);'),
                                   (t_break + 1.2, 'opacity:1; transform:none;'), (D, 'opacity:1;')])
        parts.append(f'<g style="{anim}"><path d="M{ax:.1f} {tip:.1f} l-13 17 h8 v14 h10 v-14 h8 z" '
                     f'fill="{AMBER}"/></g>')
    return ''.join(parts)


def toast(prefix, x, y, label, score, color, t_in, t_out=None):
    anim_stops = [(0, 'opacity:0; transform:translateX(30px);'),
                  (t_in, 'opacity:0; transform:translateX(30px);'),
                  (t_in + 0.45, 'opacity:1; transform:none;')]
    if t_out:
        anim_stops += [(t_out, 'opacity:1;'), (t_out + 0.6, 'opacity:0;'), (D, 'opacity:0;')]
    else:
        anim_stops += [(D, 'opacity:1;')]
    anim = kf(f'{prefix}toast', anim_stops)
    return (f'<g style="{anim}filter:drop-shadow(0 10px 26px rgba(0,0,0,.45))">'
            f'<rect x="{x}" y="{y}" width="238" height="62" rx="14" fill="#FFFFFF"/>'
            f'<text x="{x + 20}" y="{y + 39}" font-size="21" font-weight="800" fill="#0F1726" '
            f'font-family="system-ui"><tspan fill="{color}">◢</tspan>  {label}</text>'
            f'<rect x="{x + 168}" y="{y + 16}" width="52" height="30" rx="15" fill="hsl(158,52%,32%)"/>'
            f'<text x="{x + 194}" y="{y + 37}" font-size="16" font-weight="800" fill="#fff" '
            f'font-family="system-ui" text-anchor="middle">{score}</text></g>')


BRK = [
    (97, 99.5, 94, 95), (95, 100, 93, 94), (94, 96, 90, 91), (91, 94, 88, 89),
    (89, 93.5, 87, 92), (92, 95.5, 90, 90.5), (90.5, 94.4, 88, 89), (89, 91, 85, 86),
    (86, 90, 84, 88.5), (88.5, 91.2, 86, 87), (87, 89, 83, 84), (84, 89, 82, 83),
    (83, 86, 80, 81), (81, 84, 78, 79.5), (79.5, 83, 77.5, 82), (82, 84.6, 80, 81),
    (81, 83, 78.5, 79.5), (79.5, 82.4, 78, 81.5), (79, 80.8, 77.5, 79.8), (79.8, 80.1, 78.5, 79.9),
    (79.9, 85, 79.5, 84),
    (84, 87, 82.5, 86), (86, 90, 85, 89), (89, 91.5, 87, 88), (88, 94, 87.5, 93),
]
SUP = [
    (77.5, 79, 75.6, 78), (78, 79.5, 76.0, 78.5), (78.5, 81.5, 77.5, 81), (81, 84, 80, 83.5),
    (83.5, 86.5, 82.5, 86), (86, 88.5, 85, 87.5), (87.5, 88, 84.5, 85), (85, 86, 83, 83.8),
    (83.8, 84.5, 82, 82.6), (82.6, 83.5, 81.8, 82.2), (82.2, 83, 81.7, 82), (82, 83.5, 81.5, 83),
    (83, 86, 82.5, 85.5), (85.5, 88.5, 84.5, 88), (88, 91, 87, 90.5), (90.5, 93.5, 89.5, 93),
    (93, 96, 92, 95.5), (95.5, 97.5, 94.5, 96.5), (96.5, 97, 92.5, 93), (93, 93.5, 88.5, 89),
    (89, 92.5, 86.5, 92),
    (92, 94.5, 91, 94), (94, 96.5, 93, 96), (96, 97, 94.5, 95), (95, 99, 94.5, 98.5),
]


def build():
    random.seed(11)
    scenes = []

    # ---------------- S1+S2 (0-12): the published loss, then the wins above it
    zoom = kf('s12zoom', [(0, 'transform:scale(1);'), (12, 'transform:scale(1.05);')])
    cut = kf('s12', [(0, 'opacity:1;'), (11.98, 'opacity:1;'), (12.02, 'opacity:0;'), (D, 'opacity:0;')])
    a_para = appear('r_para', 0.4, 0.6)
    a_sim1 = appear('r_cap1', 1.4, 0.5, base='', shown='')
    a_pub = appear('t_pub', 3.2, 0.7, t_out=8.6, dur_out=0.7,
                   base='transform:translate(-50%,12px);', shown='transform:translate(-50%,0);')
    a_ndls = appear('r_ndls', 6.4, 0.55)
    a_aehr = appear('r_aehr', 7.5, 0.55)
    a_del = appear('t_del', 9.3, 0.7,
                   base='transform:translate(-50%,12px);', shown='transform:translate(-50%,0);')
    s12 = f'''
  <div class="scene" style="{cut}background:#05080F">
    <div class="center" style="top:0;bottom:0;justify-content:center;{zoom}">
      <div style="display:flex;flex-direction:column;gap:14px;align-items:center">
        {perf_row('rN', 'NDLS', '+307%', TEAL_L, a_ndls)}
        {perf_row('rA', 'AEHR', '+296%', TEAL_L, a_aehr)}
        {perf_row('rP', 'PARA', '−94%', RED, a_para)}
        <div style="{a_sim1}font-size:13px;color:#5C6E88;font-weight:600;letter-spacing:.14em">SIMULATED RESULTS</div>
        <div style="height:34px;position:relative;margin-top:10px">
          <div style="{a_pub}position:absolute;left:50%;white-space:nowrap;
               font-size:27px;font-weight:800;color:#EAF0F7">Published. <span style="color:{RED}">On purpose.</span></div>
          <div style="{a_del}position:absolute;left:50%;white-space:nowrap;
               font-size:27px;font-weight:800;color:#EAF0F7">Nothing deleted. <span style="color:{TEAL_L}">Ever.</span></div>
        </div>
      </div>
    </div>
  </div>'''
    scenes.append(s12)

    # ---------------- S3+S4 (12-31): the machine -> breakout -> alert -> score
    fade34 = kf('s34', [(0, 'opacity:0;'), (11.98, 'opacity:0;'), (12.02, 'opacity:1;'),
                        (30.3, 'opacity:1;'), (31.1, 'opacity:0;'), (D, 'opacity:0;')])
    minis, mini_lines = [], []
    for k in range(28):
        col, row = k % 7, k // 7
        x, y = 40 + col * 175, 40 + row * 168
        pts, p = [], 50 + random.random() * 30
        for j in range(12):
            p += random.uniform(-7, 7)
            pts.append(f'{x + 10 + j * 12.5},{y + 120 - p * 0.9}')
        t = 12.1 + (k % 14) * 0.13
        a = kf(f'm{k}', [(0, 'opacity:0;'), (t, 'opacity:0;'), (t + 0.3, 'opacity:.8;'),
                         (16.2, 'opacity:.8;'), (17.0, 'opacity:.14;'), (D, 'opacity:.14;')])
        minis.append(f'<g style="{a}"><rect x="{x}" y="{y}" width="155" height="136" rx="10" '
                     f'fill="#13253D" stroke="#22364F"/>'
                     f'<polyline points="{" ".join(pts)}" fill="none" '
                     f'stroke="{random.choice([TEAL_L, DN, "#7FD6C9", AMBER])}" stroke-width="2"/></g>')
        tl = 14.3 + (k % 9) * 0.11
        a2 = kf(f'ml{k}', [(0, 'stroke-dashoffset:200;opacity:0;'), (tl, 'stroke-dashoffset:200;opacity:.9;'),
                           (tl + 0.7, 'stroke-dashoffset:0;'), (16.2, 'opacity:.9;stroke-dashoffset:0;'),
                           (17.0, 'opacity:.12;'), (D, 'opacity:.12;')])
        y1, y2 = y + 30 + random.random() * 40, y + 90 - random.random() * 50
        mini_lines.append(f'<line x1="{x + 8}" y1="{y1:.0f}" x2="{x + 147}" y2="{y2:.0f}" stroke="{AMBER}" '
                          f'stroke-width="1.6" stroke-dasharray="200" style="{a2}"/>')
    # count-up 0 -> 2,259 (stepped elements on the shared timeline)
    steps = [0, 173, 415, 704, 1018, 1332, 1620, 1866, 2058, 2189, 2259]
    counter = ''
    for idx, v in enumerate(steps):
        t_on = 12.6 + idx * 0.24
        t_off = t_on + 0.24 if idx < len(steps) - 1 else 16.4
        a = kf(f'cnt{idx}', [(0, 'opacity:0;'), (t_on - 0.03, 'opacity:0;'), (t_on, 'opacity:1;'),
                             (t_off, 'opacity:1;'), (t_off + 0.03, 'opacity:0;'), (D, 'opacity:0;')]
               if idx < len(steps) - 1 else
               [(0, 'opacity:0;'), (t_on - 0.03, 'opacity:0;'), (t_on, 'opacity:1;'),
                (16.6, 'opacity:1;'), (17.3, 'opacity:0;'), (D, 'opacity:0;')])
        counter += (f'<div style="{a}position:absolute;left:0;right:0;text-align:center;'
                    f'font-size:110px;font-weight:800;color:#fff;letter-spacing:-.02em;'
                    f'font-variant-numeric:tabular-nums;text-shadow:0 4px 30px rgba(0,0,0,.8)">{v:,}</div>')
    a_cnt_cap = kf('cntcap', [(0, 'opacity:0;'), (13.0, 'opacity:0;'), (13.5, 'opacity:1;'),
                              (16.6, 'opacity:1;'), (17.3, 'opacity:0;'), (D, 'opacity:0;')])
    chart_brk = candle_chart('b', BRK, lambda i: 100 - 1.1 * (i - 1), 'upper',
                             (160, 150, 960, 430), t0=16.9, stagger=0.12, t_line=19.0, t_break=20.6,
                             caption='RESISTANCE BREAKOUT · SIMULATED')
    tst = toast('bt', 880, 132, 'Breakout', '8.4', RUST, 22.3)
    a_card = appear('s4card', 24.6, 0.6, base='transform:scale(.9);', shown='transform:scale(1);')
    a_sub1 = appear('s4sub1', 25.6, 0.5)
    a_sub2 = appear('s4sub2', 26.4, 0.5)
    s34 = f'''
  <div class="scene" style="{fade34}">
    <svg viewBox="0 0 1280 720" class="fill">{''.join(minis)}{''.join(mini_lines)}</svg>
    <div style="position:absolute;left:0;right:0;top:250px;height:140px">{counter}</div>
    <div style="{a_cnt_cap}position:absolute;left:0;right:0;top:400px;text-align:center;
         font-size:30px;font-weight:800;color:{AMBER}">stocks. Every night.</div>
    <svg viewBox="0 0 1280 720" class="fill">{chart_brk}{tst}</svg>
    <div style="{a_card}position:absolute;left:110px;top:170px;width:330px;background:hsl(158,52%,30%);
         border-radius:20px;padding:30px 34px;color:#fff;box-shadow:0 24px 60px -20px rgba(0,0,0,.55)">
      <div style="font-size:14px;font-weight:800;letter-spacing:.1em;opacity:.85">DIAGO SCORE</div>
      <div style="font-size:78px;font-weight:800;line-height:1.05;margin-top:6px">8.4<span
        style="font-size:30px;opacity:.7"> / 10</span></div>
      <div style="{a_sub1}font-size:16px;font-weight:650;margin-top:14px;opacity:.95">
        Built on 72,000+ historical setups</div>
      <div style="{a_sub2}font-size:13.5px;font-weight:600;margin-top:6px;opacity:.75">
        Scores range 6–10</div>
    </div>
  </div>'''
    scenes.append(s34)

    # ---------------- S5 (31-38): support bounce
    fade5 = kf('s5', [(0, 'opacity:0;'), (30.6, 'opacity:0;'), (31.3, 'opacity:1;'),
                      (37.4, 'opacity:1;'), (38.1, 'opacity:0;'), (D, 'opacity:0;')])
    chart_sup = candle_chart('s', SUP, lambda i: 76 + 0.55 * (i - 1), 'under',
                             (100, 150, 1080, 430), t0=31.4, stagger=0.09, t_line=33.5, t_break=35.1,
                             caption='SUPPORT BOUNCE · SIMULATED')
    tst5 = toast('st', 900, 132, 'Bounce', '9.1', '#1FCFAF', 36.2)
    a_s5t = appear('s5t', 36.5, 0.5)
    s5 = f'''
  <div class="scene" style="{fade5}">
    <svg viewBox="0 0 1280 720" class="fill">{chart_sup}{tst5}</svg>
    <div class="center" style="top:648px">
      <div style="{a_s5t}font-size:29px;font-weight:800;color:#EAF0F7">
        <span style="color:#1FCFAF">Diago's strongest setup.</span></div>
    </div>
  </div>'''
    scenes.append(s5)

    # ---------------- S6 (38-45): warm CTA
    fade6 = kf('s6', [(0, 'opacity:0;'), (37.6, 'opacity:0;'), (38.4, 'opacity:1;'), (D, 'opacity:1;')])
    a_logo = appear('s6logo', 38.7, 0.7, base='transform:scale(.86);', shown='transform:scale(1);')
    tiles = ''
    for k, txt in enumerate(('7 days free — no card', '$5/month', 'All signals public')):
        a = appear(f's6t{k}', 39.7 + k * 0.75, 0.5)
        tiles += (f'<div style="{a}background:rgba(255,255,255,.13);border:1px solid rgba(255,255,255,.25);'
                  f'border-radius:14px;padding:16px 26px;font-size:21px;font-weight:750;color:#fff">'
                  f'<span style="color:#8FF0DD;font-weight:800;margin-right:10px">✓</span>{txt}</div>')
    a_comp = appear('s6comp', 38.9, 0.6, base='', shown='')
    s6 = f'''
  <div class="scene" style="{fade6}background:linear-gradient(120deg, #2A1508, #7A3D14 62%, #C05C1D 125%)">
    <div class="center" style="top:150px">
      <div style="{a_logo}display:flex;align-items:center;gap:20px">
        <svg width="76" height="76" viewBox="0 0 26 26"><defs>
          <linearGradient id="p2w" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stop-color="#0E9382"/><stop offset="1" stop-color="#14B4A0"/></linearGradient>
          <linearGradient id="p2b" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stop-color="#C05C1D"/><stop offset="1" stop-color="#F0A868"/></linearGradient></defs>
          <path d="M3 23 L23 23 L23 3 Z" fill="url(#p2w)" stroke="url(#p2w)" stroke-width="3" stroke-linejoin="round"/>
          <path d="M2 16.5 L16 2.5" stroke="url(#p2b)" stroke-width="4.6" stroke-linecap="round"/></svg>
        <div style="font-size:68px;font-weight:800;color:#fff;letter-spacing:-.02em">Diago</div>
      </div>
      <div style="display:flex;gap:16px;margin-top:52px">{tiles}</div>
      <div style="{a_comp}font-size:15px;color:#E3C8AE;margin-top:56px">
        Simulated results. Not investment advice.</div>
    </div>
  </div>'''
    scenes.append(s6)

    html = f'''<!doctype html><html><head><meta charset="utf-8"><title>Diago — promo v2</title>
<style>
* {{ margin:0; box-sizing:border-box; }}
html, body {{ background:#000; }}
#stage {{ position:relative; width:{W}px; height:{H}px; overflow:hidden;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  background:linear-gradient(118deg, #0D1B2E 0%, #16233A 45%, #241A1B 80%, #3C2212 100%);
  background-size:220% 220%; }}
.scene {{ position:absolute; inset:0; }}
.fill {{ position:absolute; inset:0; width:{W}px; height:{H}px; }}
.center {{ position:absolute; left:0; right:0; display:flex; flex-direction:column; align-items:center; }}
{chr(10).join(_kf)}
</style></head><body><div id="stage">{''.join(scenes)}</div></body></html>'''
    out = os.path.join(os.path.dirname(__file__), 'film_v2.html')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'film v2 written: {out} ({len(html) // 1024} KB, {len(_kf)} tracks, {D:.0f}s)')


if __name__ == '__main__':
    build()
