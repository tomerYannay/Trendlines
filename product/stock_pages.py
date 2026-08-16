"""
Per-ticker detail pages for the product site.

For every ticker in today's candidate tables:
  * price chart (self-contained SVG, log scale — consistent with the methodology)
    with the relevant diagonal drawn from its true anchors; resolution picks
    itself: daily when the line is young, weekly/monthly when anchor #1 is
    years back, so the line's origin is always visible.
  * company fundamentals panel (market cap, sector, P/E ...) from Alpha Vantage
    OVERVIEW, cached locally for 7 days (product/data/overview_cache.json).
  * a large confidence card on a 6-10 scale — deeper green = higher score.

Called from product.build.main().
"""
import json
import math
import os
import time
import warnings

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import requests

import db

CACHE_PATH = 'product/data/overview_cache.json'
CACHE_TTL_DAYS = 7
CONF_LO, CONF_HI = 35.0, 70.0        # calibrated-% range mapped onto the 6-10 scale


# ---------------------------------------------------------------- fundamentals

def _load_cache():
    try:
        return json.load(open(CACHE_PATH))
    except Exception:
        return {}


def fetch_overview(ticker, cache):
    rec = cache.get(ticker)
    if rec and time.time() - rec.get('_ts', 0) < CACHE_TTL_DAYS * 86400:
        return rec
    try:
        url = (f'https://www.alphavantage.co/query?function=OVERVIEW&symbol={ticker}'
               f'&apikey={db.ALPHA_VANTAGE_KEY}')
        db._api_rate_limiter.wait()
        j = requests.get(url, timeout=20).json()
        if j.get('Symbol'):
            j['_ts'] = time.time()
            cache[ticker] = j
            return j
    except Exception:
        pass
    return rec or {}


def money(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    for unit, div in (('T', 1e12), ('B', 1e9), ('M', 1e6)):
        if abs(v) >= div:
            return f'${v / div:.2f}{unit}'
    return f'${v:,.0f}'


def num_or_dash(v, pat='{:.2f}'):
    try:
        f = float(v)
        if math.isnan(f):
            return '—'
        return pat.format(f)
    except (TypeError, ValueError):
        return '—'


# ---------------------------------------------------------------- confidence card

def conf_to_score(conf_pct):
    x = (float(conf_pct) - CONF_LO) / (CONF_HI - CONF_LO)
    return round(6 + 4 * min(1.0, max(0.0, x)), 1)


def score_color(score):
    """6 -> light green, 10 -> deep green."""
    t = (score - 6) / 4
    light = 62 - t * 38          # 62% -> 24%
    text = '#0F1726' if light > 46 else '#FFFFFF'
    return f'hsl(158, 52%, {light:.0f}%)', text


def confidence_card(conf):
    if conf is None or (isinstance(conf, float) and math.isnan(conf)):
        return ('<div class="conf-card" style="background:#E8EDF5;color:#49556A">'
                '<div><div class="lbl">Diago confidence</div>'
                '<div class="score">—</div>'
                '<div class="sub2">Approaching the line — a score is assigned once a signal prints.</div>'
                '</div></div>')
    score = conf_to_score(conf)
    bg, tx = score_color(score)
    return (f'<div class="conf-card" style="background:{bg};color:{tx}">'
            f'<div class="score num">{score:.1f}<small> / 10</small></div>'
            f'<div><div class="lbl">Diago confidence</div>'
            f'<div class="sub2">Calibrated from {conf:.0f}% historical hit-rate on similar setups '
            f'(20-trading-day horizon). Statistics — not a guarantee.</div></div></div>')


# ---------------------------------------------------------------- chart

def load_prices(ticker):
    rows = db.fetch_query(
        "SELECT date, open, high, low, close FROM stock_prices WHERE ticker=%s ORDER BY date;", (ticker,))
    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close'])
    for c in ('open', 'high', 'low', 'close'):
        df[c] = df[c].astype(float)
    return df


def nice_ticks(lo, hi, n=8):
    """~n clean price levels across the range: linear steps for narrow ranges,
    a round-number log ladder for wide ones."""
    lo = max(lo, 1e-6)
    if hi / lo < 2.5:
        # narrow range -> linear nice steps (e.g. 24, 26, 28, 30 ...)
        raw = (hi - lo) / n
        mag = 10 ** math.floor(math.log10(raw))
        step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag)
        first = math.ceil(lo / step) * step
        return [round(first + i * step, 6) for i in range(int((hi - first) / step) + 1)]
    # wide range -> round-number ladder, thinned evenly in log space
    ladder = []
    k_lo, k_hi = math.floor(math.log10(lo)), math.ceil(math.log10(hi))
    for k in range(k_lo, k_hi + 1):
        for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9):
            v = m * 10 ** k
            if lo <= v <= hi:
                ladder.append(v)
    if not ladder:
        return [lo, hi]
    targets = np.geomspace(lo, hi, n)
    return sorted({min(ladder, key=lambda v: abs(math.log(v) - math.log(t))) for t in targets})


def chart_svg(df, row, side, style='candles'):
    """Price + diagonal, auto daily/weekly/monthly so anchor #1 is visible."""
    dates = df['date'].tolist()
    idx = {d: i for i, d in enumerate(dates)}
    n = len(df)

    a1 = pd.to_datetime(row['anchor1']).date()
    a2 = pd.to_datetime(row['anchor2']).date()
    i1, i2 = idx.get(a1), idx.get(a2)
    if i1 is None or i2 is None:
        return '<p>Chart unavailable.</p>', ''
    price_col = 'high' if side == 'upper' else 'low'
    p2 = float(df[price_col].iloc[i2])
    slope_d = math.log(1 + float(row['slope_yr_pct']) / 100) / 252

    start = max(0, i1 - 40)
    span = n - start
    step, tf = (1, 'Daily') if span <= 420 else ((5, 'Weekly') if span <= 2100 else (21, 'Monthly'))

    # true OHLC aggregation per bucket (candle = whole day/week/month)
    buckets = []
    for b0 in range(start, n, step):
        b1 = min(n, b0 + step)
        buckets.append({
            'i_last': b1 - 1,
            'op': float(df['open'].iloc[b0]),
            'hi': float(df['high'].iloc[b0:b1].max()),
            'lo': float(df['low'].iloc[b0:b1].min()),
            'cl': float(df['close'].iloc[b1 - 1]),
        })
    nb = len(buckets)
    line_v = [p2 * math.exp(slope_d * (b['i_last'] - i2)) for b in buckets]

    W, H, ML, MR, MT, MB = 960, 430, 14, 62, 20, 36
    lo = min(min(b['lo'] for b in buckets), min(line_v)) * 0.965
    hi = max(max(b['hi'] for b in buckets), max(line_v), float(df[price_col].iloc[i1]), p2) * 1.035
    llo, lhi = math.log(lo), math.log(hi)
    plot_w = W - ML - MR

    def X(k):
        return ML + (k + 0.5) * plot_w / nb

    def Y(v):
        return MT + (lhi - math.log(v)) / (lhi - llo) * (H - MT - MB)

    UP, DN = '#0E9382', '#C25B5B'
    cw = max(1.6, min(9.0, plot_w / nb * 0.62))
    candles = []
    for k, b in enumerate(buckets):
        x = X(k)
        color = UP if b['cl'] >= b['op'] else DN
        y_top, y_bot = Y(max(b['op'], b['cl'])), Y(min(b['op'], b['cl']))
        body_h = max(1.0, y_bot - y_top)
        candles.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{Y(b["hi"]):.1f}" y2="{Y(b["lo"]):.1f}" '
            f'stroke="{color}" stroke-width="1"/>' 
            f'<rect x="{x - cw / 2:.1f}" y="{y_top:.1f}" width="{cw:.1f}" height="{body_h:.1f}" '
            f'fill="{color}" rx="0.8"/>')
    candles = ''.join(candles)

    pts_line = ' '.join(f'{X(k):.1f},{Y(v):.1f}' for k, v in enumerate(line_v))
    line_color = '#B45309' if side == 'upper' else '#0A6E62'

    if style == 'line':
        pts_close = ' '.join(f'{X(k):.1f},{Y(b["cl"]):.1f}' for k, b in enumerate(buckets))
        band = ('M ' + ' L '.join(f'{X(k):.1f},{Y(b["hi"]):.1f}' for k, b in enumerate(buckets))
                + ' L ' + ' L '.join(f'{X(k):.1f},{Y(b["lo"]):.1f}'
                                     for k, b in reversed(list(enumerate(buckets)))) + ' Z')
        candles = (f'<path d="{band}" fill="#49556A" opacity="0.12"/>'
                   f'<polyline points="{pts_close}" fill="none" stroke="#0F1726" stroke-width="1.7"/>')

    gridlines, ylabels = '', ''
    for t in nice_ticks(lo, hi):
        if lo <= t <= hi:
            y = Y(t)
            gridlines += (f'<line x1="{ML}" x2="{W - MR}" y1="{y:.1f}" y2="{y:.1f}" '
                          f'stroke="#EAEDF3" stroke-width="1"/>')
            lbl = (f'{t:,.0f}' if (t >= 10 and float(t) == int(t)) else (f'{t:,.1f}' if t >= 10 else f'{t:.2f}'))
            ylabels += (f'<text x="{W - MR + 8}" y="{y + 4:.1f}" font-size="11" '
                        f'fill="#8A94A6" class="num">{lbl}</text>')
    xlabels = ''
    for frac in (0.02, 0.34, 0.66, 0.98):
        k = int(frac * (nb - 1))
        anch = 'start' if frac < 0.1 else ('end' if frac > 0.9 else 'middle')
        xlabels += (f'<text x="{X(k):.1f}" y="{H - 10}" text-anchor="{anch}" font-size="11" '
                    f'fill="#8A94A6">{dates[buckets[k]["i_last"]]}</text>')

    def bucket_of(i):
        return min(range(nb), key=lambda kk: abs(buckets[kk]['i_last'] - (step - 1) / 2 - i))

    a_lbl = ('H1', 'H2') if side == 'upper' else ('L1', 'L2')
    dy, base = (-11, 'auto') if side == 'upper' else (18, 'hanging')
    def anchor_marker(i, price, label):
        k = bucket_of(i)
        x, y = X(k), Y(price)
        return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="{line_color}" stroke="#fff" stroke-width="2"/>'
                f'<text x="{x:.1f}" y="{y + dy:.1f}" text-anchor="middle" font-size="10.5" font-weight="700" '
                f'fill="{line_color}">{label}</text>')

    dots = (anchor_marker(i1, float(df[price_col].iloc[i1]), a_lbl[0])
            + anchor_marker(i2, p2, a_lbl[1]))

    # last-price tag on the axis
    last_cl = buckets[-1]['cl']
    tag_color = UP if buckets[-1]['cl'] >= buckets[-1]['op'] else DN
    ytag = Y(last_cl)
    price_tag = (f'<rect x="{W - MR + 2}" y="{ytag - 10:.1f}" width="{MR - 4}" height="20" rx="4" fill="{tag_color}"/>'
                 f'<text x="{W - MR / 2:.1f}" y="{ytag + 4:.1f}" text-anchor="middle" font-size="11" '
                 f'font-weight="700" fill="#fff" class="num">{last_cl:,.2f}</text>')

    svg = (f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto" role="img" '
           f'aria-label="{row["ticker"]} candlestick chart with trendline">'
           f'{gridlines}{candles}'
           f'<polyline points="{pts_line}" fill="none" stroke="{line_color}" stroke-width="4" opacity="0.18"/>'
           f'<polyline points="{pts_line}" fill="none" stroke="{line_color}" stroke-width="2"/>'
           f'{dots}{price_tag}{ylabels}{xlabels}</svg>')
    return svg, tf


# ---------------------------------------------------------------- page

def build_stock_page(row, ov, page_fn, stamp):
    ticker = row['ticker']
    side = row['side_key']
    side_name = 'Resistance breakout' if side == 'upper' else 'Support bounce'
    pill_cls = 'brk' if side == 'upper' else 'sup'
    status = row.get('status', 'APPROACHING')
    status_lbl = {'BREAKOUT': 'Breakout signal', 'SUPPORT_TOUCH': 'Support signal',
                  'PIERCED': 'Pierced — unconfirmed', 'APPROACHING': 'Approaching the line'}.get(status, status)

    df = load_prices(ticker)
    svg_candles, tf = chart_svg(df, row, side, 'candles')
    svg_line, _ = chart_svg(df, row, side, 'line')
    last_close = float(df['close'].iloc[-1])
    c = df['close']
    def chg(k):
        return round((last_close / float(c.iloc[-1 - k]) - 1) * 100, 2) if len(c) > k else None
    chg_d, chg_w, chg_m = chg(1), chg(5), chg(21)
    last_date = df['date'].iloc[-1]
    hi52 = df['high'].tail(252).max()
    lo52 = df['low'].tail(252).min()
    name = ov.get('Name', ticker)
    desc = (ov.get('Description') or '').strip()
    if len(desc) > 420:
        desc = desc[:420].rsplit(' ', 1)[0] + '…'

    dist = -row['gap_vs_line_pct'] if side == 'upper' else row['gap_vs_line_pct']
    kv = ''.join(f'<div class="kv"><span>{k}</span><b class="num">{v}</b></div>' for k, v in [
        ('Market cap', money(ov.get('MarketCapitalization'))),
        ('Sector', ov.get('Sector', '—') or '—'),
        ('Industry', (ov.get('Industry', '—') or '—')[:28]),
        ('P/E ratio', num_or_dash(ov.get('PERatio'))),
        ('EPS', num_or_dash(ov.get('EPS'))),
        ('Beta', num_or_dash(ov.get('Beta'))),
        ('Dividend yield', num_or_dash(ov.get('DividendYield'), '{:.2%}') if ov.get('DividendYield') not in (None, 'None', '0') else '—'),
        ('52-week high', f'{hi52:,.2f}'),
        ('52-week low', f'{lo52:,.2f}'),
        ('Avg $ volume', money((row.get('dollar_vol_m') or 0) * 1e6)),
        ('Volatility (ATR)', num_or_dash(row.get('atr_pct'), '{:.1f}%')),
    ])
    sig_kv = ''.join(f'<div class="kv"><span>{k}</span><b class="num">{v}</b></div>' for k, v in [
        ('Signal type', side_name),
        ('Status', status_lbl),
        ('Trendline price', f'{row["line"]:,.2f}'),
        ('Distance to line', f'{dist:+.1f}%'),
        ('Anchor 1', str(row['anchor1'])[:10]),
        ('Anchor 2', str(row['anchor2'])[:10]),
        ('Line age', f'{int(row["days_since_anchor"])} trading days'),
        ('Line slope', f'{row["slope_yr_pct"]:+.1f}% / yr'),
    ])

    line_color = '#C05C1D' if side == 'upper' else '#0E9382'
    body = f"""
<section style="padding-bottom:76px"><div class="wrap">
  <div class="stock-head">
    <a href="{'breakouts.html' if side == 'upper' else 'supports.html'}" style="color:var(--ink3);font-size:13px">← Back to signals</a>
  </div>
  <div class="stock-head" style="margin-top:6px">
    <h1>{ticker}</h1>
    <button class="heart big" data-t="{ticker}" onclick="toggleWatch('{ticker}')">♡</button>
    <span class="co">{name}</span>
    <span class="pill {pill_cls}">{status_lbl}</span>
    <div class="price-block">
      <div style="display:flex;align-items:center;gap:10px;justify-content:flex-end">
        <span class="pb-price num">${last_close:,.2f}</span>
        <span id="chg-pill" class="chg-pill" data-d="{'' if chg_d is None else chg_d}"
              data-w="{'' if chg_w is None else chg_w}" data-m="{'' if chg_m is None else chg_m}">—</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;justify-content:flex-end;margin-top:6px">
        <span class="pb-cap">last close · {last_date}</span>
        <span class="pb-toggle">
          <button data-p="d" onclick="setPxPeriod('d')">1D</button><button data-p="w" onclick="setPxPeriod('w')">1W</button><button data-p="m" onclick="setPxPeriod('m')">1M</button>
        </span>
      </div>
    </div>
  </div>
  <div class="stock-grid">
    <div>
      <div class="info-panel">
        <h3>Company overview</h3>
        {kv}
        {f'<p class="about">{desc}</p>' if desc else ''}
      </div>
      <div class="info-panel" style="margin-top:18px">
        <h3>Signal details</h3>
        {sig_kv}
      </div>
    </div>
    <div>
      {confidence_card(row.get('confidence'))}
      <div class="chart-card">
        <div class="chart-head">
          <div class="view-toggle" role="tablist" aria-label="Chart style">
            <button data-view="candles" onclick="setChartView('candles')">Candles</button>
            <button data-view="line" onclick="setChartView('line')">Line</button>
          </div>
          <div class="tf-badge">{tf} chart</div>
        </div>
        <div class="chart-view" data-view="candles">{svg_candles}</div>
        <div class="chart-view" data-view="line">{svg_line}</div>
        <div class="cap">
          <span class="chart-view" data-view="candles">
            <span><span class="legend-dot" style="background:#0E9382"></span> Up candle</span>
            <span><span class="legend-dot" style="background:#C25B5B"></span> Down candle</span></span>
          <span class="chart-view" data-view="line">
            <span><span class="legend-dot" style="background:#49556A;opacity:.35"></span> High–Low range</span>
            <span><span class="legend-dot" style="background:#0F1726"></span> Close price</span></span>
          <span><span class="legend-dot" style="background:{line_color}"></span> {'Resistance' if side == 'upper' else 'Support'} diagonal (log scale)</span>
          <span><span class="legend-dot" style="background:{line_color};border-radius:50%"></span> Line anchors</span>
          <span style="margin-left:auto">data through {stamp}</span>
        </div>
      </div>
      <div class="notice" style="margin-top:16px">⚠️ Algorithmic output for research purposes — not investment advice.</div>
    </div>
  </div>
</div></section>
"""
    return page_fn(f'{ticker} — {name} · {BRAND_TITLE}', 'none', stamp, body,
                   f'{ticker} trendline analysis: {side_name.lower()}, confidence score, and company fundamentals.')


BRAND_TITLE = 'Trendlines'


def build_all(cand, page_fn, stamp, out_dir):
    os.makedirs(f'{out_dir}/stock', exist_ok=True)
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    cache = _load_cache()
    # one page per ticker; if a ticker appears on both sides, prefer the actual event row
    cand = cand.copy()
    cand['is_event'] = cand['status'] != 'APPROACHING'
    cand = (cand.sort_values(['is_event', 'confidence'], ascending=[False, False])
                .drop_duplicates(subset=['ticker'], keep='first'))
    built = 0
    for _, row in cand.iterrows():
        try:
            ov = fetch_overview(row['ticker'], cache)
            html = build_stock_page(row, ov, page_fn, stamp)
            with open(f'{out_dir}/stock/{row["ticker"]}.html', 'w', encoding='utf-8') as f:
                f.write(html)
            built += 1
        except Exception as e:
            print(f'  stock page failed {row["ticker"]}: {e}')
    json.dump(cache, open(CACHE_PATH, 'w'))
    print(f'stock pages built: {built}')
